#!/usr/bin/env python3

import subprocess
import sys
import os
import time
import threading

def match_output(actual, expected):
    """Check if actual output matches expected pattern with * wildcards"""
    import re
    # Escape special regex chars except *
    pattern = re.escape(expected).replace(r'\*', '.*')
    return re.search(pattern, actual, re.DOTALL) is not None

def run_command(cmd, description, expected_output=None):
    """Run a command and handle errors with timer"""
    print(f"\n=== {description} ===")
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
                print(f"Expected pattern: {expected_output}")
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
    print("Starting MAKI Test Plan Execution")
    
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
        if not run_command(cmd, section, expected_output):
            print(f"Failed at: {cmd}")
            sys.exit(1)
    
    print("\n=== Test Plan Execution Complete ===")

if __name__ == "__main__":
    main()
