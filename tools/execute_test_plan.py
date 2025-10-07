#!/usr/bin/env python3
"""
MAKI Test Plan Execution Engine

This tool automates the execution of MAKI's comprehensive test plan, validating functionality 
across different modes and processing types. It parses test_plan.md and executes all 7 test 
scenarios with output validation and progress monitoring.

Purpose:
- Automated testing of MAKI deployment and functionality
- Validation of both support cases and health events processing modes
- Output verification against expected JSON patterns using wildcards
- Progress monitoring with real-time step function execution tracking

Test Scenarios Covered:
1. Deploy - CDK stack deployment validation
2. Support Cases - Empty Dataset (error handling)
3. Support Cases - On-Demand Processing (< 100 cases)
4. Support Cases - Batch Processing (≥ 100 cases)
5. Health Events - Empty Dataset (error handling)
6. Health Events - On-Demand Processing (< 100 events)
7. Health Events - Batch Processing (≥ 100 events)

Usage:
    python tools/execute_test_plan.py                    # Execute full test plan
    python tools/execute_test_plan.py --test-case 3      # Execute only Test 3
    python tools/execute_test_plan.py --check-files-only # Only validate S3 outputs
    python tools/execute_test_plan.py --test-plan custom_test_plan.md # Use custom test plan file
    python tools/execute_test_plan.py --test-plan custom_test_plan.md # Use custom test plan file

Key Features:
- Real-time progress monitoring with elapsed time tracking
- JSON structure comparison with wildcard support (*)
- S3 output validation for batch and on-demand processing
- Automatic test failure detection and reporting
- Integration with runMaki.py for step function progress display
- Individual test case execution for faster iteration
"""

import subprocess
import sys
import os
import time
import threading
import argparse
import boto3
import json

