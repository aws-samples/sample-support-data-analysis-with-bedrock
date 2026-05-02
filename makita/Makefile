.PHONY: help install synth diff deploy deploy-primary deploy-replica \
       deploy-kiro-agent deploy-mcp-servers destroy destroy-primary destroy-replica \
       test lint clean generate-iam-policy build-skill-zip

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
PRIMARY_REGION  ?= us-east-1
DR_REGION       ?= us-west-2
CDK_DIR         := infra-cdk
SCRIPTS_DIR     := scripts
VENV            := .venv
PYTHON          := $(VENV)/bin/python
PIP             := $(VENV)/bin/pip
CDK             := PATH=$(CURDIR)/$(VENV)/bin:$$PATH npx cdk

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-24s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
install: $(VENV)/bin/activate ## Install Python dependencies
$(VENV)/bin/activate:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r $(CDK_DIR)/requirements.txt
	$(PIP) install -e ".[dev]"
	touch $(VENV)/bin/activate

# ---------------------------------------------------------------------------
# CDK commands
# ---------------------------------------------------------------------------
synth: install ## Synthesize all CDK stacks
	cd $(CDK_DIR) && $(CDK) synth

diff: install ## Show CDK diff for all stacks
	cd $(CDK_DIR) && $(CDK) diff

# ---------------------------------------------------------------------------
# Build artifacts
# ---------------------------------------------------------------------------
generate-iam-policy: install ## Generate IAM policy JSON for AgentCore runtimes
	$(PYTHON) $(SCRIPTS_DIR)/generate_iam_policy.py

build-skill-zip: install ## Build DevOps Agent skill zip
	$(PYTHON) $(SCRIPTS_DIR)/build_skill_zip.py

# ---------------------------------------------------------------------------
# Deploy
# ---------------------------------------------------------------------------
deploy: generate-iam-policy build-skill-zip deploy-primary deploy-replica ## Deploy everything
	@echo ""
	@echo "=== All stacks deployed ==="

deploy-primary: install ## Deploy Makita nested stack (PostgreSQL + AgentCore + DevOps Agent)
	@echo "[makita] Deploying to $(PRIMARY_REGION)..."
	cd $(CDK_DIR) && $(CDK) deploy Makita --require-approval never

deploy-replica: install ## Deploy cross-region PostgreSQL replica to us-west-2
	@echo "[makita] Deploying replica to $(DR_REGION)..."
	cd $(CDK_DIR) && $(CDK) deploy MakitaPostgresqlReplica --exclusively --require-approval never

deploy-mcp-servers: ## Deploy MCP servers to AgentCore Runtime (requires agentcore CLI)
	@echo "[makita] Deploying MCP servers to AgentCore Runtime..."
	$(SCRIPTS_DIR)/deploy-mcp-server.sh failover
	$(SCRIPTS_DIR)/deploy-mcp-server.sh precheck
	$(SCRIPTS_DIR)/deploy-mcp-server.sh postcheck

attach-runtime-permissions: ## Attach IAM permissions to AgentCore runtime roles
	$(SCRIPTS_DIR)/attach-runtime-permissions.sh

deploy-kiro-agent: install ## Deploy Kiro agent config
	@echo "[kiro-agent] Deploying Kiro agent config..."
	$(PYTHON) $(SCRIPTS_DIR)/deploy_kiro_agent.py

# ---------------------------------------------------------------------------
# Destroy (reverse order)
# ---------------------------------------------------------------------------
destroy: destroy-replica destroy-primary ## Destroy all stacks
	@echo ""
	@echo "=== All stacks destroyed ==="

destroy-replica: ## Destroy replica stack
	@echo "[makita] Destroying replica..."
	cd $(CDK_DIR) && $(CDK) destroy MakitaPostgresqlReplica --force || true

destroy-primary: ## Destroy Makita nested stack
	@echo "[makita] Destroying primary..."
	cd $(CDK_DIR) && $(CDK) destroy Makita --force || true

# ---------------------------------------------------------------------------
# Test & Lint
# ---------------------------------------------------------------------------
test: install ## Run tests
	$(PYTHON) -m pytest tests/ $(CDK_DIR)/tests/ -v

lint: install ## Lint CDK and CloudFormation templates
	$(PYTHON) -m py_compile $(CDK_DIR)/app.py
	cfn-lint infra-cfn/**/*.yaml || true

# ---------------------------------------------------------------------------
# Clean
# ---------------------------------------------------------------------------
clean: ## Remove build artifacts and venv
	rm -rf $(VENV) $(CDK_DIR)/cdk.out __pycache__ .pytest_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

clean-aws: ## Delete all orphaned AWS resources (runtimes, gateways, guardrails, etc.)
	$(SCRIPTS_DIR)/cleanup.sh

force-delete: ## Force-delete stuck CloudFormation stacks (DELETE_FAILED, ROLLBACK_*)
	$(SCRIPTS_DIR)/force-delete-stacks.sh

show-config: ## Print gateway registration parameters for the DevOps Agent manual step
	$(SCRIPTS_DIR)/show-gateway-config.sh
