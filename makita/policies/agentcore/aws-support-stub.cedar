// MAKITA AWS Support Stub MCP Server Policy
//
// Permits support case management actions.

permit(
  principal,
  action in [
    Action::"create_support_case",
    Action::"update_support_case"
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
    Action::"create_support_case",
    Action::"update_support_case"
  ]
};
