#!/usr/bin/env python3
"""Asset versioning: every served CSS/JS URL changes when public/ changes (cache busting)."""
import json
import os
import re
import shutil
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import server


class AssetVersionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.QuickPickHandler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=5)

    def get(self, path):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.request("GET", path)
            response = conn.getresponse()
            return response.status, response.read().decode("utf-8")
        finally:
            conn.close()

    def test_index_references_versioned_assets(self):
        status, html = self.get("/")
        self.assertEqual(status, 200)
        version = server.asset_version()
        self.assertRegex(version, r"^[0-9a-f]{12}$")
        self.assertIn(f'<meta name="quick-pick-version" content="{version}">', html)
        local_refs = re.findall(r'(?:href|src)="(\./[^"]+\.(?:css|js|svg)[^"]*)"', html)
        self.assertTrue(local_refs)
        for ref in local_refs:
            self.assertTrue(ref.endswith(f"?v={version}"), ref)

    def test_module_imports_are_versioned(self):
        version = server.asset_version()
        status, js = self.get(f"/app.js?v={version}")
        self.assertEqual(status, 200)
        imports = re.findall(r'from\s*"(\./[^"]+)"', js)
        self.assertTrue(imports)
        for ref in imports:
            self.assertTrue(ref.endswith(f".js?v={version}"), ref)

    def test_health_reports_version(self):
        status, body = self.get("/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["version"], server.asset_version())

    def test_version_changes_when_a_public_file_changes(self):
        tmp = tempfile.mkdtemp()
        try:
            for name in ("style.css", "app.js"):
                shutil.copy(os.path.join(server.PUBLIC_DIR, name), tmp)
            before = server.asset_version(tmp)
            self.assertEqual(before, server.asset_version(tmp))
            with open(os.path.join(tmp, "style.css"), "a", encoding="utf-8") as fh:
                fh.write("\n/* changed */\n")
            self.assertNotEqual(before, server.asset_version(tmp))
        finally:
            shutil.rmtree(tmp)

    def test_rewrite_leaves_other_content_alone(self):
        js = b'import { a } from "./api.js";\nconst url = "./not-an-import.js";\nimport x from "https://cdn.example/x.js";\n'
        out = server.version_asset_refs(js, ".js", "abc123").decode("utf-8")
        self.assertIn('from "./api.js?v=abc123"', out)
        self.assertIn('"./not-an-import.js"', out)
        self.assertIn('"https://cdn.example/x.js"', out)
        css = b'body { background: url("./bg.svg"); }'
        self.assertEqual(server.version_asset_refs(css, ".css", "abc123"), css)


if __name__ == "__main__":
    unittest.main()
