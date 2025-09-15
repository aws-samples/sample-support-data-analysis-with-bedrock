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

def aggregate_prompt(model_id_input, cases, temperature, summary_output_format, max_tokens):

    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s: %(message)s")

    # Setup the system prompts and messages to send to the model.
    system_prompt_text = "You are an AWS technical account manager.  \n\
        By reviewing all the AWS support cases of your customer, you will understand the aggrevate view of the customer.\n\
        You are responsible to derive an overall sentiment and plan to improve the customer's resilience on AWS.\n"
    system_prompt_text += "You will review the following support case summaries:\n"
    system_prompt_text += cases + "\n"
    system_prompt_text += "Return overall summary of the customer's experience on AWS as Summary.\n"
    system_prompt_text += "Discuss the aggregate Resilience themes in the Summary.\n"
    system_prompt_text += "DO NOT DISCUSS INDIVIDUAL CASES IN THE SUMMARY.\n"
    system_prompt_text += "Return overall plan to improve the customer's resilience on AWS as Plan.\n"
    system_prompt_text += "Output must be in the following format:\n"
    system_prompt_text += json.dumps(summary_output_format) + "\n"
    system_prompt_text += "Output the summary and nothing else.\n"
    system_prompt_text += "Output must be in JSON format.\n"

    system_prompt_text = system_prompt_text.replace("\n", " ")

    user_msg1 = "Return overall Summary and Plan for the customer.\n"

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