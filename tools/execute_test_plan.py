#!/usr/bin/env python3

import subprocess
import sys
import os
import time
import threading
import argparse
import boto3
import json

def check_s3_files(section, expected_output):
    """Check S3 files for batch processing"""
    if "Test Cases / Batch" not in section:
        return True
        
    # Get AWS account and region
    sts_client = boto3.client("sts")
    account_id = sts_client.get_caller_identity()["Account"]
    region = boto3.session.Session().region_name
    
    s3_client = boto3.client('s3')
    bucket_name = f'maki-{account_id}-{region}-report'
    
    try:
        # List batch directories
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
    """Check if actual output matches expected pattern with * wildcards"""
    import re
    # Escape special regex chars except *
    pattern = re.escape(expected).replace(r'\*', '.*')
    return re.search(pattern, actual, re.DOTALL) is not None

def run_command(cmd, description, expected_output=None, check_files_only=False):
    """Run a command and handle errors with timer"""
    print(f"\n=== {description} ===")
    
    if check_files_only:
        if expected_output:
            return check_s3_files(description, expected_output)
        else:
            print("✅ No output validation needed")
            return True
    
    print(f"Executing: {cmd}")
    
    # Suppress output for CDK synth commands
    suppress_output = "cdk synth" in cmd
    
    # Timer setup
    start_time = time.time()
    timer_running = True
    
    def show_timer():
        while timer_running:
            elapsed = time.time() - start_time
            print(f"Elapsed: {elapsed:.1f}s")
            time.sleep(5)  # Update every 5 seconds
    
    timer_thread = threading.Thread(target=show_timer)
    timer_thread.daemon = True
    timer_thread.start()
    
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        timer_running = False
        elapsed = time.time() - start_time
        
        if suppress_output:
            print(f"Completed in {elapsed:.1f}s (output suppressed)")
        else:
            print(f"Completed in {elapsed:.1f}s")
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
        print(f"Failed after {elapsed:.1f}s")
        print(f"ERROR: Command failed with exit code {e.returncode}")
        if e.stdout:
            print(f"STDOUT: {e.stdout}")
        if e.stderr:
            print(f"STDERR: {e.stderr}")
        return False

def parse_test_plan():
    """Parse commands from test_plan.md"""
    commands = []
    
    with open('tools/test_plan.md', 'r') as f:
        content = f.read()
    
    # Remove HTML comments
    import re
    content = re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL)
    
    # Remove Usage section
    content = re.sub(r'## Usage.*?## End Usage', '', content, flags=re.DOTALL)
    
    lines = content.strip().split('\n')
    current_section = ""
    i = 0
    
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith('## '):
            current_section = line[3:]
        elif line and not line.startswith('#'):
            commands.append((line, current_section, None))
        elif line == '### OUTPUT':
            # Associate output with the last command
            if commands:
                output_lines = []
                i += 1
                while i < len(lines) and lines[i].strip() != '### END OUTPUT':
                    output_lines.append(lines[i])
                    i += 1
                if i < len(lines):  # Found ### END OUTPUT
                    expected_output = '\n'.join(output_lines).strip()
                    # Update the last command with expected output
                    last_cmd, last_section, _ = commands[-1]
                    commands[-1] = (last_cmd, last_section, expected_output)
        i += 1
    
    return commands

def main():
    parser = argparse.ArgumentParser(description="Execute MAKI Test Plan")
    parser.add_argument("-check-files-only", action="store_true",
                       help="Only check S3 files against expected output, skip command execution")
    args = parser.parse_args()
    
    print("Starting MAKI Test Plan Execution")
    if args.check_files_only:
        print("CHECK-FILES-ONLY MODE: Commands will not be executed, only S3 files checked")
    
    # Get the script directory and project root
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    
    # Change to repository base directory
    os.chdir(project_root)
    print(f"Changed to directory: {os.getcwd()}")
    
    # Parse test plan
    commands = parse_test_plan()
    
    # Execute each command
    for cmd, section, expected_output in commands:
        if not run_command(cmd, section, expected_output, args.check_files_only):
            print(f"Failed at: {cmd}")
            sys.exit(1)
    
    print("\n=== Test Plan Execution Complete ===")

if __name__ == "__main__":
    main()
