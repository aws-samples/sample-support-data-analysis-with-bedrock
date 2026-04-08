// MAKITA PostgreSQL Failover MCP Server Policy
//
// Permits failover and health-check actions on the PostgreSQL cluster.
// Restricts to makita-* resources in us-east-1 and us-west-2 only.

permit(
  principal,
  action in [
    Action::"execute_failover",
    Action::"health_check"
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
    Action::"execute_failover",
    Action::"health_check"
  ]
};
