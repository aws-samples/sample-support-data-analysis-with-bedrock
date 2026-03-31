"""Post-failover validation engine for the makita-dr DR reference architecture."""

import logging
from datetime import datetime

import boto3

from makita_dr.models import CheckResult, CheckStatus, DRConfig, PostCheckResult

logger = logging.getLogger(__name__)


class PostCheckEngine:
    """Runs all post-failover validation checks after DR failover completes."""

    def __init__(self, config: DRConfig):
        self._config = config
        self._rds_dr = boto3.client("rds", region_name=config.dr_region)
        self._route53 = boto3.client("route53", region_name=config.dr_region)

    def run_all_checks(self) -> PostCheckResult:
        """Execute all post-failover validations. Returns aggregated result."""
        checks = [
            self.check_read_write_mode(),
            self.check_application_queries(),
            self.check_dns_routing(),
        ]
        overall = (
            CheckStatus.PASSED
            if all(c.status == CheckStatus.PASSED for c in checks)
            else CheckStatus.FAILED
        )
        return PostCheckResult(
            checks=checks,
            overall_status=overall,
            timestamp=datetime.utcnow(),
        )

    def check_read_write_mode(self) -> CheckResult:
        """Verify promoted instance accepts read-write connections."""
        check_name = "read_write_mode"
        try:
            resp = self._rds_dr.describe_db_instances(
                DBInstanceIdentifier=self._config.replica_instance_id
            )
            instances = resp.get("DBInstances", [])
            if not instances:
                return CheckResult(
                    check_name=check_name,
                    status=CheckStatus.FAILED,
                    message=f"Instance {self._config.replica_instance_id} not found in DR region",
                )

            db = instances[0]
            status = db.get("DBInstanceStatus", "unknown")
            is_replica = bool(db.get("ReadReplicaSourceDBInstanceIdentifier"))

            if status != "available":
                return CheckResult(
                    check_name=check_name,
                    status=CheckStatus.FAILED,
                    message=f"Instance status is '{status}', expected 'available'",
                    details={"db_instance_status": status, "is_replica": is_replica},
                )

            if is_replica:
                return CheckResult(
                    check_name=check_name,
                    status=CheckStatus.FAILED,
                    message="Instance is still a read replica, not promoted to standalone",
                    details={"db_instance_status": status, "is_replica": True},
                )

            return CheckResult(
                check_name=check_name,
                status=CheckStatus.PASSED,
                message="Promoted instance is available in read-write mode",
                details={"db_instance_status": status, "is_replica": False},
            )
        except Exception as exc:
            logger.exception("read_write_mode check failed")
            return CheckResult(
                check_name=check_name,
                status=CheckStatus.FAILED,
                message=f"Error checking read-write mode: {exc}",
            )

    def check_application_queries(self) -> CheckResult:
        """Verify application endpoints can query the promoted database."""
        check_name = "application_queries"
        try:
            resp = self._rds_dr.describe_db_instances(
                DBInstanceIdentifier=self._config.replica_instance_id
            )
            instances = resp.get("DBInstances", [])
            if not instances:
                return CheckResult(
                    check_name=check_name,
                    status=CheckStatus.FAILED,
                    message=f"Instance {self._config.replica_instance_id} not found in DR region",
                )

            db = instances[0]
            status = db.get("DBInstanceStatus", "unknown")
            endpoint = db.get("Endpoint", {})
            address = endpoint.get("Address", "")
            port = endpoint.get("Port")

            if status != "available":
                return CheckResult(
                    check_name=check_name,
                    status=CheckStatus.FAILED,
                    message=f"Instance status is '{status}', expected 'available'",
                    details={"db_instance_status": status},
                )

            if not address:
                return CheckResult(
                    check_name=check_name,
                    status=CheckStatus.FAILED,
                    message="Instance endpoint address is not available",
                    details={"db_instance_status": status},
                )

            return CheckResult(
                check_name=check_name,
                status=CheckStatus.PASSED,
                message=f"Instance endpoint {address}:{port} is available for queries",
                details={
                    "db_instance_status": status,
                    "endpoint_address": address,
                    "endpoint_port": port,
                },
            )
        except Exception as exc:
            logger.exception("application_queries check failed")
            return CheckResult(
                check_name=check_name,
                status=CheckStatus.FAILED,
                message=f"Error checking application queries: {exc}",
            )

    def check_dns_routing(self) -> CheckResult:
        """Verify DNS/connection strings point to promoted instance."""
        check_name = "dns_routing"
        try:
            # Get the promoted instance endpoint
            resp = self._rds_dr.describe_db_instances(
                DBInstanceIdentifier=self._config.replica_instance_id
            )
            instances = resp.get("DBInstances", [])
            if not instances:
                return CheckResult(
                    check_name=check_name,
                    status=CheckStatus.FAILED,
                    message=f"Instance {self._config.replica_instance_id} not found in DR region",
                )

            db = instances[0]
            endpoint = db.get("Endpoint", {})
            instance_address = endpoint.get("Address", "")

            if not instance_address:
                return CheckResult(
                    check_name=check_name,
                    status=CheckStatus.FAILED,
                    message="Instance endpoint address is not available",
                )

            # Check Route53 DNS record
            dns_resp = self._route53.list_resource_record_sets(
                HostedZoneId=self._config.dns_hosted_zone_id,
                StartRecordName=self._config.dns_record_name,
                StartRecordType="CNAME",
                MaxItems="1",
            )
            record_sets = dns_resp.get("ResourceRecordSets", [])

            matching_record = None
            for rs in record_sets:
                if rs.get("Name", "").rstrip(".") == self._config.dns_record_name.rstrip("."):
                    matching_record = rs
                    break

            if not matching_record:
                return CheckResult(
                    check_name=check_name,
                    status=CheckStatus.FAILED,
                    message=f"DNS record '{self._config.dns_record_name}' not found in hosted zone",
                    details={"hosted_zone_id": self._config.dns_hosted_zone_id},
                )

            # Check if the DNS record points to the promoted instance
            resource_records = matching_record.get("ResourceRecords", [])
            record_values = [r.get("Value", "") for r in resource_records]

            if instance_address in record_values:
                return CheckResult(
                    check_name=check_name,
                    status=CheckStatus.PASSED,
                    message=f"DNS record points to promoted instance {instance_address}",
                    details={
                        "dns_record_name": self._config.dns_record_name,
                        "record_values": record_values,
                        "instance_address": instance_address,
                    },
                )
            else:
                return CheckResult(
                    check_name=check_name,
                    status=CheckStatus.FAILED,
                    message=f"DNS record does not point to promoted instance. "
                            f"Expected '{instance_address}', found {record_values}",
                    details={
                        "dns_record_name": self._config.dns_record_name,
                        "record_values": record_values,
                        "instance_address": instance_address,
                    },
                )
        except Exception as exc:
            logger.exception("dns_routing check failed")
            return CheckResult(
                check_name=check_name,
                status=CheckStatus.FAILED,
                message=f"Error checking DNS routing: {exc}",
            )
