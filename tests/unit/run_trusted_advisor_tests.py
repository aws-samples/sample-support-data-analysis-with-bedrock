#!/usr/bin/env python3
"""
Test runner for Trusted Advisor functionality in MAKI

This script runs all Trusted Advisor related tests including:
- Lambda handler tests
- Standalone tool tests
- Infrastructure validation tests
"""

import unittest
import sys
import os

def run_trusted_advisor_tests():
    """Run all Trusted Advisor tests"""
    
    # Discover and run tests
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add Trusted Advisor handler tests
    from test_trusted_advisor import TestTrustedAdvisorHandlers
    suite.addTests(loader.loadTestsFromTestCase(TestTrustedAdvisorHandlers))
    
    # Add Trusted Advisor tool tests
    from test_trusted_advisor_tool import TestTrustedAdvisorTool
    suite.addTests(loader.loadTestsFromTestCase(TestTrustedAdvisorTool))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Return success status
    return result.wasSuccessful()

if __name__ == '__main__':
    success = run_trusted_advisor_tests()
    sys.exit(0 if success else 1)