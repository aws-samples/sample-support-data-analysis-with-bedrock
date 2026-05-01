# Sample Support Data Analysis and Actions with Amazon Bedrock, DevOps Agent and AgentCore

This repository contains two self-contained projects that demonstrate AI-powered operations using Amazon's GenAI and AgenticAI services.

## Projects

### [MAKITA — Machine Augmented Key Infrastructure Technology Automation](makita/README.md)

MAKITA is a technical reference architecture demonstrating AI-assisted disaster recovery using Amazon DevOps Agent and Amazon AgentCore. It provisions a multi-region PostgreSQL cluster (us-east-1 primary, us-west-2 DR) and orchestrates automated failover through MCP servers built with the Strands Agents SDK, with governance via Cedar policies and Bedrock Guardrails.

```mermaid
graph TB
    subgraph "DevOps Engineer"
        User[DevOps Engineer Chat]
    end

    subgraph "Amazon DevOps Agent"
        DA[DevOps Agent]
    end

    subgraph "Amazon AgentCore"
        subgraph "Governance Layer"
            BG_F[Bedrock Guardrails<br/>Failover]
            BG_Pre[Bedrock Guardrails<br/>Pre-Check]
            BG_Post[Bedrock Guardrails<br/>Post-Check]
            AP[AgentCore Policies]
        end

        subgraph "MCP Servers"
            PreMCP[Pre-Check<br/>MCP Server]
            FailMCP[Failover<br/>MCP Server]
            PostMCP[Post-Check<br/>MCP Server]
            AWSS[AWS Support<br/>Stub Server]
            SNS[ServiceNow<br/>Stub Server]
        end
    end

    subgraph "us-east-1 (Primary)"
        PG_Primary[PostgreSQL Primary]
        PS[Parameter Store]
    end

    subgraph "us-west-2 (DR)"
        PG_Replica[PostgreSQL Replica]
    end

    User --> DA
    DA --> PreMCP
    DA --> FailMCP
    DA --> PostMCP
    DA --> AWSS
    DA --> SNS

    BG_F -.->|governs| FailMCP
    BG_Pre -.->|governs| PreMCP
    BG_Post -.->|governs| PostMCP
    AP -.->|restricts| PreMCP
    AP -.->|restricts| FailMCP
    AP -.->|restricts| PostMCP

    PreMCP --> PG_Primary
    PreMCP --> PG_Replica
    FailMCP --> PG_Primary
    FailMCP --> PG_Replica
    FailMCP --> PS
    PostMCP --> PG_Replica
    PostMCP --> PS

    PG_Primary -->|replication| PG_Replica
```

### [MAKI — Machine Augmented Key Insights](maki/README.md)

MAKI is a sample application that uses Amazon Bedrock to analyze AWS Enterprise Support cases and AWS Health events. It automates categorization, sentiment analysis, and generates actionable recommendations through both batch reporting and an interactive agentic workflow.

Note that MAKI pattern is now considered legacy and no longer maintained.  

#### Reporting and Analysis

![MAKI Reporting and Analysis Architecture](maki/maki-architecture-reporting-analysis.jpeg)

#### Agentic Workflow

![MAKI Agentic Workflow Architecture](maki/maki-architecture-agentic-workflow.jpeg)

## Repository Structure

```
.
├── makita/                 # MAKITA project
├── maki/                   # MAKI project
├── CODE_OF_CONDUCT.md
├── CONTRIBUTING.md
├── LICENSE
└── README.md
```

Each project is self-contained with its own CDK configuration, dependencies, and documentation. See the individual project READMEs for details.

## License

This project is licensed under the MIT-0 License. See the [LICENSE](LICENSE) file.
