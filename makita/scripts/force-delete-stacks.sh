#!/usr/bin/env bash
set -euo pipefail

# Force-delete all MAKITA resources: CloudFormation stacks, all AgentCore
# resources, DevOps Agent spaces, Cognito pools, Bedrock guardrails,
# IAM roles, SSM parameters, and CloudWatch log groups.
#
# Usage:
#   ./scripts/force-delete-stacks.sh              # full cleanup
#   ./scripts/force-delete-stacks.sh stacks-only   # only CloudFormation stacks

REGION="${AWS_DEFAULT_REGION:-us-east-1}"
DR_REGION="us-west-2"
MODE="${1:-all}"
PROJECT="makita"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "unknown")
AC="aws bedrock-agentcore-control --region $REGION"

echo "=== MAKITA Force Delete (account: ${ACCOUNT_ID}, region: ${REGION}) ==="
echo ""

# ---------------------------------------------------------------------------
# Helper: force delete a CloudFormation stack
# ---------------------------------------------------------------------------
get_stack_status() {
    aws cloudformation describe-stacks \
        --stack-name "$1" --region "$2" \
        --query 'Stacks[0].StackStatus' --output text 2>/dev/null || echo "GONE"
}

force_delete_stack() {
    local stack="$1" region="$2" status
    status=$(get_stack_status "$stack" "$region")
    if [ "$status" = "GONE" ] || [ "$status" = "DELETE_COMPLETE" ]; then
        echo "    ✓ $stack already gone"; return 0
    fi
    echo "    $stack ($status) — force deleting..."
    aws cloudformation delete-stack --stack-name "$stack" --region "$region" \
        --deletion-mode FORCE_DELETE_STACK 2>/dev/null || true
    local attempts=0
    while [ $attempts -lt 120 ]; do
        status=$(get_stack_status "$stack" "$region")
        case "$status" in
            GONE|DELETE_COMPLETE) echo "    ✓ $stack deleted"; return 0 ;;
            DELETE_IN_PROGRESS)  sleep 10; attempts=$((attempts + 10)) ;;
            DELETE_FAILED)
                echo "    Retrying force delete..."
                aws cloudformation delete-stack --stack-name "$stack" --region "$region" \
                    --deletion-mode FORCE_DELETE_STACK 2>/dev/null || true
                sleep 15; attempts=$((attempts + 15)) ;;
            *) sleep 5; attempts=$((attempts + 5)) ;;
        esac
    done
    echo "    ⚠ Timed out ($stack: $(get_stack_status "$stack" "$region"))"
}

# ---------------------------------------------------------------------------
# Helper: delete items from a list command, filtering by name prefix
# ---------------------------------------------------------------------------
ac_delete_by_name() {
    # Usage: ac_delete_by_name <list-action> <list-jmespath> <delete-action> <delete-id-param> <label>
    local list_action="$1" list_query="$2" delete_action="$3" id_param="$4" label="$5"
    for id in $($AC "$list_action" --query "$list_query" --output text 2>/dev/null || echo ""); do
        [ -z "$id" ] || [ "$id" = "None" ] && continue
        echo "  Deleting $label $id"
        $AC "$delete_action" --"$id_param" "$id" 2>/dev/null || true
    done
}

