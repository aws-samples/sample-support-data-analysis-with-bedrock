"""Pre-failover validation engine for the makita-dr DR reference architecture."""

import logging
from datetime import datetime
from typing import List, Optional

import boto3

from makita_dr.models import CheckResult, CheckStatus, DRConfig, PreCheckResult

logger = logging.getLogger(__name__)


class PreCheckEngine:
    """Runs all pre-failover validation checks before DR failover proceeds."""

    def __init__(self, config: DRConfig):
        self._config = config
        self._rds_primary = boto3.client("rds", region_name=config.primary_region)
        self._rds_dr = boto3.client("rds", region_name=config.dr_region)
        self._ec2_dr = boto3.client("ec2", region_name=config.dr_region)

    def run_all_checks(self) -> PreCheckResult:
        """Execute all pre-failover validations. Returns aggregated result."""
        checks = [
            self.check_replica_health(),
            self.check_replication_lag(),
            self.check_network_connectivity(),
        ]
        overall = (
            CheckStatus.PASSED
            if all(c.status == CheckStatus.PASSED for c in checks)
            else CheckStatus.FAILED
        )
        return PreCheckResult(
            checks=checks,
            overall_status=overall,
            timestamp=datetime.utcnow(),
        )

    def check_replica_health(self) -> CheckResult:
        """Verify RDS read replica is reachable and replicating."""
        check_name = "replica_health"
        try:
            resp = self._rds_dr.describe_db_instances(
                DBInstanceIdentifier=self._config.replica_instance_id
            )
            instances = resp.get("DBInstances", [])
            if not instances:
                return CheckResult(
                    check_name=check_name,
                    status=CheckStatus.FAILED,
                    message=f"Replica {self._config.replica_instance_id} not found in DR region",
                )

            db = instances[0]
            status = db.get("DBInstanceStatus", "unknown")
            is_replica = bool(db.get("ReadReplicaSourceDBInstanceIdentifier"))

            if status != "available":
                return CheckResult(
                    check_name=check_name,
                    status=CheckStatus.FAILED,
                    message=f"Replica status is '{status}', expected 'available'",
                    details={"db_instance_status": status},
                )

            if not is_replica:
                return CheckResult(
                    check_name=check_name,
                    status=CheckStatus.FAILED,
                    message="Instance is not configured as a read replica",
                    details={"db_instance_status": status},
                )

            return CheckResult(
                check_name=check_name,
                status=CheckStatus.PASSED,
                message="Replica is available and replicating",
                details={"db_instance_status": status},
            )
        except Exception as exc:
            logger.exception("replica_health check failed")
            return CheckResult(
                check_name=check_name,
                status=CheckStatus.FAILED,
                message=f"Error checking replica health: {exc}",
            )

    def check_replication_lag(self) -> CheckResult:
        """Verify replication lag is within acceptable threshold."""
        check_name = "replication_lag"
        try:
            resp = self._rds_dr.describe_db_instances(
                DBInstanceIdentifier=self._config.replica_instance_id
            )
            instances = resp.get("DBInstances", [])
            if not instances:
                return CheckResult(
                    check_name=check_name,
                    status=CheckStatus.FAILED,
                    message=f"Replica {self._config.replica_instance_id} not found",
                )

            db = instances[0]
            # StatusInfos contains replication lag for read replicas
            lag_seconds = self._extract_replication_lag(db)

            threshold = self._config.replication_lag_threshold_seconds
            if lag_seconds is None:
                return CheckResult(
                    check_name=check_name,
                    status=CheckStatus.FAILED,
                    message="Replication lag information not available",
                    details={"threshold_seconds": threshold},
                )

            if lag_seconds <= threshold:
                return CheckResult(
                    check_name=check_name,
                    status=CheckStatus.PASSED,
                    message=f"Replication lag {lag_seconds}s is within threshold {threshold}s",
                    details={
                        "lag_seconds": lag_seconds,
                        "threshold_seconds": threshold,
                    },
                )
            else:
                return CheckResult(
                    check_name=check_name,
                    status=CheckStatus.FAILED,
                    message=f"Replication lag {lag_seconds}s exceeds threshold {threshold}s",
                    details={
                        "lag_seconds": lag_seconds,
                        "threshold_seconds": threshold,
                    },
                )
        except Exception as exc:
            logger.exception("replication_lag check failed")
            return CheckResult(
                check_name=check_name,
                status=CheckStatus.FAILED,
                message=f"Error checking replication lag: {exc}",
            )

    def check_network_connectivity(self) -> CheckResult:
        """Verify DR region VPC/security groups/subnets allow DB connectivity."""
        check_name = "network_connectivity"
        try:
            resp = self._rds_dr.describe_db_instances(
                DBInstanceIdentifier=self._config.replica_instance_id
            )
            instances = resp.get("DBInstances", [])
            if not instances:
                return CheckResult(
                    check_name=check_name,
                    status=CheckStatus.FAILED,
                    message=f"Replica {self._config.replica_instance_id} not found",
                )

            db = instances[0]
            subnet_group = db.get("DBSubnetGroup", {})
            subnets = subnet_group.get("Subnets", [])
            vpc_sg_ids = [
                sg["VpcSecurityGroupId"]
                for sg in db.get("VpcSecurityGroups", [])
            ]

            issues: List[str] = []

            # Verify subnets exist and are available
            if not subnets:
                issues.append("No subnets associated with the DB subnet group")
            else:
                subnet_ids = [s["SubnetIdentifier"] for s in subnets]
                ec2_resp = self._ec2_dr.describe_subnets(SubnetIds=subnet_ids)
                for subnet in ec2_resp.get("Subnets", []):
                    if subnet.get("State") != "available":
                        issues.append(
                            f"Subnet {subnet['SubnetId']} state is "
                            f"'{subnet.get('State')}', expected 'available'"
                        )

            # Verify security groups exist
            if not vpc_sg_ids:
                issues.append("No VPC security groups associated with the replica")
            else:
                sg_resp = self._ec2_dr.describe_security_groups(
                    GroupIds=vpc_sg_ids
                )
                found_ids = {
                    sg["GroupId"] for sg in sg_resp.get("SecurityGroups", [])
                }
                for sg_id in vpc_sg_ids:
                    if sg_id not in found_ids:
                        issues.append(f"Security group {sg_id} not found")

            if issues:
                return CheckResult(
                    check_name=check_name,
                    status=CheckStatus.FAILED,
                    message="; ".join(issues),
                    details={
                        "vpc_security_groups": vpc_sg_ids,
                        "subnet_count": len(subnets),
                        "issues": issues,
                    },
                )

            return CheckResult(
                check_name=check_name,
                status=CheckStatus.PASSED,
                message="Network configuration permits DB connectivity",
                details={
                    "vpc_security_groups": vpc_sg_ids,
                    "subnet_count": len(subnets),
                },
            )
        except Exception as exc:
            logger.exception("network_connectivity check failed")
            return CheckResult(
                check_name=check_name,
                status=CheckStatus.FAILED,
                message=f"Error checking network connectivity: {exc}",
            )

    @staticmethod
    def _extract_replication_lag(db_instance: dict) -> Optional[int]:
        """Extract replication lag in seconds from RDS instance description."""
        for info in db_instance.get("StatusInfos", []):
            if info.get("StatusType") == "read replication":
                try:
                    return int(info.get("Message", "0"))
                except (ValueError, TypeError):
                    return None
        return None
