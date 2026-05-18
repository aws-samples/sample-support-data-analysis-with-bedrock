# Sample Support Data Analysis and Actions with Amazon Bedrock, DevOps Agent and AgentCore

This repository demonstrates AI-powered operations using Amazon's GenAI and Agentic AI services.

## [MAKITA — Machine Augmented Key Infrastructure Technology Automation](makita/README.md)

MAKITA is a sample application demonstrating AI-assisted disaster recovery using Amazon DevOps Agent and Amazon AgentCore. It provisions a multi-region PostgreSQL cluster (us-east-1 primary, us-west-2 DR) and orchestrates automated failover through MCP servers built with governance via Cedar policies and Bedrock Guardrails.

See the [MAKITA README](makita/README.md) for prerequisites, architecture, and deployment instructions.

```mermaid
graph TB
    subgraph "DevOps Engineer"
        User[DevOps Engineer Chat]
    end

    subgraph "Amazon DevOps Agent"
        DA[DevOps Agent Space<br/>makita-agentspace]
    end

    subgraph "Amazon AgentCore"
        GW[AgentCore Gateway<br/>makita-mcp-gateway]

        subgraph "Governance Layer"
            BG_F[Bedrock Guardrails<br/>Failover]
            BG_Pre[Bedrock Guardrails<br/>Pre-Check]
            BG_Post[Bedrock Guardrails<br/>Post-Check]
            CP[Cedar Policies]
        end

        subgraph "AgentCore Runtimes"
            PreMCP[Pre-Check<br/>MCP Server]
            FailMCP[Failover<br/>MCP Server]
            PostMCP[Post-Check<br/>MCP Server]
        end
    end

    subgraph "us-east-1 (Primary Region)"
        PG_Primary[PostgreSQL<br/>Primary Instance]
        PS1[Parameter Store<br/>/makita/*]
    end

    subgraph "us-west-2 (DR Region)"
        PG_Replica[PostgreSQL<br/>Replica Instance]
    end

    User --> DA
    DA --> GW
    GW --> PreMCP
    GW --> FailMCP
    GW --> PostMCP

    CP -.->|restricts| GW
    BG_F -.->|governs| FailMCP
    BG_Pre -.->|governs| PreMCP
    BG_Post -.->|governs| PostMCP

    PreMCP --> PG_Primary
    PreMCP --> PG_Replica
    FailMCP --> PG_Primary
    FailMCP --> PG_Replica
    FailMCP --> PS1
    PostMCP --> PG_Replica
    PostMCP --> PS1

    PG_Primary -->|replication| PG_Replica
```

## Repository Structure

```
.
├── makita/                 # MAKITA project
├── CODE_OF_CONDUCT.md
├── CONTRIBUTING.md
├── LICENSE
└── README.md
```

## License

This project is licensed under the MIT-0 License. See the [LICENSE](LICENSE) file.

---

> **Note:** MAKI (Machine Augmented Key Insights) has been updated to MAKITA with new agentic patterns.
