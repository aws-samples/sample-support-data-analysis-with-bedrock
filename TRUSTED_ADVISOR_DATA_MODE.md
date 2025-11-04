# AWS Trusted Advisor Data Mode for MAKI

## Overview

The AWS Trusted Advisor Data Mode extends MAKI's capabilities to analyze AWS Trusted Advisor recommendations, providing cost optimization, security, performance, and operational excellence insights through Amazon Bedrock analysis.

## Architecture

The Trusted Advisor Data Mode follows the same architectural patterns as the existing Support Cases and Health Events modes:

```
Support API → Lambda Data Retrieval → S3 Storage → Bedrock Analysis → Aggregated Reports
```

## Components Created

### 1. Data Retrieval
- **Lambda Function**: `getTrustedAdvisorFromAPI_handler.py`
- **Purpose**: Retrieves actionable Trusted Advisor recommendations from AWS Support API
- **Features**:
  - Filters recommendations by category (cost_optimizing, security, fault_tolerance, performance, service_limits)
  - Only processes actionable recommendations (warning/error status)
  - Generates structured Bedrock prompts for each recommendation
  - Stores individual recommendation files in S3

### 2. On-Demand Processing
- **Lambda Function**: `bedrockOnDemandInferenceTrustedAdvisor_handler.py`
- **Purpose**: Processes individual Trusted Advisor recommendations through Bedrock
- **Features**:
  - Exponential backoff retry logic
  - Individual recommendation analysis with cost and security focus
  - S3 file management with organized output structure

### 3. Batch Processing
- **Lambda Function**: `bedrockProcessBatchOutputTrustedAdvisor_handler.py`
- **Purpose**: Aggregates batch inference results for Trusted Advisor recommendations
- **Features**:
  - Processes multiple batch job outputs
  - Aggregates optimization insights
  - Generates executive summaries focused on cost and security

### 4. Prompt Aggregation Layer
- **Lambda Layer**: `prompt_agg_trusted_advisor`
- **Purpose**: Specialized prompt generation for Trusted Advisor aggregation
- **Features**:
  - Technical account manager persona with cost optimization expertise
  - Well-Architected Framework alignment
  - Strategic optimization recommendations

### 5. Data Collection Tool
- **Tool**: `get_trusted_advisor_recommendations.py`
- **Purpose**: Standalone tool for collecting Trusted Advisor data
- **Features**:
  - Direct Support API integration
  - Category-based filtering
  - File export capabilities
  - Comprehensive error handling

## Configuration

### New Configuration Constants (config.py)

```python
# Trusted Advisor Output Format
TRUSTED_ADVISOR_OUTPUT_FORMAT = "{ 
\"checkId\": \"checkId\", 
\"checkName\": \"checkName\", 
\"category\": \"category\", 
\"status\": \"status\", 
\"priority\": \"High|Medium|Low\", 
\"estimatedImpact\": \"estimatedImpact\", 
\"recommendation_summary\": \"recommendation_summary\", 
\"actionable_steps\": \"actionable_steps\", 
\"implementation_effort\": \"implementation_effort\", 
\"expected_benefits\": \"expected_benefits\" 
}"

# Lambda configurations for Trusted Advisor components
GET_TRUSTED_ADVISOR_FROM_API_NAME_BASE = 'GetTrustedAdvisorFromAPI'
BEDROCK_TRUSTED_ADVISOR_ONDEMAND_INF_NAME_BASE = 'trusted-advisor-ondemand-inference'
BEDROCK_PROCESS_TRUSTED_ADVISOR_ONDEMAND_OUTPUT_NAME_BASE = 'trusted-advisor-process-ondemand'
PROMPT_AGG_TRUSTED_ADVISOR_LAYER_NAME_BASE = 'MakiPromptAggTrustedAdvisor'
BUCKET_NAME_TRUSTED_ADVISOR_AGG_BASE = 'trusted-advisor-agg'
```

## Usage

