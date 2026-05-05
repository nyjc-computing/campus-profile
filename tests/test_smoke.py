"""Smoke tests to verify basic application functionality."""
import unittest


class SmokeTest(unittest.TestCase):
    """Basic smoke tests that verify the application can import and initialize."""

    def test_main_imports(self):
        """Verify that main.py imports without errors."""
        import main

    def test_flask_app_exists(self):
        """Verify that the Flask app is created."""
        import main
        self.assertIsNotNone(main.app)

    def test_routes_defined(self):
        """Verify that expected routes are defined."""
        import main
        rules = [str(rule) for rule in main.app.url_map.iter_rules()]

        # Check for main routes
        self.assertTrue(any("/" in rule for rule in rules))
        self.assertTrue(any("/profile/" in rule for rule in rules))
        self.assertTrue(any("/profile/integrations" in rule for rule in rules))


if __name__ == "__main__":
    unittest.main()