# ===========================================================================
# 1. CloudFormation stacks (both regions, nested first)
# ===========================================================================
echo "[1/10] CloudFormation stacks..."
for r in "$REGION" "$DR_REGION"; do
    STACKS=$(aws cloudformation list-stacks --region "$r" \
        --query "StackSummaries[?starts_with(StackName, \`Makita\`) && StackStatus!=\`DELETE_COMPLETE\`].{name:StackName,status:StackStatus}" \
        --output json 2>/dev/null || echo "[]")
    COUNT=$(echo "$STACKS" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))")
    if [ "$COUNT" != "0" ]; then
        echo "  $r: $COUNT stack(s)"
        NAMES=$(echo "$STACKS" | python3 -c "
import sys, json
for s in sorted(json.load(sys.stdin), key=lambda x: -len(x['name'])):
    print(s['name'])")
        for stack in $NAMES; do force_delete_stack "$stack" "$r"; done
    else
        echo "  $r: clean"
    fi
done

if [ "$MODE" = "stacks-only" ]; then
    echo ""; echo "=== Done (stacks only) ==="; exit 0
fi

# ===========================================================================
# 2. AgentCore gateway targets + rules + gateways
# ===========================================================================
echo ""
echo "[2/10] AgentCore gateways (targets, rules, gateways)..."
for GW_ID in $($AC list-gateways \
    --query "items[?starts_with(name, \`${PROJECT}\`)].gatewayId" --output text 2>/dev/null || echo ""); do
    [ -z "$GW_ID" ] || [ "$GW_ID" = "None" ] && continue
    # Targets
    for tid in $($AC list-gateway-targets --gateway-identifier "$GW_ID" \
        --query 'items[].targetId' --output text 2>/dev/null || echo ""); do
        [ -z "$tid" ] || [ "$tid" = "None" ] && continue
        echo "  Deleting target $tid"
        $AC delete-gateway-target --gateway-identifier "$GW_ID" --target-id "$tid" 2>/dev/null || true
    done
    # Rules
    for rid in $($AC list-gateway-rules --gateway-identifier "$GW_ID" \
        --query 'items[].ruleId' --output text 2>/dev/null || echo ""); do
        [ -z "$rid" ] || [ "$rid" = "None" ] && continue
        echo "  Deleting rule $rid"
        $AC delete-gateway-rule --gateway-identifier "$GW_ID" --rule-id "$rid" 2>/dev/null || true
    done
    sleep 5
    echo "  Deleting gateway $GW_ID"
    $AC delete-gateway --gateway-identifier "$GW_ID" 2>/dev/null || true
done
echo "  ✓ done"

# ===========================================================================
# 3. AgentCore runtimes + endpoints
# ===========================================================================
echo ""
echo "[3/10] AgentCore runtimes & endpoints..."
for rt in $($AC list-agent-runtimes \
    --query "agentRuntimes[?starts_with(agentRuntimeName, \`${PROJECT}\`)].agentRuntimeId" \
    --output text 2>/dev/null || echo ""); do
    [ -z "$rt" ] || [ "$rt" = "None" ] && continue
    # Endpoints
    for ep in $($AC list-agent-runtime-endpoints --agent-runtime-id "$rt" \
        --query 'agentRuntimeEndpoints[].agentRuntimeEndpointId' --output text 2>/dev/null || echo ""); do
        [ -z "$ep" ] || [ "$ep" = "None" ] && continue
        echo "  Deleting endpoint $ep"
        $AC delete-agent-runtime-endpoint --agent-runtime-id "$rt" --agent-runtime-endpoint-id "$ep" 2>/dev/null || true
    done
    echo "  Deleting runtime $rt"
    $AC delete-agent-runtime --agent-runtime-id "$rt" 2>/dev/null || true
done
echo "  ✓ done"

# ===========================================================================
# 4. AgentCore OAuth2 + API key credential providers
# ===========================================================================
echo ""
echo "[4/10] AgentCore credential providers..."
for name in $($AC list-oauth2-credential-providers \
    --query "oauth2CredentialProviders[?starts_with(name, \`${PROJECT}\`)].name" \
    --output text 2>/dev/null || echo ""); do
    [ -z "$name" ] || [ "$name" = "None" ] && continue
    echo "  Deleting OAuth2 provider $name"
    $AC delete-oauth2-credential-provider --name "$name" 2>/dev/null || true
done
for name in $($AC list-api-key-credential-providers \
    --query "apiKeyCredentialProviders[?starts_with(name, \`${PROJECT}\`)].name" \
    --output text 2>/dev/null || echo ""); do
    [ -z "$name" ] || [ "$name" = "None" ] && continue
    echo "  Deleting API key provider $name"
    $AC delete-api-key-credential-provider --name "$name" 2>/dev/null || true
done
echo "  ✓ done"

# ===========================================================================
# 5. AgentCore workload identities
# ===========================================================================
echo ""
echo "[5/10] AgentCore workload identities..."
for wid in $($AC list-workload-identities \
    --query "workloadIdentities[?starts_with(name, \`${PROJECT}\`)].name" \
    --output text 2>/dev/null || echo ""); do
    [ -z "$wid" ] || [ "$wid" = "None" ] && continue
    echo "  Deleting workload identity $wid"
    $AC delete-workload-identity --name "$wid" 2>/dev/null || true
done
echo "  ✓ done"

# ===========================================================================
# 6. AgentCore memories, browsers, code interpreters, policy engines
# ===========================================================================
echo ""
echo "[6/10] AgentCore memories, browsers, code interpreters, policy engines..."
for mid in $($AC list-memories \
    --query "memories[?starts_with(name, \`${PROJECT}\`)].memoryId" \
    --output text 2>/dev/null || echo ""); do
    [ -z "$mid" ] || [ "$mid" = "None" ] && continue
    echo "  Deleting memory $mid"
    $AC delete-memory --memory-id "$mid" 2>/dev/null || true
done
for bid in $($AC list-browsers \
    --query "browsers[?starts_with(name, \`${PROJECT}\`)].browserId" \
    --output text 2>/dev/null || echo ""); do
    [ -z "$bid" ] || [ "$bid" = "None" ] && continue
    echo "  Deleting browser $bid"
    $AC delete-browser --browser-id "$bid" 2>/dev/null || true
done
for cid in $($AC list-code-interpreters \
    --query "codeInterpreters[?starts_with(name, \`${PROJECT}\`)].codeInterpreterId" \
    --output text 2>/dev/null || echo ""); do
    [ -z "$cid" ] || [ "$cid" = "None" ] && continue
    echo "  Deleting code interpreter $cid"
    $AC delete-code-interpreter --code-interpreter-id "$cid" 2>/dev/null || true
done
for peid in $($AC list-policy-engines \
    --query "policyEngines[?starts_with(name, \`${PROJECT}\`)].policyEngineId" \
    --output text 2>/dev/null || echo ""); do
    [ -z "$peid" ] || [ "$peid" = "None" ] && continue
    echo "  Deleting policy engine $peid"
    $AC delete-policy-engine --policy-engine-id "$peid" 2>/dev/null || true
done
echo "  ✓ done"

# ===========================================================================
# 7. DevOps Agent spaces
# ===========================================================================
echo ""
echo "[7/10] DevOps Agent spaces..."
for space_id in $(aws devops-agent list-agent-spaces --region "$REGION" \
    --query "agentSpaces[?starts_with(name, \`${PROJECT}\`)].agentSpaceId" \
    --output text 2>/dev/null || echo ""); do
    [ -z "$space_id" ] || [ "$space_id" = "None" ] && continue
    echo "  Deleting agent space $space_id"
    aws devops-agent delete-agent-space --agent-space-id "$space_id" --region "$REGION" 2>/dev/null || true
done
echo "  ✓ done"

# ===========================================================================
# 8. Cognito User Pools + domains
# ===========================================================================
echo ""
echo "[8/10] Cognito User Pools..."
for pool_id in $(aws cognito-idp list-user-pools --max-results 60 --region "$REGION" \
    --query "UserPools[?starts_with(Name, \`${PROJECT}\`)].Id" \
    --output text 2>/dev/null || echo ""); do
    [ -z "$pool_id" ] || [ "$pool_id" = "None" ] && continue
    DOMAIN=$(aws cognito-idp describe-user-pool --user-pool-id "$pool_id" --region "$REGION" \
        --query 'UserPool.Domain' --output text 2>/dev/null || echo "")
    if [ -n "$DOMAIN" ] && [ "$DOMAIN" != "None" ]; then
        echo "  Deleting domain $DOMAIN"
        aws cognito-idp delete-user-pool-domain --domain "$DOMAIN" --user-pool-id "$pool_id" --region "$REGION" 2>/dev/null || true
    fi
    echo "  Deleting user pool $pool_id"
    aws cognito-idp delete-user-pool --user-pool-id "$pool_id" --region "$REGION" 2>/dev/null || true
done
echo "  ✓ done"

# ===========================================================================
# 9. Bedrock guardrails
# ===========================================================================
echo ""
echo "[9/10] Bedrock guardrails..."
for gid in $(aws bedrock list-guardrails --region "$REGION" \
    --query "guardrails[?starts_with(name, \`${PROJECT}\`)].guardrailId" \
    --output text 2>/dev/null || echo ""); do
    [ -z "$gid" ] || [ "$gid" = "None" ] && continue
    echo "  Deleting guardrail $gid"
    aws bedrock delete-guardrail --guardrail-identifier "$gid" --region "$REGION" 2>/dev/null || true
done
echo "  ✓ done"

# ===========================================================================
# 10. IAM roles, SSM parameters, CloudWatch log groups
# ===========================================================================
echo ""
echo "[10/10] IAM roles, SSM parameters, log groups..."
for role in makita-failover-role makita-precheck-role makita-postcheck-role makita-devops-agent-operator-role; do
    if aws iam get-role --role-name "$role" 2>/dev/null >/dev/null; then
        for arn in $(aws iam list-attached-role-policies --role-name "$role" \
            --query 'AttachedPolicies[].PolicyArn' --output text 2>/dev/null || echo ""); do
            aws iam detach-role-policy --role-name "$role" --policy-arn "$arn" 2>/dev/null || true
        done
        for pname in $(aws iam list-role-policies --role-name "$role" \
            --query 'PolicyNames[]' --output text 2>/dev/null || echo ""); do
            aws iam delete-role-policy --role-name "$role" --policy-name "$pname" 2>/dev/null || true
        done
        aws iam delete-role --role-name "$role" 2>/dev/null || true
        echo "  Deleted role $role"
    fi
done
aws ssm delete-parameters --region "$REGION" --names \
    /makita/db/primary-endpoint /makita/db/replica-endpoint \
    /makita/db/primary-region /makita/db/dr-region \
    /makita/db/cluster-name /makita/db/replication-status \
    /makita/db/port /makita/mcp/failover-server-arn \
    /makita/mcp/precheck-server-arn /makita/mcp/postcheck-server-arn \
    2>/dev/null || true
aws logs delete-log-group --log-group-name /makita/devops-agent --region "$REGION" 2>/dev/null || true
echo "  ✓ done"

# ===========================================================================
# Verify
# ===========================================================================
echo ""
echo "=== Verification ==="
echo "Stacks:"
aws cloudformation list-stacks --region "$REGION" \
    --query "StackSummaries[?starts_with(StackName, \`Makita\`) && StackStatus!=\`DELETE_COMPLETE\`].{Name:StackName,Status:StackStatus}" \
    --output table 2>/dev/null || echo "  (none)"
echo "Runtimes:  $($AC list-agent-runtimes --query "agentRuntimes[?starts_with(agentRuntimeName, \`${PROJECT}\`)].agentRuntimeName" --output text 2>/dev/null || echo "(none)")"
echo "Gateways:  $($AC list-gateways --query "items[?starts_with(name, \`${PROJECT}\`)].name" --output text 2>/dev/null || echo "(none)")"
echo "OAuth2:    $($AC list-oauth2-credential-providers --query "oauth2CredentialProviders[?starts_with(name, \`${PROJECT}\`)].name" --output text 2>/dev/null || echo "(none)")"
echo "Identities:$($AC list-workload-identities --query "workloadIdentities[?starts_with(name, \`${PROJECT}\`)].name" --output text 2>/dev/null || echo "(none)")"
echo "Cognito:   $(aws cognito-idp list-user-pools --max-results 60 --region "$REGION" --query "UserPools[?starts_with(Name, \`${PROJECT}\`)].Name" --output text 2>/dev/null || echo "(none)")"
echo "Guardrails:$(aws bedrock list-guardrails --region "$REGION" --query "guardrails[?starts_with(name, \`${PROJECT}\`)].name" --output text 2>/dev/null || echo "(none)")"
echo ""
echo "=== Force delete complete ==="
