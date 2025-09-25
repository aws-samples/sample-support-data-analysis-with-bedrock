# MAKI User Guide
## Machine Augmented Key Insights for AWS Enterprise Support Data Analysis

### Table of Contents
1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Installation & Setup](#installation--setup)
4. [Configuration](#configuration)
5. [Deployment](#deployment)
6. [Usage](#usage)
7. [Data Sources](#data-sources)
8. [Output & Analysis](#output--analysis)
9. [Troubleshooting](#troubleshooting)
10. [Advanced Features](#advanced-features)

---

## Overview

MAKI (Machine Augmented Key Insights) is an educational sample application that demonstrates how Amazon Bedrock can analyze AWS data to derive meaningful insights. It supports two data source modes:

1. **Support Cases Mode**: Analyzes AWS Enterprise Support cases
2. **Health Events Mode**: Analyzes AWS Health events

### Key Features
- **Dual Data Source Support**: Process either support cases or health events
- **Automated Analysis**: Categorizes events into predefined categories
- **Sentiment Analysis**: Determines sentiment from event content
- **Actionable Insights**: Provides suggested actions and documentation links
- **Scalable Processing**: Uses both on-demand and batch inference based on volume
- **Comprehensive Reporting**: Generates detailed JSON reports for further analysis
- **Mode Switching**: Easy switching between data source modes

### Architecture Components
- **Amazon Bedrock**: LLM inference (light and sophisticated models)
- **Amazon S3**: Data storage and processing
- **AWS Lambda**: Serverless compute functions
- **AWS Step Functions**: Workflow orchestration with mode-based routing
- **Amazon CloudWatch**: Logging and monitoring
- **OpenSearch Serverless**: Health events storage and search (Health mode only)
- **AWS Systems Manager**: Parameter Store for mode configuration

---

## Prerequisites

### AWS Services Required
- AWS Enterprise Support (for real support case data)
- Amazon Bedrock with enabled models
- AWS Cloud Intelligence Dashboard (CID) - optional but recommended

### Development Environment
- Python 3.9+
- AWS CDK v2
- AWS CLI configured with appropriate permissions
- Node.js (for CDK)

### Required Permissions
- Bedrock model access and inference permissions
- S3 bucket creation and management
- Lambda function deployment
- Step Functions execution
- CloudWatch logging
- Systems Manager Parameter Store access
- OpenSearch Serverless access (for Health mode)
- AWS Health API access (for Health mode)

---

## Installation & Setup

### 1. Clone and Setup Environment
```bash
git clone <repository-url>
cd sample-support-data-analysis-with-bedrock

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -r tools/requirements.txt
```

### 2. Environment Validation
```bash
python tools/environment_validation.py
```

### 3. AWS Configuration
```bash
# Configure AWS CLI if not already done
aws configure

# Verify CDK installation
cdk --version

# Bootstrap CDK (if first time)
cdk bootstrap
```

---

## Configuration

### Core Configuration (`config.py`)

#### Model Configuration
```python
# Light model for individual event processing
BEDROCK_TEXT_MODEL = "us.amazon.nova-micro-v1:0"

# Sophisticated model for aggregation and synthesis
BEDROCK_TEXT_MODEL_AGG = "us.anthropic.claude-3-7-sonnet-20250219-v1:0"

# Embedding model for health events (Health mode only)
BEDROCK_EMBEDDING_MODEL = "amazon.titan-embed-text-v2:0"
```

#### Data Source Mode Configuration
MAKI operates in two distinct modes controlled by an SSM parameter:

- **Cases Mode**: Processes AWS Enterprise Support cases from CID
- **Health Mode**: Processes AWS Health events from OpenSearch

#### Processing Thresholds
```python
# Switch to batch processing when event count reaches this threshold
BEDROCK_ONDEMAND_BATCH_INFLECTION = 100
```

#### Event Categories
The system categorizes both support cases and health events into these predefined categories:
- `limit-reached`: Service limit issues
- `customer-release`: Customer deployment problems
- `development-issue`: Development and coding problems
- `customer-networking`: Network connectivity issues
- `throttling`: API throttling problems
- `ice-error`: Insufficient Capacity Errors
- `feature-request`: Feature requests
- `customer-dependency`: External dependency issues
- `aws-release`: AWS service release impacts
- `customer-question`: General questions
- `exceeding-capability`: Service capability limits
- `lack-monitoring`: Monitoring gaps
- `security-issue`: Security-related issues
- `service-event`: AWS service events
- `transient-issues`: Temporary problems
- `upgrade-management`: Upgrade-related issues

#### Data Source Configuration

##### Support Cases Mode
```python
# Use CID as data source for real support cases
CID_SKIP = 'false'  # Set to 'true' to skip CID and use synthetic data for testing

# Synthetic case generation settings (used when CID_SKIP = 'true')
SYNTH_CASES_NUMBER_SEED = 2  # Number of synthetic cases per category
```

##### Health Events Mode
```python
# OpenSearch configuration for health events
OPENSEARCH_COLLECTION_NAME = 'maki-health'
OPENSEARCH_INDEX = 'aws-health-events'
OPENSEARCH_SKIP = 'false'  # Set to 'true' to skip OpenSearch queries
```

### Mode Management

#### Current Mode Check
```bash
# Check current mode
python tools/flip_mode.py
```

#### Switch Modes
```bash
# Switch to Support Cases mode
python tools/flip_mode.py --mode cases

# Switch to Health Events mode
python tools/flip_mode.py --mode health

# Check current mode only (no changes)
python tools/flip_mode.py --show

# Toggle between modes (automatic flip)
python tools/flip_mode.py
```

#### Mode Configuration Details
The mode is stored in AWS Systems Manager Parameter Store:
- **Parameter Name**: `maki-{account}-{region}-maki-mode`
- **Valid Values**: `cases` or `health`
- **Default**: `health`

---

## Deployment

### 1. Deploy Foundation Stack
```bash
# Synthesize and review the foundation stack
cdk synth MakiFoundations

# Deploy the foundation infrastructure
cdk deploy MakiFoundations
```

This creates:
- VPC and networking components
- S3 buckets for data storage
- Lambda functions
- Step Functions state machine
- CloudWatch log groups
- IAM roles and policies

### 2. Deploy Data Stack
```bash
# Synthesize and review the data stack
cdk synth MakiData

# Deploy the data layer
cdk deploy MakiData
```

This adds:
- Reference data for case categorization
- Example cases for each category
- Configuration parameters

### 3. Deploy Embeddings Stack (Required for Health Mode)
```bash
# Deploy the embeddings stack for health events processing
cdk deploy MakiEmbeddings
```

This creates:
- OpenSearch Serverless collection for health events
- Vector embedding capabilities
- Additional IAM permissions for OpenSearch access

### 4. Verify Deployment
```bash
# List deployed stacks
aws cloudformation list-stacks --stack-status-filter CREATE_COMPLETE

# Check Step Functions
aws stepfunctions list-state-machines

# Verify OpenSearch collection (Health mode)
aws opensearchserverless list-collections
```
```bash
# List deployed stacks
aws cloudformation list-stacks --stack-status-filter CREATE_COMPLETE

# Check Step Functions
aws stepfunctions list-state-machines
```

---

## Usage

### Setting the Data Source Mode

Before running MAKI, set the appropriate mode for your data source:

```bash
# For Support Cases analysis
python tools/flip_mode.py --mode cases

# For Health Events analysis  
python tools/flip_mode.py --mode health

# Check current mode
python tools/flip_mode.py
```

### Method 1: Manual Execution (Development/Testing)
```bash
# Run the Step Function manually with monitoring
python tools/runMaki.py
```

This script:
- Shows current mode configuration
- Starts the Step Function execution
- Monitors progress in real-time
- Shows detailed step information
- Reports final results

### Method 2: Scheduled Execution (Sample Implementation)
The Step Function can be scheduled using Amazon EventBridge:
- Default schedule: Daily at 6:00 AM UTC
- Configurable via `config.py` CRON settings

### Method 3: Generate Synthetic Data (Support Cases Mode Only)
```bash
# Generate synthetic test cases
python tools/generate_synth_cases.py

# Generate with specific parameters
python tools/generate_synth_cases.py --min-cases 1 --max-cases 5
```

### Method 4: Load Health Events (Health Mode Only)
The included `tools/get_health_events.py` is an example tool that demonstrates how to retrieve AWS Health events and load them into OpenSearch. Your organization may implement other methods for health events ingestion based on your specific requirements.

```bash
# Load health events from AWS Health API to OpenSearch
python tools/get_health_events.py --load-to-opensearch

# Load events with custom date range
python tools/get_health_events.py --start-time "2024-01-01T00:00:00Z" --end-time "2024-12-31T23:59:59Z"

# Save events to files instead of OpenSearch
python tools/get_health_events.py --output-dir ./health_events --verbose
```

For comprehensive guidance on building AWS Health ingestion pipelines, refer to the [AWS documentation on AWS Health](https://docs.aws.amazon.com/health/latest/ug/what-is-aws-health.html)

---

## Data Sources

MAKI supports two distinct data source modes, each with its own data pipeline and processing workflow.

### Support Cases Mode

#### AWS Cloud Intelligence Dashboard (CID)
- **Purpose**: Primary source of real AWS support case data
- **Setup**: Deploy CID data layer before using MAKI
- **Configuration**: Set `CID_SKIP = 'false'` in config.py to use CID as data source
- **Data Flow**: Cases → CID → S3 → MAKI processing

#### Alternative Data Sources
Organizations may implement other methods for support case ingestion, such as pulling directly from the [AWS Support API](https://docs.aws.amazon.com/awssupport/latest/user/about-support-api.html).

#### Synthetic Data Generation (Testing)
- **Purpose**: Testing and development without real support data
- **Usage**: Automatically generates realistic test cases when `CID_SKIP = 'true'`
- **Categories**: Creates cases for all predefined categories
- **Command**: `python tools/generate_synth_cases.py`

### Health Events Mode

#### AWS Health API Integration
- **Purpose**: Analyzes AWS Health events for operational insights
- **Data Source**: AWS Health API via `describe_events` and related calls
- **Storage**: OpenSearch Serverless collection with vector embeddings
- **Processing**: Events enriched with embeddings for semantic search

#### Health Events Data Pipeline
1. **Collection**: Events retrieved from AWS Health API
2. **Enrichment**: Event descriptions converted to vector embeddings
3. **Storage**: Events stored in OpenSearch with searchable vectors
4. **Processing**: Events processed through Bedrock models for insights

#### Health Events Setup
```bash
# Load health events into OpenSearch
python tools/get_health_events.py --load-to-opensearch

# Verify events are loaded
python tools/get_health_events.py --count-only
```

### Data Flow Comparison

#### Support Cases Mode
1. **Ingestion**: Cases pulled from CID or generated synthetically
2. **Storage**: Raw cases stored in S3 bucket `maki-{account}-{region}-cases-agg`
3. **Processing**: Cases processed through Bedrock models
4. **Output**: Results stored in `maki-{account}-{region}-report`

#### Health Events Mode
1. **Ingestion**: Events pulled from AWS Health API
2. **Enrichment**: Events enhanced with vector embeddings
3. **Storage**: Events stored in OpenSearch Serverless collection
4. **Processing**: Events processed through Bedrock models with vector context
5. **Output**: Results stored in `maki-{account}-{region}-report`

---

## Output & Analysis

### Individual Event Analysis
Each processed event (support case or health event) generates a JSON file with:

#### Support Cases Output
```json
{
  "caseId": "case-961341536468-muen-2025-f09f14aa1c569098",
  "displayId": "173983009900080",
  "status": "pending-customer-action",
  "serviceCode": "service-bedrock",
  "timeCreated": "2025-02-17T22:08:19.234Z",
  "submittedBy": "customer@example.com",
  "category": "customer-question",
  "category_explanation": "The customer is asking a technical question...",
  "case_summary": "Customer inquiry about DeepSeek models in Bedrock",
  "sentiment": "Neutral",
  "suggested_action": "Refer to documentation and provide guidance",
  "suggestion_link": "https://docs.aws.amazon.com/bedrock/..."
}
```

#### Health Events Output
```json
{
  "arn": "arn:aws:health:us-east-1::event/EC2/AWS_EC2_INSTANCE_REBOOT_MAINTENANCE_SCHEDULED/...",
  "service": "EC2",
  "eventTypeCode": "AWS_EC2_INSTANCE_REBOOT_MAINTENANCE_SCHEDULED",
  "eventTypeCategory": "scheduledChange",
  "region": "us-east-1",
  "startTime": "2025-02-17T22:08:19.234Z",
  "lastUpdatedTime": "2025-02-17T22:08:19.234Z",
  "statusCode": "open",
  "eventScopeCode": "ACCOUNT_SPECIFIC",
  "latestDescription": "Scheduled maintenance for EC2 instances...",
  "category": "upgrade-management",
  "category_explanation": "This is a scheduled maintenance event...",
  "event_summary": "EC2 maintenance affecting customer instances",
  "sentiment": "Neutral",
  "suggested_action": "Review affected instances and plan accordingly",
  "suggestion_link": "https://docs.aws.amazon.com/ec2/..."
}
```

### Aggregate Analysis (`summary.json`)
```json
{
  "summary": "Overall analysis of customer experience patterns...",
  "plan": "Recommended actions to improve customer resilience..."
}
```

### Key Insights Provided
- **Categorization**: Automatic classification of support issues and health events
- **Sentiment Analysis**: Customer satisfaction and operational impact indicators
- **Root Cause Patterns**: Common issue themes across both data sources
- **Actionable Recommendations**: Specific improvement suggestions
- **Documentation Links**: Relevant AWS documentation
- **Vector Similarity**: Semantic search capabilities (Health mode only)

---

## Troubleshooting

### Common Issues

#### 1. Model Access Errors
```
Error: Could not access Bedrock model
```
**Solution**: Enable required models in Amazon Bedrock console
- Navigate to Amazon Bedrock → Model access
- Request access for Nova Micro and Claude models

#### 2. S3 Bucket Errors
```
Error: The specified bucket does not exist
```
**Solution**: Ensure CDK stacks are deployed
```bash
cdk deploy MakiFoundations
```

#### 3. Step Function Failures
**Check CloudWatch Logs**:
```bash
aws logs describe-log-groups --log-group-name-prefix maki
```

#### 4. Mode Configuration Issues
```
Error: Current mode: None
```
**Solution**: Initialize the mode parameter
```bash
python tools/flip_mode.py --mode cases  # or --mode health
```

#### 5. OpenSearch Access Errors (Health Mode)
```
Error: Access denied to OpenSearch collection
```
**Solution**: Ensure proper IAM permissions and collection policies
- Deploy MakiEmbeddings stack: `cdk deploy MakiEmbeddings`
- Verify collection exists: `aws opensearchserverless list-collections`

#### 6. Health Events Loading Issues
```
Error: No health events found
```
**Solution**: Check AWS Health API access and date ranges
```bash
# Verify Health API access
aws health describe-events --max-items 1

# Load events with broader date range
python tools/get_health_events.py --start-time "2023-01-01T00:00:00Z"
```

### Monitoring and Debugging

#### CloudWatch Log Groups
- `maki-{account}-{region}-log-group`: Main application logs
- Individual Lambda function logs

#### Step Function Monitoring
```bash
# List recent executions
aws stepfunctions list-executions --state-machine-arn <state-machine-arn>

# Get execution details
aws stepfunctions describe-execution --execution-arn <execution-arn>
```

---

## Advanced Features

#### Dual Mode Processing
- **Mode Switching**: Easy switching between support cases and health events
- **Unified Analysis**: Same analytical framework for both data sources
- **Consistent Output**: Standardized JSON format regardless of mode

#### Batch vs On-Demand Processing
- **On-Demand**: < 100 events, immediate processing
- **Batch**: ≥ 100 events, cost-effective batch processing
- **Configuration**: `BEDROCK_ONDEMAND_BATCH_INFLECTION = 100`
- **Mode Aware**: Works for both support cases and health events

#### Custom Categories
1. Add new category to `CATEGORIES` list in `config.py`
2. Create example files in `categories/{new-category}/`
3. Redeploy data stack: `cdk deploy MakiData`

#### Model Customization
```python
# Adjust model parameters
BEDROCK_CATEGORIZE_TEMPERATURE = 0.5
BEDROCK_CATEGORIZE_TOP_P = 0.1
BEDROCK_MAX_TOKENS = 10240

# Health mode specific - embedding model
BEDROCK_EMBEDDING_MODEL = "amazon.titan-embed-text-v2:0"
```

#### Vector Search Capabilities (Health Mode)
- **Semantic Search**: Find similar health events using vector embeddings
- **OpenSearch Integration**: Full-text and vector search capabilities
- **Embedding Generation**: Automatic vector creation for event descriptions

#### Integration with BI Tools
- Output JSON files can be consumed by:
  - Amazon QuickSight
  - Tableau
  - Power BI
  - Custom analytics applications
  - OpenSearch Dashboards (Health mode)

#### Future Enhancements (In Development)
- **Enhanced Health Integration**: Additional AWS Health event types
- **Cross-Mode Analysis**: Correlate support cases with health events
- **Advanced Vector Search**: Improved semantic search capabilities
- **Agentic Interface**: MCP servers for conversational data access

---

## Security Considerations

### Data Classification
- Support case and health event data may contain sensitive information
- Ensure proper data handling and retention policies
- Review AWS data classification standards
- This is sample code - implement appropriate security reviews for any real usage

### Access Control
- Use least-privilege IAM policies
- Implement proper VPC security groups
- Enable CloudTrail for audit logging

### Model Security
- Use cross-region inference profiles when available
- Implement prompt caching for efficiency
- Monitor model usage and costs

---

## Cost Optimization

### Bedrock Usage
- Use batch inference for large volumes (>100 cases)
- Implement prompt caching
- Choose appropriate model sizes for tasks

### Storage Optimization
- Configure S3 lifecycle policies (default: 90 days to IA)
- Use appropriate storage classes
- Clean up temporary processing files

### Monitoring Costs
- Set up billing alerts
- Monitor Bedrock token usage
- Track Lambda execution costs

---

## Support and Resources

### Documentation
- [Amazon Bedrock User Guide](https://docs.aws.amazon.com/bedrock/)
- [AWS CDK Documentation](https://docs.aws.amazon.com/cdk/)
- [AWS Step Functions Guide](https://docs.aws.amazon.com/step-functions/)

### Sample Data
- Synthetic case generation for testing
- Example categories with realistic scenarios
- Configurable data volume for development

### Community
- This is educational sample code for demonstration purposes
- Not intended for use without proper review and security assessment
- Implement appropriate oversight and security reviews for any deployment
- Follow your organization's software development and security practices

---

*This guide provides comprehensive instructions for deploying and using MAKI as a sample application. This is educational code intended for learning and demonstration purposes only.*
