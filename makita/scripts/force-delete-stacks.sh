#!/usr/bin/env bash
set -euo pipefail

# Force-delete stuck CloudFormation stacks (DELETE_FAILED, ROLLBACK_FAILED,
# ROLLBACK_COMPLETE, CREATE_FAILED, UPDATE_ROLLBACK_COMPLETE).
#
# For DELETE_FAILED stacks, identifies the resources that failed to delete
# and retries with --retain-resources to skip them, then cleans up the
# retained resources individually.
#
# Usage:
#   ./scripts/force-delete-stacks.sh                  # all Makita* stacks
#   ./scripts/force-delete-stacks.sh MyStackName       # specific stack

REGION="${AWS_DEFAULT_REGION:-us-east-1}"
STACK_FILTER="${1:-Makita}"

echo "=== Force-delete stuck stacks matching '${STACK_FILTER}' in ${REGION} ==="
echo ""

# Stuck states that need intervention
STUCK_STATES="DELETE_FAILED ROLLBACK_FAILED ROLLBACK_COMPLETE CREATE_FAILED UPDATE_ROLLBACK_COMPLETE"

get_stack_status() {
    aws cloudformation describe-stacks \
        --stack-name "$1" --region "$REGION" \
        --query 'Stacks[0].StackStatus' --output text 2>/dev/null || echo "GONE"
}

get_failed_resources() {
    # Returns logical IDs of resources that failed to delete
    aws cloudformation list-stack-resources \
        --stack-name "$1" --region "$REGION" \
        --query 'StackResourceSummaries[?ResourceStatus==`DELETE_FAILED`].LogicalResourceId' \
        --output text 2>/dev/null || echo ""
}

delete_stack_with_retain() {
    local stack="$1"
    local status
    status=$(get_stack_status "$stack")

    if [ "$status" = "GONE" ] || [ "$status" = "DELETE_COMPLETE" ]; then
        echo "  ✓ $stack already deleted"
        return 0
    fi

    echo "  Stack: $stack (status: $status)"

    if [ "$status" = "DELETE_FAILED" ]; then
        # Get resources that failed to delete
        local failed_resources
        failed_resources=$(get_failed_resources "$stack")

        if [ -n "$failed_resources" ] && [ "$failed_resources" != "None" ]; then
            echo "  Failed resources: $failed_resources"
            echo "  Retrying delete with --retain-resources..."

            # Convert space-separated list to array for the CLI
            # shellcheck disable=SC2086
            aws cloudformation delete-stack \
                --stack-name "$stack" --region "$REGION" \
                --retain-resources $failed_resources 2>/dev/null || true
        else
            echo "  No specific failed resources found, force deleting..."
            aws cloudformation delete-stack \
                --stack-name "$stack" --region "$REGION" \
                --deletion-mode FORCE_DELETE_STACK 2>/dev/null || true
        fi

    elif [ "$status" = "ROLLBACK_COMPLETE" ] || [ "$status" = "CREATE_FAILED" ]; then
        # These can be deleted directly
        echo "  Deleting..."
        aws cloudformation delete-stack \
            --stack-name "$stack" --region "$REGION" 2>/dev/null || true

    elif [ "$status" = "ROLLBACK_FAILED" ] || [ "$status" = "UPDATE_ROLLBACK_COMPLETE" ]; then
        # Try normal delete first, fall back to force
        echo "  Deleting..."
        aws cloudformation delete-stack \
            --stack-name "$stack" --region "$REGION" 2>/dev/null || {
            echo "  Normal delete failed, trying force delete..."
            aws cloudformation delete-stack \
                --stack-name "$stack" --region "$REGION" \
                --deletion-mode FORCE_DELETE_STACK 2>/dev/null || true
        }
    else
        echo "  Skipping (status $status is not a stuck state)"
        return 0
    fi

    # Wait for deletion
    echo "  Waiting for deletion..."
    local attempts=0
    while [ $attempts -lt 60 ]; do
        status=$(get_stack_status "$stack")
        if [ "$status" = "GONE" ] || [ "$status" = "DELETE_COMPLETE" ]; then
            echo "  ✓ $stack deleted"
            return 0
        elif [ "$status" = "DELETE_FAILED" ]; then
            echo "  ✗ $stack still in DELETE_FAILED"
            # One more attempt with force
            echo "  Trying force delete..."
            aws cloudformation delete-stack \
                --stack-name "$stack" --region "$REGION" \
                --deletion-mode FORCE_DELETE_STACK 2>/dev/null || true
            sleep 15
            attempts=$((attempts + 15))
            continue
        fi
        sleep 5
        attempts=$((attempts + 5))
    done

    echo "  ⚠ Timed out waiting for $stack deletion (current status: $(get_stack_status "$stack"))"
    return 1
}

# Find all stuck stacks
echo "Scanning for stuck stacks..."
STACKS=$(aws cloudformation list-stacks --region "$REGION" \
    --stack-status-filter DELETE_FAILED ROLLBACK_FAILED ROLLBACK_COMPLETE CREATE_FAILED UPDATE_ROLLBACK_COMPLETE \
    --query "StackSummaries[?starts_with(StackName, \`${STACK_FILTER}\`)].{name:StackName, status:StackStatus}" \
    --output json 2>/dev/null || echo "[]")

COUNT=$(echo "$STACKS" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))")

if [ "$COUNT" = "0" ]; then
    echo "No stuck stacks found matching '${STACK_FILTER}'."
    exit 0
fi

echo "Found $COUNT stuck stack(s):"
echo "$STACKS" | python3 -c "
import sys, json
for s in json.load(sys.stdin):
    print(f\"  {s['name']} ({s['status']})\")"
echo ""

# Delete nested stacks first (longer names = deeper nesting), then parents
STACK_NAMES=$(echo "$STACKS" | python3 -c "
import sys, json
stacks = sorted(json.load(sys.stdin), key=lambda s: -len(s['name']))
for s in stacks:
    print(s['name'])")

for stack in $STACK_NAMES; do
    delete_stack_with_retain "$stack"
    echo ""
done

echo "=== Done ==="
