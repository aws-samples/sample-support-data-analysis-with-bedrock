#!/usr/bin/env python3
"""
MAKI Synthetic Support Cases Generator

This tool generates realistic synthetic AWS support cases using Amazon Bedrock models for 
testing and development purposes. It creates cases across all predefined categories using 
example cases and category descriptions as templates.

Purpose:
- Generate test data when real support cases from CID are not available
- Create varied synthetic cases across all MAKI categories
- Support both small-scale testing and large-scale batch processing validation
- Enable development and testing without requiring AWS Enterprise Support

Categories Supported:
- limit-reached, customer-release, development-issue, customer-networking
- throttling, ice-error, feature-request, customer-dependency
- aws-release, customer-question, exceeding-capability, lack-monitoring
- security-issue, service-event, transient-issues, upgrade-management

Usage:
    python tools/generate_synth_cases.py                           # Generate default cases
    python tools/generate_synth_cases.py -q                       # Quick test (minimal cases)
    python tools/generate_synth_cases.py --min-cases 5 --max-cases 10  # Custom range

Key Features:
- Uses Bedrock models to generate realistic case content
- Configurable case volume per category
- Quick test mode for rapid validation
- Outputs in JSONL format for batch inference compatibility
- Integrates with MAKI's categorization and processing pipeline
"""

import sys
import os
import boto3
import logging
import random
import argparse

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)

# Add paths for config.py - handle both tools/ and root directory execution
if os.path.basename(current_dir) == 'tools':
    # Running from tools directory
    sys.path.append(parent_dir)
else:
    # Running from root directory
    sys.path.append(current_dir)

sys.path.append(os.path.join(parent_dir, 'lambda', 'layers', 's3_utils'))
sys.path.append(os.path.join(parent_dir, 'lambda', 'layers', 'prompt_gen_input'))

import config
from s3 import get_category_examples, get_category_desc, store_data
from prompt_gen_input import gen_synth_prompt, gen_batch_record_cases 

boto3_bedrock = boto3.client('bedrock')
model_id_text = config.BEDROCK_TEXT_MODEL

categoryBucketName = config.KEY + '-' + config.BUCKET_NAME_CATEGORY_BASE
genCasesBucketName = config.KEY + '-' + config.BUCKET_NAME_CASES_AGG_BASE

def parse_arguments():
    parser = argparse.ArgumentParser(description='Generate synthetic cases')
    parser.add_argument('--min-cases', type=int, default=1,
                      help='minimum number of cases generated (default: 1)')
    parser.add_argument('--max-cases', type=int, default=config.SYNTH_CASES_NUMBER_SEED,
                      help="max number of cases generated (default: config.SYNTH_CASES_NUMBER_SEED)")
    parser.add_argument('-q', '--quick-test', action='store_true',
                      help='generate cases for only 2 categories: limit-reached and service-event')
    
    return parser.parse_args()

def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s: %(message)s")

    args = parse_arguments()

    # Select categories based on quick-test flag
    categories = ['limit-reached'] if args.quick_test else config.CATEGORIES

    # for each category configured, create some synth records
    for category in categories:
        examples_category = get_category_examples(categoryBucketName,category)
        desc_category = get_category_desc(categoryBucketName,category)

        desc_category = '\n'.join(desc_category.splitlines()[1:])

        min = 1
        if args.min_cases:
            min = args.min_cases
        
        max = config.SYNTH_CASES_NUMBER_SEED
        if args.max_cases:
            max = args.max_cases
            
        start = 0
        end = random.randint(min, max)

        logging.info("\ngenerating " + str(end) + " cases for " + category)

        for i in range (start, end):
            # output must be in jsonl for Bedrock batch inerence
            n = i + 1
            key = 'case-gen-' + category + '-' + str(n) + '.jsonl'
        
            # first create the synth case, for the given category, for the given number of category cases
            synth_case = gen_synth_prompt(model_id_text=model_id_text,
                        examples=examples_category,
                        desc=desc_category,
                        category=category,
                        temperature=config.SYNTH_CASES_TEMPERATURE)
        
            logging.info("generating " + genCasesBucketName + '/' + key) 

            # then create a batch input record for each synth case
            # this now includes all categories for examples
            batch_record = gen_batch_record_cases(synth_case, 
                config.SYNTH_CASES_TEMPERATURE, 
                config.SYNTH_CASES_MAX_TOKENS, 
                config.SYNTH_CASES_CATEGORIZE_TOP_P,
                categoryBucketName,
                str(config.CATEGORIES),
                str(config.CASES_CATEGORY_OUTPUT_FORMAT)
            )

            store_data(batch_record, genCasesBucketName, key)

if __name__ == '__main__':
   main()

       

