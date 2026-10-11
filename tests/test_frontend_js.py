#!/usr/bin/env python3
"""Lance les tests front-end Node (aucune dépendance, DOM non requis)."""
import glob
import os
import shutil
import subprocess
import unittest

TESTS_JS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "js")


class FrontendJsTests(unittest.TestCase):
    def test_node_frontend_checks(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        test_files = sorted(glob.glob(os.path.join(TESTS_JS_DIR, "*.test.mjs")))
        self.assertTrue(test_files, "no *.test.mjs found in tests/js")
        result = subprocess.run(
            [node, "--test", *test_files],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            self.fail(f"node --test failed:\n{result.stdout}\n{result.stderr}")


if __name__ == "__main__":
    unittest.main()