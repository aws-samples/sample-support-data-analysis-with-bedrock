"""Custom MCP server running on Amazon Bedrock AgentCore.

Exposes DR failover tools to the DevOps Agent, enforces Bedrock Guardrails,
authenticates via Cognito (AgentCore Identity), and authorizes via AgentCore Policy.
All Guardrail evaluations and auth decisions are logged for audit.
"""

import json
import logging
from typing import Any, Dict, List, Optional

import boto3

from makita_dr.models import DRConfig

logger = logging.getLogger(__name__)

# Tool definitions exposed to the DevOps Agent
TOOL_DEFINITIONS = [
    {
        "name": "generate_failover_summary",
        "description": (
            "Generate a comprehensive summary of the DR failover event "
            "from start to finish by invoking the makita-dr-summary Lambda."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "event_data": {
                    "type": "object",
                    "description": "The full failover event data including pre-check results, "
                    "failover steps, post-check results, and incident management actions.",
                }
            },
            "required": ["event_data"],
        },
    },
]

# Actions that require Cognito-authenticated identity
COGNITO_RESTRICTED_ACTIONS = {"generate_failover_summary"}


class DRMCPServer:
    """Custom MCP server running on AgentCore.

    Provides tool discovery and invocation for the DevOps Agent.
    Enforces Bedrock Guardrails on all requests, authenticates callers
    via Cognito (AgentCore Identity), and authorizes via AgentCore Policy.
    """

    def __init__(
        self,
        config: DRConfig,
        lambda_client: Optional[Any] = None,
        bedrock_runtime_client: Optional[Any] = None,
        cognito_client: Optional[Any] = None,
    ):
        self._config = config
        self._lambda_client = lambda_client or boto3.client(
            "lambda", region_name=config.primary_region
        )
        self._bedrock_runtime_client = bedrock_runtime_client or boto3.client(
            "bedrock-runtime", region_name=config.primary_region
        )
        self._cognito_client = cognito_client or boto3.client(
            "cognito-idp", region_name=config.primary_region
        )
        self._audit_log: List[Dict[str, Any]] = []

    @property
    def audit_log(self) -> List[Dict[str, Any]]:
        """Return the audit log for inspection."""
        return list(self._audit_log)

    def list_tools(self) -> list:
        """Return tool definitions for DevOps Agent discovery."""
        return list(TOOL_DEFINITIONS)

    def invoke_tool(self, tool_name: str, params: dict, auth_token: Optional[str] = None) -> dict:
        """Invoke a tool with Guardrails, authentication, and authorization enforcement.

        Steps:
        1. Evaluate Guardrails on the request content
        2. Authenticate the caller via Cognito
        3. Authorize the action via AgentCore Policy
        4. Execute the tool

        Args:
            tool_name: Name of the tool to invoke.
            params: Parameters for the tool.
            auth_token: Cognito access token for authentication.

        Returns:
            Tool result or error response dict.
        """
        # Step 1: Guardrails evaluation
        guardrail_result = self._evaluate_guardrails(tool_name, params)
        if guardrail_result["action"] == "BLOCKED":
            return {
                "status": "error",
                "error_type": "guardrail_violation",
                "message": "Request blocked by Guardrail policy",
                "details": guardrail_result,
            }

        # Step 2: Authentication
        identity = self._authenticate(auth_token)
        if identity is None:
            return {
                "status": "error",
                "error_type": "authentication_error",
                "message": "Authentication failed: invalid or missing credentials",
            }

        # Step 3: Authorization
        if not self._authorize(identity, tool_name):
            return {
                "status": "error",
                "error_type": "authorization_error",
                "message": "Authorization failed: insufficient permissions",
            }

        # Step 4: Execute the tool
        if tool_name == "generate_failover_summary":
            return self.generate_failover_summary(params.get("event_data", {}))

        return {
            "status": "error",
            "error_type": "unknown_tool",
            "message": f"Unknown tool: {tool_name}",
        }

    def generate_failover_summary(self, event_data: dict) -> dict:
        """Invoke the makita-dr-summary Lambda to generate event summary.

        Args:
            event_data: Failover event data to summarize.

        Returns:
            Dict with status and summary or error details.
        """
        try:
            response = self._lambda_client.invoke(
                FunctionName=self._config.lambda_function_arn,
                InvocationType="RequestResponse",
                Payload=json.dumps(event_data),
            )
            payload = json.loads(response["Payload"].read())

            if payload.get("statusCode") == 200:
                logger.info("Lambda summary generated successfully")
                return {
                    "status": "success",
                    "summary": payload["summary"],
                }

            # Lambda returned an error in its response body
            error_msg = payload.get("error", "Unknown Lambda error")
            logger.error("Lambda returned error: %s", error_msg)
            return {
                "status": "error",
                "error_type": "lambda_error",
                "message": error_msg,
                "details": payload,
            }

        except Exception as exc:
            logger.error("Lambda invocation failed: %s", exc)
            return {
                "status": "error",
                "error_type": "lambda_invocation_error",
                "message": f"Lambda invocation failed: {str(exc)}",
            }

    def _evaluate_guardrails(self, tool_name: str, params: dict) -> dict:
        """Evaluate Bedrock Guardrails on the incoming request.

        Uses the Bedrock Runtime apply_guardrail API to check the request
        content against configured guardrail policies.

        Returns:
            Dict with 'action' key: 'ALLOWED' or 'BLOCKED', plus details.
        """
        request_content = json.dumps({"tool_name": tool_name, "params": params})
        result: Dict[str, Any] = {"action": "ALLOWED", "details": {}}

        try:
            response = self._bedrock_runtime_client.apply_guardrail(
                guardrailIdentifier=self._config.guardrail_id,
                guardrailVersion=self._config.guardrail_version,
                source="INPUT",
                content=[{"text": {"text": request_content}}],
            )
            action = response.get("action", "NONE")
            if action == "GUARDRAIL_INTERVENED":
                result = {
                    "action": "BLOCKED",
                    "details": {
                        "guardrail_id": self._config.guardrail_id,
                        "outputs": response.get("outputs", []),
                        "assessments": response.get("assessments", []),
                    },
                }
            else:
                result = {"action": "ALLOWED", "details": {"guardrail_id": self._config.guardrail_id}}

        except Exception as exc:
            logger.error("Guardrail evaluation failed: %s", exc)
            # Fail-closed: block on guardrail evaluation failure
            result = {
                "action": "BLOCKED",
                "details": {"error": str(exc)},
            }

        # Audit log entry
        self._audit_log.append({
            "event_type": "guardrail_evaluation",
            "tool_name": tool_name,
            "action": result["action"],
            "details": result["details"],
        })
        logger.info(
            "Guardrail evaluation for tool '%s': %s", tool_name, result["action"]
        )
        return result

    def _authenticate(self, auth_token: Optional[str]) -> Optional[dict]:
        """Authenticate the caller via Cognito (AgentCore Identity).

        Validates the access token against the Cognito User Pool.

        Args:
            auth_token: Cognito access token.

        Returns:
            User identity dict if authenticated, None otherwise.
        """
        identity: Optional[dict] = None

        if not auth_token:
            self._audit_log.append({
                "event_type": "authentication",
                "result": "rejected",
                "reason": "missing_token",
            })
            logger.warning("Authentication failed: no token provided")
            return None

        try:
            response = self._cognito_client.get_user(AccessToken=auth_token)
            username = response.get("Username", "unknown")
            identity = {
                "username": username,
                "user_attributes": {
                    attr["Name"]: attr["Value"]
                    for attr in response.get("UserAttributes", [])
                },
                "auth_source": "cognito",
            }
            self._audit_log.append({
                "event_type": "authentication",
                "result": "authenticated",
                "username": username,
            })
            logger.info("Authenticated user: %s", username)

        except Exception as exc:
            self._audit_log.append({
                "event_type": "authentication",
                "result": "rejected",
                "reason": str(exc),
            })
            logger.warning("Authentication failed: %s", exc)

        return identity

    def _authorize(self, identity: dict, tool_name: str) -> bool:
        """Authorize the action via AgentCore Policy.

        Checks that the authenticated identity has permission to invoke
        the requested tool. Lambda invocation is restricted to
        Cognito-authenticated identities only.

        Args:
            identity: Authenticated user identity dict.
            tool_name: The tool being invoked.

        Returns:
            True if authorized, False otherwise.
        """
        authorized = False

        # Policy rule: Lambda-invoking tools require Cognito auth source
        if tool_name in COGNITO_RESTRICTED_ACTIONS:
            authorized = identity.get("auth_source") == "cognito"
        else:
            # Non-restricted tools: any authenticated identity is allowed
            authorized = True

        self._audit_log.append({
            "event_type": "authorization",
            "username": identity.get("username", "unknown"),
            "tool_name": tool_name,
            "result": "authorized" if authorized else "denied",
        })
        logger.info(
            "Authorization for user '%s' on tool '%s': %s",
            identity.get("username", "unknown"),
            tool_name,
            "authorized" if authorized else "denied",
        )
        return authorized
