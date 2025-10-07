# MAKI Agent Guide

This guide shows how to use MAKI as a FastMCP agent with Amazon Q CLI for interactive support data analysis.

## Prerequisites

- AWS CLI configured with appropriate permissions
- Python 3.8 or later
- Node.js 18 or later (for Amazon Q CLI)

## Step 1: Install Amazon Q CLI

### macOS/Linux
```bash
curl -sSL https://amazon-q-developer-cli.s3.us-west-2.amazonaws.com/install.sh | bash
```

### Windows (PowerShell)
```powershell
iwr -Uri "https://amazon-q-developer-cli.s3.us-west-2.amazonaws.com/install.ps1" -OutFile "install.ps1"; .\install.ps1
```

### Verify Installation
```bash
q --version
```

## Step 2: Deploy MAKI Infrastructure

Deploy the MAKI backend infrastructure first:

```bash
# Clone and navigate to MAKI directory
cd /path/to/sample-support-data-analysis-with-bedrock

# Deploy infrastructure (follow MAKI_USER_GUIDE.md for detailed steps)
cdk deploy
```

## Step 3: Set Up MCP Server

### Install Dependencies
```bash
pip install fastmcp boto3 pandas
```

### Create MCP Server Configuration
Create `mcp_config.json`:

```json
{
  "mcpServers": {
    "maki": {
      "command": "python",
      "args": ["maki_mcp_server.py"],
      "env": {
        "AWS_REGION": "us-east-1"
      }
    }
  }
}
```

### Create MAKI MCP Server
Create `maki_mcp_server.py`:

```python
from fastmcp import FastMCP
import boto3
import json

mcp = FastMCP("MAKI Support Analysis")

@mcp.tool()
def analyze_support_cases(query: str, time_range: str = "30d") -> str:
    """Analyze support cases using MAKI backend"""
    # Connect to your deployed MAKI infrastructure
    client = boto3.client('lambda')
    
    response = client.invoke(
        FunctionName='maki-analysis-function',
        Payload=json.dumps({
            'query': query,
            'timeRange': time_range
        })
    )
    
    return json.loads(response['Payload'].read())

@mcp.tool()
def get_case_insights(case_id: str) -> str:
    """Get detailed insights for a specific support case"""
    client = boto3.client('lambda')
    
    response = client.invoke(
        FunctionName='maki-case-insights-function',
        Payload=json.dumps({'caseId': case_id})
    )
    
    return json.loads(response['Payload'].read())

if __name__ == "__main__":
    mcp.run()
```

## Step 4: Configure Amazon Q CLI with MCP

```bash
# Initialize Q CLI with MCP configuration
q config set mcp-config-path ./mcp_config.json

# Start Q CLI with MCP support
q chat --mcp
```

## Example Queries

Once connected, you can use these example queries:

### General Support Analysis
```
Analyze support cases from the last 7 days and identify the top 3 most common issues
```

### Service-Specific Analysis
```
What are the trending EC2-related support cases this month?
```

### Case Deep Dive
```
Get detailed insights for support case 12345678901234567890
```

### Trend Analysis
```
Compare support case volume between this month and last month, broken down by service
```

### Sentiment Analysis
```
Analyze customer sentiment in support cases related to billing issues in the last 30 days
```

### Resolution Time Analysis
```
What's the average resolution time for P1 cases in the last quarter?
```

## Advanced Usage

### Custom Time Ranges
```
Analyze support cases from 2024-01-01 to 2024-03-31 for Lambda service issues
```

### Multi-Service Analysis
```
Compare support case patterns between S3, EC2, and RDS services over the last 60 days
```

### Executive Summary
```
Generate an executive summary of support trends and key insights for the last month
```

## Troubleshooting

### MCP Server Not Starting
- Verify Python dependencies are installed
- Check AWS credentials are configured
- Ensure MAKI infrastructure is deployed

### Connection Issues
- Verify `mcp_config.json` path is correct
- Check AWS region matches your deployment
- Confirm Lambda functions are accessible

### Query Errors
- Ensure case IDs are valid
- Check time range format (e.g., "7d", "30d", "2024-01-01")
- Verify you have permissions to access support data

## Next Steps

- Customize the MCP server for your specific use cases
- Add additional analysis functions
- Integrate with your existing support workflows
- Set up automated reporting using the Q CLI
