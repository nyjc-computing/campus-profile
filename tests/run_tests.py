"""Test runner for campus-profile tests."""
import sys
import unittest

if __name__ == "__main__":
    # Discover and run all tests in the tests directory
    loader = unittest.TestLoader()
    start_dir = "."
    suite = loader.discover(start_dir, pattern="test_*.py")

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Exit with non-zero code if tests failed
    sys.exit(0 if result.wasSuccessful() else 1)
