# MAKI FastMCP Agent

This document describes the MAKI FastMCP Agent that provides semantic and lexical search capabilities over the OpenSearch instance created by the MakiEmbeddings stack.

## Overview

The MAKI Agent is a FastMCP (Model Context Protocol) agent that integrates with Amazon Q CLI to query MAKI's health events and support case data stored in OpenSearch Serverless.

## Prerequisites

1. **Deploy Required Stacks**: The following CDK stacks must be deployed in order:
   - `MakiFoundations` - Core infrastructure
   - `MakiData` - Reference data
   - `MakiEmbeddings` - OpenSearch collection
   - `MakiAgents` - Agent infrastructure

2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **AWS Configuration**: Ensure your AWS credentials are configured and you have access to:
   - OpenSearch Serverless collections
   - Amazon Bedrock (for embeddings)
   - AWS Systems Manager Parameter Store

## Deployment

Deploy the MakiAgents stack:

```bash
cdk deploy MakiAgents
```

## Configuration

The agent is configured via the `mcp.json` file in the project root. Amazon Q CLI will automatically read this configuration.

### MCP Configuration (`mcp.json`)

Create an `mcp.json` file in your project root directory:

```json
{
  "mcpServers": {
    "maki-agent": {
      "command": "python",
      "args": ["maki/BuildAgents.py"],
      "env": {}
    }
  }
}
```

**Important**: The path `maki/BuildAgents.py` is relative to your project root directory. Ensure this file exists at the correct location.

## Usage

### Starting Amazon Q CLI

Once configured, start Amazon Q CLI in the project directory:

```bash
q chat
```

Amazon Q CLI will automatically detect and load the `mcp.json` configuration file in the current directory. The MAKI agent will be loaded and available for use.

### Available Tools

The agent provides three main tools accessible through Q CLI:

#### 1. Semantic Search
Performs vector-based semantic search using embeddings:
- Query: "database connection issues"
- Finds conceptually similar events
- Uses Amazon Titan embeddings

#### 2. Lexical Search
Performs exact term matching:
- Query: "RDS connectivity"
- Exact term matching across fields
- Multi-field search support

#### 3. Index Statistics
Gets information about the OpenSearch index:
- Document counts
- Storage size
- Index health status

### Example Queries in Q CLI

```
Search for database performance issues using semantic search
Find RDS connectivity problems with lexical search
Show me statistics for the health-events index
```

## Search Capabilities

### Semantic Search Features
- Uses Amazon Titan embeddings for vector search
- Finds conceptually similar events even with different terminology
- Supports natural language queries
- Returns relevance scores

### Lexical Search Features
- Exact term matching across specified fields
- Multi-field search capabilities
- Boolean query support
- Field-specific filtering

## Configuration

The agent uses AWS Systems Manager Parameter Store for configuration:

- `maki-{account}-{region}-opensearch-endpoint`: OpenSearch collection endpoint
- `maki-{account}-{region}-opensearch-query-size`: Maximum query results

## Troubleshooting

### Common Issues

1. **OpenSearch client not initialized**
   - Ensure MakiEmbeddings stack is deployed
   - Check SSM parameter for OpenSearch endpoint
   - Verify IAM permissions

2. **Bedrock access denied**
   - Ensure Bedrock model access is enabled
   - Check IAM permissions for bedrock:InvokeModel
   - Verify the Titan embedding model is available

3. **Agent not loading in Q CLI**
   - Verify mcp.json is in the correct directory
   - Check that all dependencies are installed
   - Ensure Python path is correct

### Testing

Test the agent configuration:

```bash
python test_agent.py
```

## Security

The agent follows security best practices:
- Uses IAM roles for authentication
- Leverages AWS-managed encryption
- Implements least-privilege access
- Integrates with existing MAKI security model
