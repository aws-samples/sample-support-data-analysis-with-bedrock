// MAKITA PostgreSQL Pre-Check MCP Server Policy
//
// Permits read-only pre-failover verification actions.
// Restricts to makita-* resources in us-east-1 and us-west-2 only.

permit(
  principal,
  action in [
    Action::"verify_replication_health",
    Action::"verify_primary_status",
    Action::"verify_replica_readiness"
  ],
  resource
) when {
  resource has tags &&
  resource.tags.contains({"key": "proj", "value": "makita"}) &&
  resource.tags.contains({"key": "Env", "value": "prod1"})
};

forbid(
  principal,
  action,
  resource
) unless {
  action in [
    Action::"verify_replication_health",
    Action::"verify_primary_status",
    Action::"verify_replica_readiness"
  ]
};