def check_s3_files(section, expected_output):
    """Check S3 files for batch and ondemand processing"""
    if "Test Cases / Batch" not in section and "Test Cases / OnDemand" not in section:
        return True
        
    # Get AWS account and region
    sts_client = boto3.client("sts")
    account_id = sts_client.get_caller_identity()["Account"]
    region = boto3.session.Session().region_name
    
    s3_client = boto3.client('s3')
    bucket_name = f'maki-{account_id}-{region}-report'
    
    try:
        if "Test Cases / Batch" in section:
            # Handle batch processing
            response = s3_client.list_objects_v2(
                Bucket=bucket_name,
                Prefix='batch/',
                Delimiter='/'
            )
            
            if 'CommonPrefixes' not in response:
                print("❌ No batch directories found")
                return False
                
            # Get the latest batch directory
            batch_dirs = [prefix['Prefix'] for prefix in response['CommonPrefixes']]
            latest_batch = sorted(batch_dirs)[-1]
            
            # Check for summary.json
            summary_key = f"{latest_batch}summary.json"
            try:
                summary_obj = s3_client.get_object(Bucket=bucket_name, Key=summary_key)
                summary_content = summary_obj['Body'].read().decode('utf-8')
                print(f"✅ Found summary: s3://{bucket_name}/{summary_key}")
            except:
                print(f"❌ Summary not found: s3://{bucket_name}/{summary_key}")
                return False
                
            # Check for event files
            events_prefix = f"{latest_batch}events/"
            events_response = s3_client.list_objects_v2(
                Bucket=bucket_name,
                Prefix=events_prefix,
                MaxKeys=10
            )
            
            if 'Contents' not in events_response:
                print(f"❌ No event files found in: s3://{bucket_name}/{events_prefix}")
                return False
                
            # Get first event file
            event_key = events_response['Contents'][0]['Key']
            event_obj = s3_client.get_object(Bucket=bucket_name, Key=event_key)
            event_content = event_obj['Body'].read().decode('utf-8')
            print(f"✅ Found event file: s3://{bucket_name}/{event_key}")
            
            # Create combined output like runMaki.py does
            combined_output = {
                "Summary": json.loads(summary_content),
                "Event_Example": json.loads(event_content)
            }
            
        else:  # OnDemand processing
            # Handle ondemand processing
            response = s3_client.list_objects_v2(
                Bucket=bucket_name,
                Prefix='ondemand/',
                Delimiter='/'
            )
            
            if 'CommonPrefixes' not in response:
                print("❌ No ondemand directories found")
                return False
                
            # Get the latest ondemand directory
            ondemand_dirs = [prefix['Prefix'] for prefix in response['CommonPrefixes']]
            latest_ondemand = sorted(ondemand_dirs)[-1]
            
            # Check for summary.json
            summary_key = f"{latest_ondemand}summary.json"
            try:
                summary_obj = s3_client.get_object(Bucket=bucket_name, Key=summary_key)
                summary_content = summary_obj['Body'].read().decode('utf-8')
                print(f"✅ Found summary: s3://{bucket_name}/{summary_key}")
                
                # Validate summary JSON
                try:
                    summary_json = json.loads(summary_content)
                except json.JSONDecodeError as e:
                    print(f"❌ Invalid JSON in summary file: {e}")
                    return False
                    
            except:
                print(f"❌ Summary not found: s3://{bucket_name}/{summary_key}")
                return False
                
            # Check for event files in the same directory
            events_response = s3_client.list_objects_v2(
                Bucket=bucket_name,
                Prefix=latest_ondemand,
                MaxKeys=100
            )
            
            event_content = None
            event_json = None
            if 'Contents' in events_response:
                for obj in events_response['Contents']:
                    key = obj['Key']
                    if (key.endswith('.json') and 
                        ('case-gen-' in key) and 
                        'summary.json' not in key):
                        event_obj = s3_client.get_object(Bucket=bucket_name, Key=key)
                        event_content = event_obj['Body'].read().decode('utf-8')
                        print(f"✅ Found event file: s3://{bucket_name}/{key}")
                        
                        # Validate event JSON
                        try:
                            event_json = json.loads(event_content)
                        except json.JSONDecodeError as e:
                            print(f"❌ Invalid JSON in event file: {e}")
                            return False
                        break
            
            # Create combined output like runMaki.py does
            if event_json:
                combined_output = {
                    "Summary": summary_json,
                    "Event_Example": event_json
                }
            else:
                combined_output = {
                    "Summary": summary_json,
                    "Event_Example": "No individual event files found"
                }
        
        # Validate against expected output
        combined_json = json.dumps(combined_output, indent=2)
        if match_output(combined_json, expected_output):
            print("✅ S3 files match expected pattern")
            return True
        else:
            print("❌ S3 files do not match expected pattern")
            show_diff(expected_output, combined_json)
            return False
            
    except Exception as e:
        print(f"❌ Error checking S3 files: {e}")
        return False

def show_diff(expected, actual):
    """Show differences between expected and actual output with red highlighting"""
    import difflib
    
    # ANSI color codes
    RED = '\033[91m'
    GREEN = '\033[92m'
    RESET = '\033[0m'
    
    expected_lines = expected.splitlines()
    actual_lines = actual.splitlines()
    
    diff = list(difflib.unified_diff(expected_lines, actual_lines, 
                                   fromfile='Expected', tofile='Actual', lineterm=''))
    
    print(f"\nDifferences (- expected, + actual):")
    for line in diff:
        if line.startswith('---') or line.startswith('+++') or line.startswith('@@'):
            print(line)
        elif line.startswith('-'):
            print(f"{RED}{line}{RESET}")
        elif line.startswith('+'):
            print(f"{GREEN}{line}{RESET}")
        else:
            print(line)

def match_output(actual, expected):
    """Check if actual output matches expected pattern with * wildcards and JSON structure comparison"""
    import re
    
    # Try JSON structure comparison first
    try:
        actual_json = json.loads(actual)
        expected_json = json.loads(expected)
        return match_json_structure(actual_json, expected_json)
    except (json.JSONDecodeError, ValueError):
        # Fall back to regex pattern matching for non-JSON content
        pattern = re.escape(expected).replace(r'\*', '.*')
        return re.search(pattern, actual, re.DOTALL) is not None

