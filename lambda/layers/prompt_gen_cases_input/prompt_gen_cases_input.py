import logging
import boto3
import json
import time
import sys
import ast

sys.path.append('/opt')
from s3 import get_category_examples, get_category_desc
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

def generate_15_digit_number():
    # Combine timestamp components
    timestamp = int(time.time() * 1000000)  # Get microsecond precision
    
    # Ensure 15 digits by using modulo
    max_15_digits = 999999999999999
    random_num = timestamp % max_15_digits
    
    # Pad with leading zeros if necessary
    result = str(random_num).zfill(15)
    
    return result

def generate_conversation(bedrock_client,
                          model_id,
                          system_prompts,
                          messages,
                          temperature):
    inference_config = {"temperature": temperature}
    response = bedrock_client.converse(
        modelId=model_id,
        messages=messages,
        system=system_prompts,
        inferenceConfig=inference_config,
    )

    return response

# this prompt generates the synthetic event
def gen_synth_prompt(model_id_text, examples, desc, category, temperature):
    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s: %(message)s")
    DisplayId = generate_15_digit_number()

    model_id = model_id_text

    system_prompt_text = "You are creating synthetic AWS Support Cases.  \
        Use the examples provided to create a new synthetic event. \
        The synthetic event must be different from the examples. \
        The synthetic event must follow the same format as the examples." 
    system_prompt_text += "The synthetic event content must tell a story of:\n" 
    system_prompt_text += category + "\n"
    system_prompt_text += desc + "\n"
    system_prompt_text += "DisplayId MUST BE: :" + DisplayId + ".\n"
    system_prompt_text += "Output a new synthetic event and nothing else."
    system_prompt_text += "OUTPUT MUST BE IN JSONL FORMAT."

    system_prompt_text = system_prompt_text.replace("\n", " ")
    
    #system_prompts = [{"text": system_prompt_text}, {"cachePoint":{"type":"default"}}]
    system_prompts = [{"text": system_prompt_text}]

    user_msg1 = "Create a new synthetic support event using these examples:"
    user_msg1 += examples
    user_msg1 += "OUTPUT MUST BE IN THE SAME FORMAT AS THE EXAMPLES. OUTPUT MUST BE IN JSONL FORMAT."

    message_1 = {
        "role": "user",
        "content": [{"text": user_msg1}]
    #    "content": [{"text": user_msg1}, {"cachePoint":{"type":"default"}}]
    }
    messages = []

    try:

        bedrock_client = boto3.client(service_name='bedrock-runtime')

        # Start the conversation with the 1st message.
        messages.append(message_1)
        response = generate_conversation(
            bedrock_client, model_id, system_prompts, messages, temperature)

        # Add the response message to the conversation.
        output_message = response['output']['message']
        messages.append(output_message)

        # Show the complete conversation.
        for message in messages:
            if message['role'] == 'assistant':
                out = message['content'][0]['text']
                return(out)

    except ClientError as err:
        message = err.response['Error']['Message']
        logger.error("A client error occurred: %s", message)
        print(f"A client error occured: {message}")

    else:
        print('')
      #      f"Finished generating text with model {model_id}.")


# this creates the batch inf records
def gen_batch_record(input_event,temperature,maxTokens,topP,categoryBucketName,categories,categoryOutputFormat):
    if (isinstance(input_event, str) == False):
        return("invalid input event:", input_event)
    
    categories = ast.literal_eval(categories)

    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s: %(message)s")

    # Setup the system prompts and messages to send to the model.
    system_prompt_text = "You are an AWS technical account manager.  \n\
        You are responsible for managing AWS accounts for customers. \n\
        You are responsible for categorizing different support events into the following Categories:\n" 

    n = 1
    for category in categories:
        system_prompt_text += str(n) + ". " + category + "\n"
        n += 1
    system_prompt_text += str(n) + ". Other.\n"

    for category in categories:
        examples_category = get_category_examples(categoryBucketName,category)
        desc_category = get_category_desc(categoryBucketName,category)
        system_prompt_text += "Here is a description of the Category: " + category + ": " + desc_category + "\n"
        system_prompt_text += "Here are some examples of the Category: " + category + "\n"
        system_prompt_text += examples_category + "\n"

    system_prompt_text += "You will respond with the Category that best matches the customer's support case.\n" 
    system_prompt_text += "Return the Category in the output field category.\n"
    system_prompt_text += "Explain why the Category was picked in output field category_explanation.\n"
    system_prompt_text += "If a support case does not match any of the above categories, return Other Support.\n"
    system_prompt_text += "Summarize the support case in the output field event_summary.\n"
    system_prompt_text += "Return Sentiment of the customer in the output field sentiment.\n"
    system_prompt_text += "Sentiment must be one of the following: Positive, Negative, Neutral.\n"
    system_prompt_text += "Return Suggested Action to the customer in the output field suggestion_action.\n"
    system_prompt_text += "Suggested Action must tell the customer how to fix the issue, and prevent it from re-occurrence.\n"
    system_prompt_text += "Return AWS document Suggesetion Link that supports the Suggested Action in the output field suggestion_link.\n"
    system_prompt_text += "Output must be in the following format:\n"
    system_prompt_text += json.dumps(categoryOutputFormat) + "\n"
    system_prompt_text += "Output above and nothing else.\n"
    system_prompt_text += "Output must be in JSON format.\n"
    system_prompt_text += "THINK STEP BY STEP\n"

    system_prompts = [{"text": system_prompt_text}]


    user_msg1 = "Categorize this <support_case>" + input_event + "</support_case>"
    message_1 = {
        "role": "user",
        "content": [{"text": user_msg1}]
    }

    messages = []
    messages.append(message_1)
   
    inf_params = {"maxTokens": maxTokens, "topP": topP, "temperature": temperature}

    recordId = 'maki-' + str(time.time())

    batch_record = {
        "recordId": recordId,
        "modelInput": {
            "messages": messages,
            "system": system_prompts,
            "inferenceConfig": inf_params
        }
    }

    jsonl = json.dumps(batch_record)
    return(jsonl)


