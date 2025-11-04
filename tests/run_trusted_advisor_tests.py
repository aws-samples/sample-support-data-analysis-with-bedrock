#!/usr/bin/env python3
"""
Test Runner for MAKI Trusted Advisor Tests

This script runs all Trusted Advisor related tests for the MAKI application.
It includes tests for:
- Trusted Advisor Lambda handlers
- Trusted Advisor data collection tool
- MAKI stack infrastructure tests

Usage:
    python tests/run_trusted_advisor_tests.py
    python tests/run_trusted_advisor_tests.py --verbose
    python tests/run_trusted_advisor_tests.py --specific test_trusted_advisor
"""

import unittest
import sys
import os
import argparse

# Add the project root to the path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

def run_tests(test_pattern=None, verbose=False):
    """Run the test suite"""
    
    # Set up test discovery
    loader = unittest.TestLoader()
    
    if test_pattern:
        # Run specific test pattern
        suite = loader.discover('tests/unit', pattern=f'*{test_pattern}*.py')
    else:
        # Run all tests in the unit directory
        suite = loader.discover('tests/unit', pattern='test_*.py')
    
    # Configure test runner
    verbosity = 2 if verbose else 1
    runner = unittest.TextTestRunner(verbosity=verbosity, buffer=True)
    
    # Run tests
    print("Running MAKI Trusted Advisor Tests...")
    print("=" * 50)
    
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "=" * 50)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Skipped: {len(result.skipped) if hasattr(result, 'skipped') else 0}")
    
    if result.failures:
        print("\nFAILURES:")
        for test, traceback in result.failures:
            print(f"- {test}: {traceback}")
    
    if result.errors:
        print("\nERRORS:")
        for test, traceback in result.errors:
            print(f"- {test}: {traceback}")
    
    # Return success/failure
    return len(result.failures) == 0 and len(result.errors) == 0

def main():
    """Main function"""
    parser = argparse.ArgumentParser(description='Run MAKI Trusted Advisor tests')
    parser.add_argument('--verbose', '-v', action='store_true', 
                       help='Run tests with verbose output')
    parser.add_argument('--specific', '-s', type=str,
                       help='Run specific test pattern (e.g., "trusted_advisor")')
    
    args = parser.parse_args()
    
    # Run tests
    success = run_tests(test_pattern=args.specific, verbose=args.verbose)
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()