### 1. State Machine Integration
The Trusted Advisor mode integrates with the existing MAKI state machine by adding a third data source option:

```json
{
  "mode": "trusted_advisor"
}
```

### 2. Data Collection
Use the standalone tool to collect Trusted Advisor data:

```bash
# Collect and display recommendations
python tools/get_trusted_advisor_recommendations.py --verbose

# Save recommendations to files
python tools/get_trusted_advisor_recommendations.py --output-dir ./trusted_advisor_data
```

### 3. Processing Flow
1. **Data Retrieval**: Support API queries for actionable recommendations
2. **Filtering**: Focus on cost_optimizing, security, fault_tolerance, performance, service_limits
3. **Analysis**: Bedrock processes each recommendation for optimization insights
4. **Aggregation**: Executive summaries with strategic optimization plans

## Key Features

### Cost Optimization Focus
- Identifies underutilized resources
- Recommends Reserved Instance opportunities
- Highlights cost-saving configurations
- Provides ROI estimates for optimizations

### Security Analysis
- Security group recommendations
- IAM policy optimizations
- Encryption and compliance checks
- Access control improvements

### Performance Optimization
- Resource sizing recommendations
- Configuration optimizations
- Service limit monitoring
- Performance bottleneck identification

### Well-Architected Alignment
- Maps recommendations to Well-Architected pillars
- Provides implementation guidance
- Prioritizes based on impact and effort
- Includes best practice references

## Output Structure

### Individual Recommendation Analysis
```json
{
  "checkId": "Qch7DwouX1",
  "checkName": "Low Utilization Amazon EC2 Instances",
  "category": "cost_optimizing",
  "status": "warning",
  "priority": "High",
  "estimatedImpact": "$2,400/month potential savings",
  "recommendation_summary": "5 EC2 instances with <10% CPU utilization",
  "actionable_steps": "Right-size or terminate underutilized instances",
  "implementation_effort": "Low - can be automated",
  "expected_benefits": "Immediate cost reduction with no performance impact"
}
```

### Executive Summary
```json
{
  "summary": "Customer has significant cost optimization opportunities with potential savings of $15,000/month across compute, storage, and networking. Security posture shows 3 high-priority items requiring immediate attention.",
  "plan": "1. Implement Reserved Instance strategy for 40% cost reduction. 2. Right-size underutilized EC2 instances. 3. Enable security group restrictions. 4. Implement automated backup policies."
}
```

## Requirements

### AWS Support Plan
- **Business or Enterprise Support**: Required for full Trusted Advisor API access
- **Basic Support**: Limited to 7 core checks only

### API Permissions
- `support:DescribeTrustedAdvisorChecks`
- `support:DescribeTrustedAdvisorCheckResult`

### Bedrock Access
- Access to configured text models for analysis
- Sufficient token limits for recommendation processing

## Integration with Existing MAKI Components

The Trusted Advisor Data Mode seamlessly integrates with existing MAKI infrastructure:

- **S3 Buckets**: Uses existing bucket structure with trusted-advisor prefix
- **State Machine**: Extends existing routing logic with third data source
- **Lambda Layers**: Reuses s3_utils, json_utils, and prompt_gen_input layers
- **Bedrock Models**: Uses same model configuration as other modes
- **Reporting**: Follows same timestamped directory structure

## Benefits

1. **Comprehensive Optimization**: Covers all five Well-Architected pillars
2. **Cost Visibility**: Quantifies potential savings and optimization opportunities
3. **Security Insights**: Identifies and prioritizes security improvements
4. **Operational Excellence**: Provides actionable recommendations for better operations
5. **Executive Reporting**: Delivers strategic insights for technical leadership

## Future Enhancements

1. **Cost Calculator Integration**: Precise savings calculations
2. **Automation Recommendations**: Suggest automation tools for implementations
3. **Trend Analysis**: Track optimization progress over time
4. **Custom Check Integration**: Support for custom Trusted Advisor checks
5. **Multi-Account Analysis**: Aggregate recommendations across AWS Organizations