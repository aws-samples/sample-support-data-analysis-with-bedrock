# Sample Support Data Analysis with Bedrock

This repository contains two projects that demonstrate AI-powered operations using Amazon Bedrock.

## Projects

### [MAKI — Machine Augmented Key Insights](MAKI_README.md)

MAKI is a sample application that uses Amazon Bedrock to analyze AWS Enterprise Support cases and AWS Health events. It automates categorization, sentiment analysis, and generates actionable recommendations through both batch reporting and an interactive agentic workflow via Amazon Q CLI.

➜ [MAKI README](MAKI_README.md) · [User Guide](MAKI_USER_GUIDE.md) · [Agent Guide](MAKI_AGENT_GUIDE.md)

### [MAKITA — Machine Augmented Key Infrastructure Technology Automation](makita/README.md)

> [!CAUTION]
> MAKITA is a work in progress and not ready for usage.

MAKITA is a technical reference architecture demonstrating AI-assisted disaster recovery using Amazon DevOps Agent and Amazon AgentCore. It provisions a multi-region PostgreSQL cluster (us-east-1 primary, us-west-2 DR) and orchestrates automated failover through MCP servers built with the Strands Agents SDK, with governance via Cedar policies and Bedrock Guardrails.

➜ [MAKITA README](makita/README.md)

## Repository Structure

```
.
├── MAKI_README.md          # MAKI project README
├── MAKI_USER_GUIDE.md      # MAKI deployment and usage guide
├── MAKI_AGENT_GUIDE.md     # MAKI agentic workflow guide
├── maki/                   # MAKI CDK stack and constructs
├── lambda/                 # MAKI Lambda functions
├── categories/             # MAKI event categorization definitions
├── tools/                  # MAKI utilities and scripts
├── makita/                 # MAKITA project (self-contained)
│   ├── README.md           # MAKITA project README
│   ├── infrastructure/     # CloudFormation templates
│   ├── mcp-servers/        # MCP server implementations
│   ├── orchestrator/       # Failover orchestration
│   ├── policies/           # Cedar policies and Bedrock Guardrails
│   └── scripts/            # Deployment and teardown scripts
├── app.py                  # CDK app entry point (MAKI)
├── config.py               # MAKI configuration
└── requirements.txt        # MAKI Python dependencies
```

## License

This project is licensed under the MIT-0 License. See the [LICENSE](LICENSE) file.
