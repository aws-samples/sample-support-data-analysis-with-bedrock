"""RDS failover manager for the makita-dr DR reference architecture."""

import logging
import time
from datetime import datetime

import boto3

from makita_dr.models import DNSUpdateResult, DRConfig, PromoteResult

logger = logging.getLogger(__name__)

# Polling configuration for replica promotion
_POLL_INTERVAL_SECONDS = 10
_MAX_POLL_ATTEMPTS = 60  # 10 minutes max wait


class RDSFailoverManager:
    """Manages RDS multi-region failover: identify, promote, DNS update, verify."""

    def __init__(self, config: DRConfig):
        self._config = config
        self._rds_primary = boto3.client("rds", region_name=config.primary_region)
        self._rds_dr = boto3.client("rds", region_name=config.dr_region)
        self._route53 = boto3.client("route53")

    def identify_instances(self) -> tuple:
        """Identify primary instance and read replica using Boto3 RDS client.

        Returns a tuple of (primary_info, replica_info) where each is the
        first element from the ``describe_db_instances`` response.

        Raises ``RuntimeError`` if either instance cannot be found.
        """
        try:
            primary_resp = self._rds_primary.describe_db_instances(
                DBInstanceIdentifier=self._config.primary_instance_id
            )
            primary_instances = primary_resp.get("DBInstances", [])
            if not primary_instances:
                raise RuntimeError(
                    f"Primary instance '{self._config.primary_instance_id}' "
                    f"not found in {self._config.primary_region}"
                )
            primary_info = primary_instances[0]

            replica_resp = self._rds_dr.describe_db_instances(
                DBInstanceIdentifier=self._config.replica_instance_id
            )
            replica_instances = replica_resp.get("DBInstances", [])
            if not replica_instances:
                raise RuntimeError(
                    f"Read replica '{self._config.replica_instance_id}' "
                    f"not found in {self._config.dr_region}"
                )
            replica_info = replica_instances[0]

            logger.info(
                "Identified primary '%s' in %s and replica '%s' in %s",
                self._config.primary_instance_id,
                self._config.primary_region,
                self._config.replica_instance_id,
                self._config.dr_region,
            )
            return (primary_info, replica_info)

        except Exception:
            logger.exception("Failed to identify RDS instances")
            raise

    def promote_read_replica(self) -> PromoteResult:
        """Promote the cross-region read replica to standalone read-write.

        Calls the Boto3 ``promote_read_replica`` API and then polls
        ``describe_db_instances`` until the instance status is ``available``
        and it is no longer a read replica.
        """
        instance_id = self._config.replica_instance_id
        try:
            self._rds_dr.promote_read_replica(
                DBInstanceIdentifier=instance_id,
            )
            logger.info("Initiated promotion of read replica '%s'", instance_id)

            # Poll until the instance is available and no longer a replica
            endpoint = self._wait_for_promotion(instance_id)

            return PromoteResult(
                success=True,
                promoted_instance_id=instance_id,
                promoted_endpoint=endpoint,
                message=f"Read replica '{instance_id}' promoted successfully",
                timestamp=datetime.utcnow(),
            )
        except Exception as exc:
            logger.exception("Failed to promote read replica '%s'", instance_id)
            return PromoteResult(
                success=False,
                promoted_instance_id=instance_id,
                promoted_endpoint="",
                message=f"Promotion failed: {exc}",
                timestamp=datetime.utcnow(),
            )

    def update_dns(self) -> DNSUpdateResult:
        """Update Route53 DNS CNAME record to point to the promoted instance endpoint."""
        try:
            # Get the promoted instance endpoint
            resp = self._rds_dr.describe_db_instances(
                DBInstanceIdentifier=self._config.replica_instance_id
            )
            instances = resp.get("DBInstances", [])
            if not instances:
                raise RuntimeError(
                    f"Instance '{self._config.replica_instance_id}' not found in DR region"
                )

            endpoint_address = instances[0].get("Endpoint", {}).get("Address", "")
            if not endpoint_address:
                raise RuntimeError(
                    f"Endpoint address not available for '{self._config.replica_instance_id}'"
                )

            # Update the Route53 CNAME record
            self._route53.change_resource_record_sets(
                HostedZoneId=self._config.dns_hosted_zone_id,
                ChangeBatch={
                    "Comment": "DR failover: update CNAME to promoted instance",
                    "Changes": [
                        {
                            "Action": "UPSERT",
                            "ResourceRecordSet": {
                                "Name": self._config.dns_record_name,
                                "Type": "CNAME",
                                "TTL": 60,
                                "ResourceRecords": [
                                    {"Value": endpoint_address}
                                ],
                            },
                        }
                    ],
                },
            )

            logger.info(
                "Updated DNS record '%s' to point to '%s'",
                self._config.dns_record_name,
                endpoint_address,
            )
            return DNSUpdateResult(
                success=True,
                record_name=self._config.dns_record_name,
                new_value=endpoint_address,
                message=f"DNS record updated to '{endpoint_address}'",
                timestamp=datetime.utcnow(),
            )
        except Exception as exc:
            logger.exception("Failed to update DNS record")
            return DNSUpdateResult(
                success=False,
                record_name=self._config.dns_record_name,
                new_value="",
                message=f"DNS update failed: {exc}",
                timestamp=datetime.utcnow(),
            )

    def verify_read_write(self) -> bool:
        """Verify the promoted instance is in read-write mode.

        Checks that the instance status is ``available`` and that
        ``ReadReplicaSourceDBInstanceIdentifier`` is empty (i.e. it is
        no longer a read replica).
        """
        try:
            resp = self._rds_dr.describe_db_instances(
                DBInstanceIdentifier=self._config.replica_instance_id
            )
            instances = resp.get("DBInstances", [])
            if not instances:
                logger.error(
                    "Instance '%s' not found during read-write verification",
                    self._config.replica_instance_id,
                )
                return False

            db = instances[0]
            status = db.get("DBInstanceStatus", "unknown")
            is_replica = bool(db.get("ReadReplicaSourceDBInstanceIdentifier"))

            if status == "available" and not is_replica:
                logger.info(
                    "Instance '%s' verified as read-write (status=%s, replica=%s)",
                    self._config.replica_instance_id,
                    status,
                    is_replica,
                )
                return True

            logger.warning(
                "Instance '%s' not in read-write mode (status=%s, replica=%s)",
                self._config.replica_instance_id,
                status,
                is_replica,
            )
            return False
        except Exception:
            logger.exception("Failed to verify read-write mode")
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _wait_for_promotion(self, instance_id: str) -> str:
        """Poll until the instance is available and no longer a replica.

        Returns the endpoint address of the promoted instance.
        Raises ``TimeoutError`` if the instance does not become available
        within the maximum polling window.
        """
        for attempt in range(_MAX_POLL_ATTEMPTS):
            resp = self._rds_dr.describe_db_instances(
                DBInstanceIdentifier=instance_id
            )
            db = resp["DBInstances"][0]
            status = db.get("DBInstanceStatus", "unknown")
            is_replica = bool(db.get("ReadReplicaSourceDBInstanceIdentifier"))

            if status == "available" and not is_replica:
                endpoint = db.get("Endpoint", {}).get("Address", "")
                logger.info(
                    "Replica '%s' promotion complete (attempt %d)",
                    instance_id,
                    attempt + 1,
                )
                return endpoint

            logger.debug(
                "Waiting for promotion: status=%s, is_replica=%s (attempt %d/%d)",
                status,
                is_replica,
                attempt + 1,
                _MAX_POLL_ATTEMPTS,
            )
            time.sleep(_POLL_INTERVAL_SECONDS)

        raise TimeoutError(
            f"Instance '{instance_id}' did not become available within "
            f"{_MAX_POLL_ATTEMPTS * _POLL_INTERVAL_SECONDS} seconds"
        )
