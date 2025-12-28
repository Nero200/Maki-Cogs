#!/usr/bin/env python3
"""
Test runner for ChimeraDice cog tests.

Runs property-based tests from chimeradice_core (no Discord dependencies).
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
    print("ChimeraDice Property Test Suite")
    print("=" * 60)

    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Load property-based tests
    try:
        from test_chimeradice_properties import (
            TestPercentileFunctions,
            TestTranslationFunction,
            TestNormalizeDiceKey,
            TestWeightedRolling,
            TestFudgeDiceGeneration,
            TestValidation,
            TestParseRollAndLabel,
            TestPercentileConsistency,
        )

        suite.addTests(loader.loadTestsFromTestCase(TestPercentileFunctions))
        suite.addTests(loader.loadTestsFromTestCase(TestTranslationFunction))
        suite.addTests(loader.loadTestsFromTestCase(TestNormalizeDiceKey))
        suite.addTests(loader.loadTestsFromTestCase(TestWeightedRolling))
        suite.addTests(loader.loadTestsFromTestCase(TestFudgeDiceGeneration))
        suite.addTests(loader.loadTestsFromTestCase(TestValidation))
        suite.addTests(loader.loadTestsFromTestCase(TestParseRollAndLabel))
        suite.addTests(loader.loadTestsFromTestCase(TestPercentileConsistency))

        print("✓ Loaded property-based tests (8 test classes)")

    except ImportError as e:
        print(f"✗ Failed to load property tests: {e}")
        print("  Make sure hypothesis is installed: pip install hypothesis")
        return False

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
                print(f"  - {test}: {traceback.split('AssertionError:')[-1].strip()[:100]}")

        if result.errors:
            print("\nErrors:")
            for test, traceback in result.errors:
                print(f"  - {test}: {traceback.split('Exception:')[-1].strip()[:100]}")

        return False


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
