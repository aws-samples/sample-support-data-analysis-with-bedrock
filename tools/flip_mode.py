#!/usr/bin/env python3

import boto3
import argparse

def get_current_mode():
    """Get current MODE value from SSM Parameter Store"""
    ssm = boto3.client('ssm')
    account_id = boto3.client('sts').get_caller_identity()['Account']
    region = boto3.Session().region_name
    
    try:
        response = ssm.get_parameter(Name=f"maki-{account_id}-{region}-maki-mode")
        return response['Parameter']['Value']
    except Exception as e:
        print(f"Error getting current mode: {e}")
        return None

def set_mode(new_mode):
    """Set MODE value in SSM Parameter Store"""
    ssm = boto3.client('ssm')
    account_id = boto3.client('sts').get_caller_identity()['Account']
    region = boto3.Session().region_name
    
    try:
        ssm.put_parameter(
            Name=f"maki-{account_id}-{region}-maki-mode",
            Value=new_mode,
            Overwrite=True
        )
        print(f"Mode set to: {new_mode}")
    except Exception as e:
        print(f"Error setting mode: {e}")

def main():
    parser = argparse.ArgumentParser(description='Flip MODE between health and cases')
    parser.add_argument('--mode', choices=['health', 'cases'], help='Set specific mode')
    
    args = parser.parse_args()
    
    current_mode = get_current_mode()
    if current_mode:
        print(f"Current mode: {current_mode}")
    
    if args.mode:
        new_mode = args.mode
    else:
        # Flip mode
        new_mode = 'cases' if current_mode == 'health' else 'health'
    
    set_mode(new_mode)

if __name__ == "__main__":
    main()