def match_json_structure(actual, expected):
    """Recursively compare JSON structures, treating * as wildcards"""
    if expected == "*":
        return True
    
    if type(actual) != type(expected):
        return False
    
    if isinstance(expected, dict):
        for key, expected_value in expected.items():
            if key not in actual:
                return False
            if not match_json_structure(actual[key], expected_value):
                return False
        return True
    
    elif isinstance(expected, list):
        if len(actual) != len(expected):
            return False
        for actual_item, expected_item in zip(actual, expected):
            if not match_json_structure(actual_item, expected_item):
                return False
        return True
    
    else:
        return expected == "*" or actual == expected

def run_command(cmd, description, expected_output=None, check_files_only=False):
    """Run a command and handle errors with timer"""
    print(f"\n=== {description} ===")
    
    # Print expected output if provided
    if expected_output:
        print(f"Expected Output:\n{expected_output}\n")
    
    if check_files_only:
        if expected_output:
            return check_s3_files(description, expected_output)
        else:
            print("✅ No output validation needed")
            return True
    
    print(f"Executing: {cmd}")
    
    # Suppress output for CDK synth commands
    suppress_output = "cdk synth" in cmd
    
    # Special handling for runMaki.py to show step function progress
    if "runMaki.py" in cmd:
        return run_maki_with_progress(cmd, description, expected_output)
    
    # Timer setup
    start_time = time.time()
    timer_running = True
    
    def show_timer():
        while timer_running:
            elapsed = time.time() - start_time
            print(f"\rElapsed: {elapsed:.1f}s", end='', flush=True)
            time.sleep(10)  # Update every 10 seconds
    
    timer_thread = threading.Thread(target=show_timer)
    timer_thread.daemon = True
    timer_thread.start()
    
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        timer_running = False
        elapsed = time.time() - start_time
        
        if suppress_output:
            print(f"\rCompleted in {elapsed:.1f}s (output suppressed)")
        else:
            print(f"\rCompleted in {elapsed:.1f}s")
            if result.stdout:
                print(result.stdout)
        
        # Check expected output if provided
        if expected_output and result.stdout:
            if match_output(result.stdout, expected_output):
                print("✅ Output matches expected pattern")
            else:
                print("❌ Output does not match expected pattern")
                show_diff(expected_output, result.stdout)
                return False
        
        return True
    except subprocess.CalledProcessError as e:
        timer_running = False
        elapsed = time.time() - start_time
        print(f"\rFailed after {elapsed:.1f}s")
        print(f"ERROR: Command failed with exit code {e.returncode}")
        if e.stdout:
            print(f"STDOUT: {e.stdout}")
        if e.stderr:
            print(f"STDERR: {e.stderr}")
        return False

def run_maki_with_progress(cmd, description, expected_output):
    """Run runMaki.py with step function progress monitoring"""
    start_time = time.time()
    timer_running = True
    
    def show_timer():
        while timer_running:
            elapsed = time.time() - start_time
            print(f"\rElapsed: {elapsed:.1f}s", end='', flush=True)
            time.sleep(10)  # Update every 10 seconds
    
    timer_thread = threading.Thread(target=show_timer)
    timer_thread.daemon = True
    timer_thread.start()
    
    try:
        # Run the command and capture output line by line
        process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, 
                                 stderr=subprocess.STDOUT, text=True, bufsize=1)
        
        output_lines = []
        for line in iter(process.stdout.readline, ''):
            line = line.rstrip()
            output_lines.append(line)
            
            # Show step function progress
            if '"Step Name":' in line:
                step_name = line.split('"Step Name": "')[1].split('"')[0]
                print(f"🔄 Running step: {step_name}")
            elif "⏱️  Total:" in line:
                # Skip printing Total: lines from runMaki.py
                continue
            elif line.strip():
                print(line)
        
        process.wait()
        timer_running = False
        elapsed = time.time() - start_time
        
        if process.returncode == 0:
            print(f"\rCompleted in {elapsed:.1f}s")
            
            # Check expected output if provided
            full_output = '\n'.join(output_lines)
            if expected_output:
                if match_output(full_output, expected_output):
                    print("✅ Output matches expected pattern")
                else:
                    print("❌ Output does not match expected pattern")
                    show_diff(expected_output, full_output)
                    return False
            
            return True
        else:
            print(f"\rFailed after {elapsed:.1f}s with exit code {process.returncode}")
            return False
            
    except Exception as e:
        timer_running = False
        elapsed = time.time() - start_time
        print(f"\rFailed after {elapsed:.1f}s with error: {e}")
        return False

