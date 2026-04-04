"""
PostgreSQL cluster tests for the MAKITA CloudFormation template.

Validates the PostgreSQL cluster configuration in infrastructure/makita-stack.yaml
by parsing the YAML directly and asserting on primary instance, replica instance,
and replication health configuration.

Validates: Requirement 23.3
"""

import yaml
import pytest
from pathlib import Path


TEMPLATE_PATH = Path(__file__).parent.parent / "infrastructure" / "makita-stack.yaml"


# ---------------------------------------------------------------------------
# Custom YAML loader that handles CloudFormation intrinsic functions
# ---------------------------------------------------------------------------
class _CfnLoader(yaml.SafeLoader):
    """YAML loader that treats CloudFormation tags as plain data."""


def _cfn_tag_constructor(loader, tag_suffix, node):
    """Generic constructor for any CloudFormation !Tag."""
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    elif isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node)
    return None


_CfnLoader.add_multi_constructor("!", _cfn_tag_constructor)


@pytest.fixture(scope="module")
def template():
    """Load and parse the CloudFormation template."""
    with open(TEMPLATE_PATH, "r") as f:
        return yaml.load(f, Loader=_CfnLoader)


@pytest.fixture(scope="module")
def resources(template):
    """Extract the Resources section from the template."""
    return template.get("Resources", {})


@pytest.fixture(scope="module")
def primary_instance(resources):
    """Extract the primary PostgreSQL instance resource."""
    return resources["MakitaPgPrimary"]


@pytest.fixture(scope="module")
def replica_instance(resources):
    """Extract the replica PostgreSQL instance resource."""
    return resources["MakitaPgReplica"]


# =========================================================================
# Requirement 23.3 — Primary instance in us-east-1
# =========================================================================

class TestPrimaryInstance:
    """Validate the PostgreSQL primary instance configuration.

    Validates: Requirement 23.3
    """

    def test_primary_resource_type(self, primary_instance):
        assert primary_instance["Type"] == "AWS::RDS::DBInstance"

    def test_primary_db_instance_identifier(self, primary_instance):
        props = primary_instance["Properties"]
        assert props["DBInstanceIdentifier"] == "makita-pg-primary"

    def test_primary_engine_is_postgres(self, primary_instance):
        props = primary_instance["Properties"]
        assert props["Engine"] == "postgres"

    def test_primary_has_db_name(self, primary_instance):
        props = primary_instance["Properties"]
        assert props.get("DBName") == "makitadb"

    def test_primary_port(self, primary_instance):
        props = primary_instance["Properties"]
        assert props.get("Port") == 5432

    def test_primary_is_not_publicly_accessible(self, primary_instance):
        props = primary_instance["Properties"]
        assert props.get("PubliclyAccessible") is False

    def test_primary_has_backup_retention(self, primary_instance):
        props = primary_instance["Properties"]
        assert props.get("BackupRetentionPeriod", 0) > 0

    def test_primary_storage_encrypted(self, primary_instance):
        props = primary_instance["Properties"]
        assert props.get("StorageEncrypted") is True

    def test_primary_region_parameter_confirms_us_east_1(self, resources):
        """The /makita/db/primary-region parameter confirms us-east-1."""
        for name, res in resources.items():
            if res["Type"] == "AWS::SSM::Parameter":
                if res["Properties"]["Name"] == "/makita/db/primary-region":
                    assert res["Properties"]["Value"] == "us-east-1"
                    return
        pytest.fail("SSM parameter /makita/db/primary-region not found")


# =========================================================================
# Requirement 23.3 — Replica instance in us-west-2
# =========================================================================

class TestReplicaInstance:
    """Validate the PostgreSQL replica instance configuration.

    Validates: Requirement 23.3
    """

    def test_replica_resource_type(self, replica_instance):
        assert replica_instance["Type"] == "AWS::RDS::DBInstance"

    def test_replica_db_instance_identifier(self, replica_instance):
        props = replica_instance["Properties"]
        assert props["DBInstanceIdentifier"] == "makita-pg-replica"

    def test_replica_has_source_db_instance_identifier(self, replica_instance):
        """Replica must reference the primary via SourceDBInstanceIdentifier."""
        props = replica_instance["Properties"]
        assert "SourceDBInstanceIdentifier" in props

    def test_replica_is_not_publicly_accessible(self, replica_instance):
        props = replica_instance["Properties"]
        assert props.get("PubliclyAccessible") is False

    def test_dr_region_parameter_confirms_us_west_2(self, resources):
        """The /makita/db/dr-region parameter confirms us-west-2."""
        for name, res in resources.items():
            if res["Type"] == "AWS::SSM::Parameter":
                if res["Properties"]["Name"] == "/makita/db/dr-region":
                    assert res["Properties"]["Value"] == "us-west-2"
                    return
        pytest.fail("SSM parameter /makita/db/dr-region not found")


# =========================================================================
# Requirement 23.3 — Replication health configuration
# =========================================================================

class TestReplicationHealth:
    """Validate replication configuration between primary and replica.

    Validates: Requirement 23.3
    """

    def test_replica_source_references_primary_arn(self, replica_instance):
        """SourceDBInstanceIdentifier should reference the primary's ARN
        (via !GetAtt MakitaPgPrimary.DBInstanceArn)."""
        props = replica_instance["Properties"]
        source = props["SourceDBInstanceIdentifier"]
        # The CfnLoader resolves !GetAtt to a string "MakitaPgPrimary.DBInstanceArn"
        assert source is not None
        assert "MakitaPgPrimary" in str(source)

    def test_replication_status_parameter_is_active(self, resources):
        """The /makita/db/replication-status parameter should be 'active'."""
        for name, res in resources.items():
            if res["Type"] == "AWS::SSM::Parameter":
                if res["Properties"]["Name"] == "/makita/db/replication-status":
                    assert res["Properties"]["Value"] == "active"
                    return
        pytest.fail("SSM parameter /makita/db/replication-status not found")

    def test_primary_endpoint_stored_in_parameter_store(self, resources):
        """A parameter for the primary endpoint must exist."""
        found = False
        for name, res in resources.items():
            if res["Type"] == "AWS::SSM::Parameter":
                if res["Properties"]["Name"] == "/makita/db/primary-endpoint":
                    found = True
                    break
        assert found, "SSM parameter /makita/db/primary-endpoint not found"

    def test_replica_endpoint_stored_in_parameter_store(self, resources):
        """A parameter for the replica endpoint must exist."""
        found = False
        for name, res in resources.items():
            if res["Type"] == "AWS::SSM::Parameter":
                if res["Properties"]["Name"] == "/makita/db/replica-endpoint":
                    found = True
                    break
        assert found, "SSM parameter /makita/db/replica-endpoint not found"

    def test_two_rds_instances_exist(self, resources):
        """There should be exactly 2 RDS DB instances (primary + replica)."""
        rds_instances = [
            k for k, v in resources.items()
            if v["Type"] == "AWS::RDS::DBInstance"
        ]
        assert len(rds_instances) == 2

    def test_replica_does_not_define_engine(self, replica_instance):
        """Cross-region replica inherits engine from source — Engine should
        not be explicitly set on the replica."""
        props = replica_instance["Properties"]
        assert "Engine" not in props, (
            "Replica should not explicitly set Engine; it inherits from the primary"
        )
