#!/usr/bin/env python3
"""
MAKI Mode Management Tool

This tool manages MAKI's data source mode switching between 'cases' and 'health' processing 
modes through AWS Systems Manager Parameter Store. The mode determines which data pipeline 
and processing workflow MAKI uses.

Purpose:
- Switch between Support Cases mode and Health Events mode
- Display current mode configuration
- Toggle between modes automatically
- Manage SSM parameter: maki-{account}-{region}-maki-mode

Data Modes:
- 'cases': Processes AWS Enterprise Support cases from CID or synthetic data
- 'health': Processes AWS Health events from OpenSearch Serverless

Usage:
    python tools/flip_mode.py                    # Show current mode
    python tools/flip_mode.py --show            # Show current mode (explicit)
    python tools/flip_mode.py --mode cases      # Set to cases mode
    python tools/flip_mode.py --mode health     # Set to health mode
    python tools/flip_mode.py                   # Toggle between modes

Key Features:
- Automatic AWS account ID and region detection
- SSM Parameter Store integration for persistent configuration
- Mode validation and error handling
- Used by test scenarios to switch between processing modes
"""

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
            Type='String',
            Overwrite=True
        )
        print(f"Mode set to: {new_mode}")
    except Exception as e:
        print(f"Error setting mode: {e}")

def main():
    parser = argparse.ArgumentParser(description='Flip MODE between health and cases')
    parser.add_argument('--mode', choices=['health', 'cases'], help='Set specific mode')
    parser.add_argument('--show', action='store_true', help='Show current mode without changing it')
    
    args = parser.parse_args()
    
    current_mode = get_current_mode()
    if current_mode:
        print(f"Current mode: {current_mode}")
    
    if args.show:
        return
    
    if args.mode:
        new_mode = args.mode
    else:
        # Flip mode
        new_mode = 'cases' if current_mode == 'health' else 'health'
    
    set_mode(new_mode)

if __name__ == "__main__":
    main()
