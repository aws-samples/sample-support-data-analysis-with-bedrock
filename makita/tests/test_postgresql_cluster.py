"""
PostgreSQL cluster tests for the MAKITA CloudFormation templates.

Validates the primary instance in makita-postgresql-stack.yaml (us-east-1) and the
replica instance in makita-postgresql-replica-stack.yaml (us-west-2).

Validates: Requirement 23.3
"""

import yaml
import pytest
from pathlib import Path


PRIMARY_TEMPLATE_PATH = Path(__file__).parent.parent / "infrastructure" / "workloads" / "postgresql" / "makita-postgresql-stack.yaml"
REPLICA_TEMPLATE_PATH = Path(__file__).parent.parent / "infrastructure" / "workloads" / "postgresql" / "makita-postgresql-replica-stack.yaml"


# ---------------------------------------------------------------------------
# Custom YAML loader that handles CloudFormation intrinsic functions
# ---------------------------------------------------------------------------
class _CfnLoader(yaml.SafeLoader):
    """YAML loader that treats CloudFormation tags as plain data."""


def _cfn_tag_constructor(loader, tag_suffix, node):
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    elif isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node)
    return None


_CfnLoader.add_multi_constructor("!", _cfn_tag_constructor)


@pytest.fixture(scope="module")
def primary_template():
    with open(PRIMARY_TEMPLATE_PATH, "r") as f:
        return yaml.load(f, Loader=_CfnLoader)


@pytest.fixture(scope="module")
def primary_resources(primary_template):
    return primary_template.get("Resources", {})


@pytest.fixture(scope="module")
def primary_instance(primary_resources):
    return primary_resources["MakitaPgPrimary"]


@pytest.fixture(scope="module")
def replica_template():
    with open(REPLICA_TEMPLATE_PATH, "r") as f:
        return yaml.load(f, Loader=_CfnLoader)


@pytest.fixture(scope="module")
def replica_resources(replica_template):
    return replica_template.get("Resources", {})


@pytest.fixture(scope="module")
def replica_instance(replica_resources):
    return replica_resources["MakitaPgReplica"]


# =========================================================================
# Primary instance (us-east-1) — makita-postgresql-stack.yaml
# =========================================================================

class TestPrimaryInstance:

    def test_primary_resource_type(self, primary_instance):
        assert primary_instance["Type"] == "AWS::RDS::DBInstance"

    def test_primary_db_instance_identifier(self, primary_instance):
        assert primary_instance["Properties"]["DBInstanceIdentifier"] == "makita-pg-primary"

    def test_primary_engine_is_postgres(self, primary_instance):
        assert primary_instance["Properties"]["Engine"] == "postgres"

    def test_primary_has_db_name(self, primary_instance):
        assert primary_instance["Properties"].get("DBName") == "makitadb"

    def test_primary_port(self, primary_instance):
        assert primary_instance["Properties"].get("Port") == 5432

    def test_primary_is_not_publicly_accessible(self, primary_instance):
        assert primary_instance["Properties"].get("PubliclyAccessible") is False

    def test_primary_has_backup_retention(self, primary_instance):
        assert primary_instance["Properties"].get("BackupRetentionPeriod", 0) > 0

    def test_primary_storage_encrypted(self, primary_instance):
        assert primary_instance["Properties"].get("StorageEncrypted") is True

    def test_primary_region_parameter_confirms_us_east_1(self, primary_resources):
        for name, res in primary_resources.items():
            if res["Type"] == "AWS::SSM::Parameter":
                if res["Properties"]["Name"] == "/makita/db/primary-region":
                    assert res["Properties"]["Value"] == "us-east-1"
                    return
        pytest.fail("SSM parameter /makita/db/primary-region not found")


# =========================================================================
# Replica instance (us-west-2) — makita-postgresql-replica-stack.yaml
# =========================================================================

class TestReplicaInstance:

    def test_replica_template_exists(self):
        assert REPLICA_TEMPLATE_PATH.exists()

    def test_replica_resource_type(self, replica_instance):
        assert replica_instance["Type"] == "AWS::RDS::DBInstance"

    def test_replica_db_instance_identifier(self, replica_instance):
        assert replica_instance["Properties"]["DBInstanceIdentifier"] == "makita-pg-replica"

    def test_replica_has_source_db_instance_identifier(self, replica_instance):
        assert "SourceDBInstanceIdentifier" in replica_instance["Properties"]

    def test_replica_is_not_publicly_accessible(self, replica_instance):
        assert replica_instance["Properties"].get("PubliclyAccessible") is False

    def test_replica_does_not_define_engine(self, replica_instance):
        assert "Engine" not in replica_instance["Properties"]

    def test_dr_region_parameter_confirms_us_west_2(self, primary_resources):
        for name, res in primary_resources.items():
            if res["Type"] == "AWS::SSM::Parameter":
                if res["Properties"]["Name"] == "/makita/db/dr-region":
                    assert res["Properties"]["Value"] == "us-west-2"
                    return
        pytest.fail("SSM parameter /makita/db/dr-region not found")


# =========================================================================
# Replication configuration across both stacks
# =========================================================================

class TestReplicationHealth:

    def test_replica_source_is_parameterized(self, replica_template):
        """Replica stack should accept PrimaryInstanceArn as a parameter."""
        params = replica_template.get("Parameters", {})
        assert "PrimaryInstanceArn" in params

    def test_replication_status_parameter_is_active(self, primary_resources):
        for name, res in primary_resources.items():
            if res["Type"] == "AWS::SSM::Parameter":
                if res["Properties"]["Name"] == "/makita/db/replication-status":
                    assert res["Properties"]["Value"] == "active"
                    return
        pytest.fail("SSM parameter /makita/db/replication-status not found")

    def test_primary_endpoint_stored_in_parameter_store(self, primary_resources):
        found = any(
            res["Type"] == "AWS::SSM::Parameter"
            and res["Properties"]["Name"] == "/makita/db/primary-endpoint"
            for res in primary_resources.values()
        )
        assert found, "SSM parameter /makita/db/primary-endpoint not found"

    def test_replica_endpoint_stored_in_parameter_store(self, primary_resources):
        found = any(
            res["Type"] == "AWS::SSM::Parameter"
            and res["Properties"]["Name"] == "/makita/db/replica-endpoint"
            for res in primary_resources.values()
        )
        assert found, "SSM parameter /makita/db/replica-endpoint not found"

    def test_primary_stack_has_one_rds_instance(self, primary_resources):
        rds = [k for k, v in primary_resources.items() if v["Type"] == "AWS::RDS::DBInstance"]
        assert len(rds) == 1

    def test_replica_stack_has_one_rds_instance(self, replica_resources):
        rds = [k for k, v in replica_resources.items() if v["Type"] == "AWS::RDS::DBInstance"]
        assert len(rds) == 1

    def test_replica_stack_has_networking(self, replica_resources):
        """Replica stack should have its own VPC and subnet group."""
        types = {v["Type"] for v in replica_resources.values()}
        assert "AWS::EC2::VPC" in types
        assert "AWS::RDS::DBSubnetGroup" in types
        assert "AWS::EC2::SecurityGroup" in types

    def test_replica_stack_outputs_endpoint(self, replica_template):
        outputs = replica_template.get("Outputs", {})
        assert "ReplicaEndpoint" in outputs
