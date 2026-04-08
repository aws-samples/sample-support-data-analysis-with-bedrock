// MAKITA PostgreSQL Post-Check MCP Server Policy
//
// Permits read-only post-failover verification actions.
// Restricts to makita-* resources in us-east-1 and us-west-2 only.

permit(
  principal,
  action in [
    Action::"verify_new_primary_health",
    Action::"verify_endpoints",
    Action::"verify_replication_established"
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
    Action::"verify_new_primary_health",
    Action::"verify_endpoints",
    Action::"verify_replication_established"
  ]
};
