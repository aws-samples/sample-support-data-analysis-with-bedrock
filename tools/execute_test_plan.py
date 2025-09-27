#!/usr/bin/env python3

import subprocess
import sys
import os
import time
import threading

def run_command(cmd, description):
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
            print(f"\rElapsed: {elapsed:.1f}s", end="", flush=True)
            time.sleep(0.5)
    
    timer_thread = threading.Thread(target=show_timer)
    timer_thread.daemon = True
    timer_thread.start()
    
    try:
        if suppress_output:
            result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
            timer_running = False
            elapsed = time.time() - start_time
            print(f"\rCompleted in {elapsed:.1f}s (output suppressed)")
        else:
            result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
            timer_running = False
            elapsed = time.time() - start_time
            print(f"\rCompleted in {elapsed:.1f}s")
            if result.stdout:
                print(result.stdout)
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
    
    for line in lines:
        line = line.strip()
        if line.startswith('## '):
            current_section = line[3:]
        elif line and not line.startswith('#'):
            commands.append((line, current_section))
    
    return commands

def main():
    print("Starting MAKI Test Plan Execution")
    
    # Change to repository base directory
    os.chdir('..')
    print(f"Changed to directory: {os.getcwd()}")
    
    # Parse test plan
    commands = parse_test_plan()
    
    # Execute each command
    for cmd, section in commands:
        if not run_command(cmd, section):
            print(f"Failed at: {cmd}")
            sys.exit(1)
    
    print("\n=== Test Plan Execution Complete ===")

if __name__ == "__main__":
    main()
