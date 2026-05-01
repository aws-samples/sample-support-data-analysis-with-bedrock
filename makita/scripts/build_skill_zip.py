#!/usr/bin/env python3
"""Build a DevOps Agent skill zip for the MAKITA PostgreSQL DR MCP servers.

Output: dist/makita-postgresql-dr-skill.zip
"""

import os
import zipfile

SKILL_MD = """\
---
name: makita-postgresql-dr
description: >
  PostgreSQL Disaster Recovery skill for MAKITA. Use this skill when
  investigating database connectivity issues, replication lag, failover
  events, or when a controlled failover is needed for RDS PostgreSQL
  instances tagged with proj=makita.
---

# MAKITA PostgreSQL Disaster Recovery

## When to Use
- Database connectivity alerts for proj=makita tagged RDS PostgreSQL instances
- Replication lag exceeding thresholds between us-east-1 and us-west-2
- Planned maintenance requiring cross-region failover
- Disaster recovery activation from us-east-1 to us-west-2

## Step 1: Pre-Failover Health Checks
Run all three pre-check tools to assess cluster readiness:
- `verify_replication_health` — Check replication lag and streaming status
- `verify_primary_status` — Verify the primary instance is available
- `verify_replica_readiness` — Verify the DR replica is ready for promotion

If any pre-check fails, do NOT proceed to failover. Report the failure.

## Step 2: Execute Failover
If all pre-checks pass and failover is approved:
- `execute_failover` — Promote the DR replica to primary and update Parameter Store endpoints
- `health_check` — Verify overall cluster health after promotion

## Step 3: Post-Failover Validation
After failover completes, validate the new state:
- `verify_new_primary_health` — Confirm the promoted replica is healthy
- `verify_endpoints` — Confirm Parameter Store endpoints reflect the new primary
- `verify_replication_established` — Confirm replication is re-established
"""


def main():
    dist_dir = os.path.join(os.path.dirname(__file__), "..", "dist")
    os.makedirs(dist_dir, exist_ok=True)
    zip_path = os.path.join(dist_dir, "makita-postgresql-dr-skill.zip")

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("SKILL.md", SKILL_MD)

    print(f"Created {zip_path}")


if __name__ == "__main__":
    main()