def parse_test_plan(test_plan_path='test_plan.md', test_case_filter=None):
    """Parse commands from test plan file"""
    commands = []
    
    # Handle relative path - if test_plan.md is specified without directory,
    # look for it in the same directory as this script
    if not os.path.dirname(test_plan_path):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        test_plan_path = os.path.join(script_dir, test_plan_path)
    
    with open(test_plan_path, 'r') as f:
        content = f.read()
    
    # Remove HTML comments
    import re
    content = re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL)
    
    # Remove Usage section
    content = re.sub(r'## Usage.*?## End Usage', '', content, flags=re.DOTALL)
    
    lines = content.strip().split('\n')
    current_section = ""
    current_test_num = None
    i = 0
    
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith('## '):
            current_section = line[3:]
            # Extract test number if present
            test_match = re.match(r'Test (\d+):', current_section)
            current_test_num = int(test_match.group(1)) if test_match else None
        elif line and not line.startswith('#'):
            # Only add command if no filter or matches filter
            if test_case_filter is None or current_test_num == test_case_filter:
                # Check if next non-empty line is ### OUTPUT
                expected_output = None
                j = i + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                if j < len(lines) and lines[j].strip() == '### OUTPUT':
                    # Found output section, collect it
                    output_lines = []
                    j += 1
                    while j < len(lines) and lines[j].strip() != '### END OUTPUT':
                        output_lines.append(lines[j])
                        j += 1
                    if j < len(lines):  # Found ### END OUTPUT
                        expected_output = '\n'.join(output_lines).strip()
                        i = j  # Skip to after ### END OUTPUT
                
                commands.append((line, current_section, expected_output))
        i += 1
    
    return commands

def main():
    parser = argparse.ArgumentParser(description="Execute MAKI Test Plan")
    parser.add_argument("-check-files-only", "-c", action="store_true",
                       help="Only check S3 files against expected output, skip command execution")
    parser.add_argument("--test-case", type=int, choices=range(1, 8),
                       help="Run only the specified test case (1-7)")
    parser.add_argument("--test-plan", type=str, default="test_plan.md",
                       help="Path to the test plan file (default: test_plan.md in same directory as script)")
    args = parser.parse_args()
    
    print("Starting MAKI Test Plan Execution")
    if args.check_files_only:
        print("CHECK-FILES-ONLY MODE: Commands will not be executed, only S3 files checked")
    if args.test_case:
        print(f"SINGLE TEST MODE: Running only Test {args.test_case}")
    
    # Get the script directory and project root
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    
    # Change to repository base directory
    os.chdir(project_root)
    print(f"Changed to directory: {os.getcwd()}")
    
    # Parse test plan
    commands = parse_test_plan(args.test_plan, args.test_case)
    
    if not commands:
        if args.test_case:
            print(f"No commands found for Test {args.test_case}")
        else:
            print("No commands found in test plan")
        sys.exit(1)
    
    # Execute each command
    for cmd, section, expected_output in commands:
        if not run_command(cmd, section, expected_output, args.check_files_only):
            print(f"Failed at: {cmd}")
            sys.exit(1)
    
    print("\n=== Test Plan Execution Complete ===")
    if args.test_case:
        print(f"Test {args.test_case} completed successfully")

if __name__ == "__main__":
    main()
