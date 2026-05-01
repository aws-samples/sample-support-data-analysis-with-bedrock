#!/usr/bin/env python3
"""Build a DevOps Agent skill zip for the MAKITA PostgreSQL DR MCP servers.

The skill describes the 3 PostgreSQL MCP servers (failover, precheck,
postcheck) available through the AgentCore Gateway, so DevOps Agent
knows what tools it can invoke.

Output: dist/makita-postgresql-dr-skill.zip
"""

import json
import os
import zipfile

SKILL_NAME = "makita-postgresql-dr"
SKILL_DESCRIPTION = (
    "PostgreSQL Disaster Recovery skill for MAKITA. "
    "Provides pre-check, failover, and post-check tools for "
    "multi-region PostgreSQL DR operations via AgentCore Gateway."
)

SERVERS = [
    {
        "name": "makita-postgresql-precheck-mcp",
        "description": "Verifies cluster health before failover",
        "tools": [
            {
                "name": "verify_replication_health",
                "description": "Check replication lag and streaming status between primary and replica",
            },
            {
                "name": "verify_primary_status",
                "description": "Verify the primary PostgreSQL instance is in available state",
            },
            {
                "name": "verify_replica_readiness",
                "description": "Verify the DR replica is available and ready for promotion",
            },
        ],
    },
    {
        "name": "makita-postgresql-failover-mcp",
        "description": "Executes failover and promotes DR replica to primary",
        "tools": [
            {
                "name": "execute_failover",
                "description": "Promote the DR replica to primary, update Parameter Store endpoints, and verify the new primary is healthy",
            },
            {
                "name": "health_check",
                "description": "Check overall cluster health including replication lag and instance status",
            },
        ],
    },
    {
        "name": "makita-postgresql-postcheck-mcp",
        "description": "Verifies cluster state after failover",
        "tools": [
            {
                "name": "verify_new_primary_health",
                "description": "Verify the promoted replica is healthy as the new primary",
            },
            {
                "name": "verify_endpoints",
                "description": "Verify Parameter Store endpoints reflect the new primary",
            },
            {
                "name": "verify_replication_established",
                "description": "Verify replication is re-established from the new primary",
            },
        ],
    },
]


def build_skill_manifest() -> dict:
    return {
        "name": SKILL_NAME,
        "description": SKILL_DESCRIPTION,
        "version": "1.0.0",
        "servers": SERVERS,
    }


def main():
    dist_dir = os.path.join(os.path.dirname(__file__), "..", "dist")
    os.makedirs(dist_dir, exist_ok=True)
    zip_path = os.path.join(dist_dir, f"{SKILL_NAME}-skill.zip")

    manifest = build_skill_manifest()

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("skill.json", json.dumps(manifest, indent=2) + "\n")

    print(f"Created {zip_path}")
    print(f"  Servers: {len(SERVERS)}")
    print(f"  Tools: {sum(len(s['tools']) for s in SERVERS)}")


if __name__ == "__main__":
    main()
