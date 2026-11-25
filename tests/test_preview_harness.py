"""The committed preview harness stays importable as fixtures evolve."""
import os
import pathlib
import subprocess
import sys
import unittest


class PreviewHarnessTest(unittest.TestCase):
    """tools/run_preview.py imports cleanly (#62)."""

    def test_preview_help_imports_the_harness(self):
        """`--help` imports the script (fixtures, stubs) and exits 0.

        A subprocess keeps the stubbed client out of this test
        process: importing the harness mutates main.client.
        """
        repo_root = pathlib.Path(__file__).resolve().parent.parent
        result = subprocess.run(
            [sys.executable,
             str(repo_root / "tools" / "run_preview.py"), "--help"],
            cwd=repo_root, env=dict(os.environ),
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--port", result.stdout)


if __name__ == "__main__":
    unittest.main()
