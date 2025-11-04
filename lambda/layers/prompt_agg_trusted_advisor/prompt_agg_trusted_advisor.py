"""
MAKI Trusted Advisor Aggregation Prompt Layer

This Lambda layer provides specialized prompt generation and aggregation capabilities 
for AWS Trusted Advisor recommendations, creating operational summaries and optimization 
recommendations from individual Trusted Advisor analyses.

Purpose:
- Generate operational summaries from multiple Trusted Advisor recommendation analyses
- Create cost optimization and security improvement recommendations
- Provide technical account manager perspective on infrastructure optimization
- Aggregate individual recommendation insights into strategic optimization plans

Key Features:
- Advanced Bedrock model integration for optimization analysis
- Trusted Advisor recommendation aggregation with cost and security focus
- Operational summary generation with actionable insights
- Infrastructure optimization status assessment
- Cost optimization and security improvement plans
- JSON-formatted output for consistent reporting

Functions Provided:
- generate_conversation(): Core Bedrock conversation interface
- aggregate_prompt(): Main aggregation function for Trusted Advisor recommendations

Aggregation Capabilities:
- Multi-recommendation operational synthesis
- Cost optimization and security theme identification
- Overall infrastructure optimization assessment
- Strategic improvement recommendations
- Executive-level optimization summary generation

Prompt Engineering:
- Technical account manager persona specialized in cost optimization and security
- Operational excellence analysis framework
- Cost optimization recommendation generation
- Security and performance optimization insights
- AWS Well-Architected Framework integration

Output Format:
- Structured JSON with Optimization Summary and Action Plan fields
- Operational-level language and insights
- Actionable cost and security recommendations
- Strategic optimization themes
- Infrastructure optimization assessment

Integration Points:
- Bedrock runtime: Advanced model inference
- Batch processing: Large-scale recommendation aggregation
- On-demand processing: Real-time optimization summary generation
- Report generation: Optimization summary creation

Use Cases:
- Cost optimization reporting
- Security posture assessment and planning
- Infrastructure optimization insights
- Technical account management recommendations
- Well-Architected Framework alignment
"""

import logging
import boto3
import json

from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def generate_conversation(bedrock_client,
                          model_id,
                          system_prompts,
                          messages,
                          temperature,
                          max_tokens):

    # Base inference parameters to use.
    inference_config = {"maxTokens": int(max_tokens),"temperature": float(temperature)}

    # Send the message.
    response = bedrock_client.converse(
        modelId=model_id,
        messages=messages,
        system=system_prompts,
        inferenceConfig=inference_config
    )

    return response

def aggregate_prompt(model_id_input, events, temperature, summary_output_format, max_tokens):

    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s: %(message)s")

    # Setup the system prompts and messages to send to the model.
    system_prompt_text = "You are an AWS technical account manager specializing in cost optimization and security best practices.\n\
        By reviewing all the AWS Trusted Advisor recommendations for your customer, you will understand the aggregate optimization opportunities and security posture of the customer's infrastructure.\n\
        You are responsible to derive an overall optimization assessment and plan to improve the customer's cost efficiency, security, and operational excellence on AWS.\n"
    system_prompt_text += "You will review the following Trusted Advisor recommendation summaries:\n"
    system_prompt_text += events + "\n"
    system_prompt_text += "Return overall summary of the customer's optimization opportunities on AWS as Summary.\n"
    system_prompt_text += "Discuss the aggregate Cost Optimization, Security, Performance, and Fault Tolerance themes in the Summary.\n"
    system_prompt_text += "DO NOT DISCUSS INDIVIDUAL RECOMMENDATIONS IN THE SUMMARY.\n"
    system_prompt_text += "Return overall plan to improve the customer's cost efficiency, security posture, and operational excellence on AWS as Plan.\n"
    system_prompt_text += "Output must be in the following format:\n"
    system_prompt_text += json.dumps(summary_output_format) + "\n"
    system_prompt_text += "Output the summary and nothing else.\n"
    system_prompt_text += "Output must be in JSON format.\n"

    system_prompt_text = system_prompt_text.replace("\n", " ")

    user_msg1 = "Return overall Optimization Summary and Action Plan for the customer.\n"

# update later with prompt caching
#    system_prompts = [{"text": system_prompt_text}, {"cachePoint":{"type":"default"}}]
    system_prompts = [{"text": system_prompt_text}]

    message_1 = {
        "role": "user",
        "content": [{"text": user_msg1}]
#        "content": [{"text": user_msg1}, {"cachePoint":{"type":"default"}}]
    }

    messages = []

    out = '' 
    try:

        bedrock_client = boto3.client(service_name='bedrock-runtime')

  # Start the conversation with the 1st message.
        messages.append(message_1)
        response = generate_conversation(
            bedrock_client, model_id_input, system_prompts, messages, temperature, max_tokens)

        # Add the response message to the conversation.
        output_message = response['output']['message']
        messages.append(output_message)

        # Show the complete conversation.
        for message in messages: 
            if(message['role'] == 'assistant'): 
                for content in message['content']:
                    out += content['text']

    except ClientError as err:
        message = err.response['Error']['Message']
        logger.error("A client error occurred: %s", message)
        print(f"A client error occured: {message}")

    else:
        print('')

    return(out)