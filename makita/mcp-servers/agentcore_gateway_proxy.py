"""AgentCore Gateway stdio proxy.

Bridges a local stdio MCP transport to a remote AgentCore Gateway
using IAM SigV4 authentication. On startup, discovers all tools
from the gateway via tools/list and registers them locally.
"""

from __future__ import annotations

import asyncio
import json
import os
import time

import boto3
import httpx
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from mcp.server.fastmcp import FastMCP

GATEWAY_URL = os.environ["GATEWAY_URL"]
REGION = os.environ.get("AWS_REGION", "us-east-1")

mcp = FastMCP("agentcore-gateway-proxy")
_session = boto3.Session()


def _sigv4_headers(url: str, body: bytes) -> dict:
    req = AWSRequest(method="POST", url=url, data=body, headers={"Content-Type": "application/json"})
    SigV4Auth(_session.get_credentials(), "bedrock-agentcore", REGION).add_auth(req)
    return dict(req.headers)


async def _gateway_request(method: str, params: dict | None = None):
    payload = {"jsonrpc": "2.0", "id": f"req-{int(time.time())}", "method": method}
    if params:
        payload["params"] = params
    body = json.dumps(payload).encode()
    headers = _sigv4_headers(GATEWAY_URL, body)
    async with httpx.AsyncClient() as client:
        resp = await client.post(GATEWAY_URL, content=body, headers=headers, timeout=120)
        resp.raise_for_status()
        return resp.json().get("result", resp.json())


async def _register_gateway_tools():
    result = await _gateway_request("tools/list")
    for tool_def in result.get("tools", []):
        name = tool_def["name"]
        desc = tool_def.get("description", "")

        def make_handler(tool_name):
            async def handler(**kwargs):
                resp = await _gateway_request("tools/call", {"name": tool_name, "arguments": kwargs})
                content = resp.get("content", [])
                return "\n".join(c.get("text", str(c)) for c in content) if content else str(resp)
            return handler

        mcp.add_tool(make_handler(name), name=name, description=desc)


if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(_register_gateway_tools())
    mcp.run(transport="stdio")
