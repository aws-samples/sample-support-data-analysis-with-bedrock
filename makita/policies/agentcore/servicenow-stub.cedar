// MAKITA ServiceNow Stub MCP Server Policy
//
// Permits ticket management actions.

permit(
  principal,
  action in [
    Action::"create_ticket",
    Action::"update_ticket"
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
    Action::"create_ticket",
    Action::"update_ticket"
  ]
};
