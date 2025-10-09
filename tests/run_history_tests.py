#!/usr/bin/env python3
"""
Test runner for history handling system tests.

This script runs all tests for the history handling system and provides
a summary of results.

Usage:
    python tests/run_history_tests.py

    or with python.exe on Windows WSL:
    python.exe tests/run_history_tests.py
"""

import sys
import unittest
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src' / 'shared'))

# Import test modules
from test_history_handling import (
    TestCommentParsing,
    TestConfidenceDistribution,
    TestValidationRecordSheet,
    TestHistoryExtraction,
    TestPromptGeneration,
    OPENPYXL_AVAILABLE
)

from test_validation_record import (
    TestPreviewValidation,
    TestFullValidation,
    TestMultipleValidations,
    TestConfidenceTracking
)


def run_all_tests(verbose=2):
    """Run all history handling tests"""
    print("=" * 70)
    print("HISTORY HANDLING SYSTEM TEST SUITE")
    print("=" * 70)
    print()

    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add test classes
    print("[INFO] Loading test classes...")

    # History handling tests
    suite.addTests(loader.loadTestsFromTestCase(TestCommentParsing))
    suite.addTests(loader.loadTestsFromTestCase(TestConfidenceDistribution))
    suite.addTests(loader.loadTestsFromTestCase(TestValidationRecordSheet))

    if OPENPYXL_AVAILABLE:
        suite.addTests(loader.loadTestsFromTestCase(TestHistoryExtraction))
        print("[SUCCESS] openpyxl is available - Excel tests will run")
    else:
        print("[WARNING] openpyxl not available - some Excel tests will be skipped")

    suite.addTests(loader.loadTestsFromTestCase(TestPromptGeneration))

    # Validation record tests
    suite.addTests(loader.loadTestsFromTestCase(TestPreviewValidation))
    suite.addTests(loader.loadTestsFromTestCase(TestFullValidation))
    suite.addTests(loader.loadTestsFromTestCase(TestMultipleValidations))
    suite.addTests(loader.loadTestsFromTestCase(TestConfidenceTracking))

    print(f"[INFO] Loaded {suite.countTestCases()} tests")
    print()

    # Run tests
    print("=" * 70)
    print("RUNNING TESTS")
    print("=" * 70)
    print()

    runner = unittest.TextTestRunner(verbosity=verbose)
    result = runner.run(suite)

    # Print summary
    print()
    print("=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"Tests run: {result.testsRun}")
    print(f"Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Skipped: {len(result.skipped)}")
    print()

    if result.wasSuccessful():
        print("[SUCCESS] All tests passed!")
        return 0
    else:
        print("[FAILURE] Some tests failed!")
        if result.failures:
            print("\nFailed tests:")
            for test, traceback in result.failures:
                print(f"  - {test}")
        if result.errors:
            print("\nTests with errors:")
            for test, traceback in result.errors:
                print(f"  - {test}")
        return 1


def main():
    """Main entry point"""
    # Check for verbose flag
    verbose = 2 if '-v' in sys.argv or '--verbose' in sys.argv else 1

    # Run tests
    exit_code = run_all_tests(verbose=verbose)

    # Exit with appropriate code
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
