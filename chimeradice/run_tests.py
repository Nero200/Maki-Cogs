#!/usr/bin/env python3
"""
Test runner for ChimeraDice cog tests.

This script runs both unit tests and property-based tests for the ChimeraDice cog.
"""

import sys
import unittest
import os

# Add current directory and tests directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tests'))

def run_tests():
    """Run all tests for the ChimeraDice cog."""
    
    print("=" * 60)
    print("ChimeraDice Cog Test Suite")
    print("=" * 60)
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Load unit tests
    try:
        from test_chimeradice import (
            TestChimeraDice, 
            TestAdvancedOperations, 
            TestAsyncMethods
        )
        
        suite.addTests(loader.loadTestsFromTestCase(TestChimeraDice))
        suite.addTests(loader.loadTestsFromTestCase(TestAdvancedOperations))
        suite.addTests(loader.loadTestsFromTestCase(TestAsyncMethods))
        
        print("✓ Loaded unit tests")
        
    except ImportError as e:
        print(f"✗ Failed to load unit tests: {e}")
        return False
    
    # Load property-based tests if hypothesis is available
    try:
        from test_chimeradice_properties import (
            TestChimeraDiceProperties,
            TestDiceStateMachine,
            TestPercentileConsistency
        )
        
        suite.addTests(loader.loadTestsFromTestCase(TestChimeraDiceProperties))
        suite.addTests(loader.loadTestsFromTestCase(TestDiceStateMachine))
        suite.addTests(loader.loadTestsFromTestCase(TestPercentileConsistency))
        
        print("✓ Loaded property-based tests")
        
    except ImportError as e:
        print(f"! Property-based tests not available: {e}")
        print("  Install hypothesis for property-based testing: pip install hypothesis")
    
    # Run the tests
    print("\nRunning tests...")
    print("-" * 40)
    
    runner = unittest.TextTestRunner(
        verbosity=2,
        stream=sys.stdout,
        descriptions=True
    )
    
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    total_tests = result.testsRun
    failures = len(result.failures)
    errors = len(result.errors)
    skipped = len(result.skipped) if hasattr(result, 'skipped') else 0
    
    print(f"Total tests run: {total_tests}")
    print(f"Failures: {failures}")
    print(f"Errors: {errors}")
    print(f"Skipped: {skipped}")
    print(f"Success rate: {((total_tests - failures - errors) / total_tests * 100):.1f}%" if total_tests > 0 else "N/A")
    
    if result.wasSuccessful():
        print("\n🎉 All tests passed!")
        return True
    else:
        print("\n❌ Some tests failed!")
        
        if result.failures:
            print("\nFailures:")
            for test, traceback in result.failures:
                print(f"  - {test}: {traceback.split('AssertionError:')[-1].strip()}")
        
        if result.errors:
            print("\nErrors:")
            for test, traceback in result.errors:
                print(f"  - {test}: {traceback.split('Exception:')[-1].strip()}")
        
        return False


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)