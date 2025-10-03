"""
MAKI Health Events Aggregation Prompt Layer

This Lambda layer provides specialized prompt generation and aggregation capabilities 
for AWS Health events, creating operational summaries and health improvement 
recommendations from individual health event analyses.

Purpose:
- Generate operational summaries from multiple health event analyses
- Create health and monitoring improvement recommendations
- Provide SRE/DevOps manager perspective on infrastructure health
- Aggregate individual health insights into operational strategies

Key Features:
- Advanced Bedrock model integration for operational analysis
- Health event aggregation with operational focus
- Operational summary generation with actionable insights
- Infrastructure health status assessment
- Monitoring and alerting improvement plans
- JSON-formatted output for consistent reporting

Functions Provided:
- generate_conversation(): Core Bedrock conversation interface
- aggregate_prompt(): Main aggregation function for health events

Aggregation Capabilities:
- Multi-event operational synthesis
- Health and operational theme identification
- Overall infrastructure health assessment
- Operational improvement recommendations
- Executive-level operational summary generation

Prompt Engineering:
- SRE/DevOps manager persona specialized in health monitoring
- Operational resilience analysis framework
- Health monitoring recommendation generation
- Infrastructure optimization insights
- AWS operational best practices integration

Output Format:
- Structured JSON with Health Summary and Operational Plan fields
- Operational-level language and insights
- Actionable monitoring recommendations
- Strategic health themes
- Infrastructure health assessment

Integration Points:
- Bedrock runtime: Advanced model inference
- Batch processing: Large-scale health event aggregation
- On-demand processing: Real-time operational summary generation
- Report generation: Operational summary creation

Use Cases:
- Operational health reporting
- Infrastructure monitoring assessment and planning
- SRE team insights and recommendations
- Operational excellence initiatives
- Health monitoring strategy development
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
    system_prompt_text = "You are an AWS technical account manager specializing in health and operational monitoring.\n\
        By reviewing all the AWS health events and operational metrics of your customer, you will understand the aggregate health status of the customer's infrastructure.\n\
        You are responsible to derive an overall health assessment and plan to improve the customer's operational resilience on AWS.\n"
    system_prompt_text += "You will review the following health event summaries:\n"
    system_prompt_text += events + "\n"
    system_prompt_text += "Return overall summary of the customer's health status on AWS as Summary.\n"
    system_prompt_text += "Discuss the aggregate Health and Operational themes in the Summary.\n"
    system_prompt_text += "DO NOT DISCUSS INDIVIDUAL HEALTH EVENTS IN THE SUMMARY.\n"
    system_prompt_text += "Return overall plan to improve the customer's operational health and monitoring on AWS as Plan.\n"
    system_prompt_text += "Output must be in the following format:\n"
    system_prompt_text += json.dumps(summary_output_format) + "\n"
    system_prompt_text += "Output the summary and nothing else.\n"
    system_prompt_text += "Output must be in JSON format.\n"

    system_prompt_text = system_prompt_text.replace("\n", " ")

    user_msg1 = "Return overall Health Summary and Operational Plan for the customer.\n"

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
