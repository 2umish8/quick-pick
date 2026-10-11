#!/usr/bin/env python3
"""Security regression tests for MOW-187 (proxy SSRF, redirects, local hardening)."""
import json
import os
import shutil
import socket
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

import classifier_proxy
import server


def _clean_env(extra=None):
    """Patch environ with test values, dropping proxy security vars first."""
    env = {
        "QUICK_PICK_ALLOW_PRIVATE_ENDPOINTS": None,
        "QUICK_PICK_CLASSIFIER_ALLOWED_HOSTS": None,
        "QUICK_PICK_ALLOWED_HOSTS": None,
        "QUICK_PICK_TOKEN": None,
    }
    env.update(extra or {})
    # None values cannot go into patch.dict: pop them inside the context.
    set_vars = {k: v for k, v in env.items() if v is not None}
    unset_vars = [k for k, v in env.items() if v is None]
    return set_vars, unset_vars


class _EnvMixin:
    def patch_env(self, **kwargs):
        set_vars, _ = _clean_env()
        patcher = mock.patch.dict(os.environ, set_vars, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        for key in _clean_env()[1]:
            os.environ.pop(key, None)
        for key, value in kwargs.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class ProxySafeUrlTests(unittest.TestCase, _EnvMixin):
    def test_private_loopback_rejected_by_default(self):
        self.patch_env()
        for url in ("http://127.0.0.1:11434/v1", "http://10.0.0.5/"):
            ok, _msg = classifier_proxy.is_safe_url(url)
            self.assertFalse(ok, url)
            with self.assertRaises(ValueError, msg=url):
                classifier_proxy.query_external_classifier(url, "", {"ping": True})

    def test_private_loopback_allowed_with_opt_in(self):
        self.patch_env(QUICK_PICK_ALLOW_PRIVATE_ENDPOINTS="1")
        for url in ("http://127.0.0.1:11434/v1", "http://10.0.0.5/"):
            ok, _msg = classifier_proxy.is_safe_url(url)
            self.assertTrue(ok, url)

    def test_link_local_always_rejected_even_with_opt_in(self):
        self.patch_env(QUICK_PICK_ALLOW_PRIVATE_ENDPOINTS="1")
        ok, _msg = classifier_proxy.is_safe_url("http://169.254.169.254/")
        self.assertFalse(ok)
        with self.assertRaises(ValueError):
            classifier_proxy.query_external_classifier(
                "http://169.254.169.254/", "", {"ping": True})

    def test_ipv4_mapped_loopback_rejected(self):
        self.patch_env()
        ok, _msg = classifier_proxy.is_safe_url("http://[::ffff:127.0.0.1]/")
        self.assertFalse(ok)

    def test_classifier_allowlist_rejects_non_listed_host(self):
        self.patch_env(QUICK_PICK_CLASSIFIER_ALLOWED_HOSTS="api.openai.com")
        ok, _msg = classifier_proxy.is_safe_url("http://example.com/api")
        self.assertFalse(ok)

    def test_metadata_ips_always_rejected_even_with_opt_in(self):
        self.patch_env(QUICK_PICK_ALLOW_PRIVATE_ENDPOINTS="1")
        for url in ("http://100.100.100.200/", "http://[fd00:ec2::254]/",
                    "http://[::ffff:100.100.100.200]/"):
            ok, _msg = classifier_proxy.is_safe_url(url)
            self.assertFalse(ok, url)
            with self.assertRaises(ValueError, msg=url):
                classifier_proxy.query_external_classifier(url, "", {"ping": True})

    def test_metadata_ips_via_hostname_rejected_with_opt_in(self):
        self.patch_env(QUICK_PICK_ALLOW_PRIVATE_ENDPOINTS="1")
        cases = [
            [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("100.100.100.200", 80))],
            [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("fd00:ec2::254", 80, 0, 0))],
            [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::ffff:100.100.100.200", 80, 0, 0))],
        ]
        for addr_info in cases:
            with mock.patch("socket.getaddrinfo", return_value=addr_info):
                ok, _msg = classifier_proxy.is_safe_url("http://example.com/api")
                self.assertFalse(ok, addr_info)
                with self.assertRaises(ValueError, msg=str(addr_info)):
                    classifier_proxy.query_external_classifier(
                        "http://example.com/api", "", {"ping": True})


class _SilentHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass


class RedirectTargetHandler(_SilentHandler):
    hits = 0

    def _record(self):
        type(self).hits += 1
        body = b'{"ok": true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._record()

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        self._record()


class RedirectSourceHandler(_SilentHandler):
    target_url = ""

    def _redirect(self):
        self.send_response(302)
        self.send_header("Location", type(self).target_url)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        self._redirect()

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        self._redirect()


class ProxyRedirectTests(unittest.TestCase, _EnvMixin):
    def setUp(self):
        self.patch_env(QUICK_PICK_ALLOW_PRIVATE_ENDPOINTS="1")
        RedirectTargetHandler.hits = 0
        self.target = ThreadingHTTPServer(("127.0.0.1", 0), RedirectTargetHandler)
        self.source = ThreadingHTTPServer(("127.0.0.1", 0), RedirectSourceHandler)
        RedirectSourceHandler.target_url = (
            f"http://127.0.0.1:{self.target.server_address[1]}/")
        self.threads = []
        for srv in (self.target, self.source):
            thread = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05})
            thread.daemon = True
            thread.start()
            self.threads.append(thread)
        self.addCleanup(self.source.shutdown)
        self.addCleanup(self.target.shutdown)
        self.addCleanup(self.source.server_close)
        self.addCleanup(self.target.server_close)

    def test_redirect_is_not_followed(self):
        url = f"http://127.0.0.1:{self.source.server_address[1]}/classify"
        code, res = classifier_proxy.query_external_classifier(url, "", {"ping": True})
        self.assertEqual(RedirectTargetHandler.hits, 0)
        self.assertEqual(code, 302)
        self.assertIn("error", res)


class ProxyRebindingTests(unittest.TestCase, _EnvMixin):
    PUBLIC_IP = "93.184.216.34"

    def _addr_info(self, ip):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 80))]

    def test_single_resolution_and_pinned_connection(self):
        self.patch_env()
        recorded = []

        def fake_create_connection(address, timeout=None, source_address=None):
            recorded.append(address)
            raise ConnectionRefusedError("boom")

        with mock.patch("socket.getaddrinfo",
                         return_value=self._addr_info(self.PUBLIC_IP)) as gai, \
             mock.patch("socket.create_connection",
                        side_effect=fake_create_connection):
            code, _res = classifier_proxy.query_external_classifier(
                "http://example.com/api", "", {"ping": True})
            self.assertEqual(code, 500)
            self.assertEqual(gai.call_count, 1)
            self.assertEqual(recorded, [(self.PUBLIC_IP, 80)])

    def test_second_resolution_would_be_detected(self):
        self.patch_env()
        gai = mock.Mock(side_effect=[
            self._addr_info(self.PUBLIC_IP),
            self._addr_info("127.0.0.1"),
        ])
        recorded = []

        def fake_create_connection(address, timeout=None, source_address=None):
            recorded.append(address)
            raise ConnectionRefusedError("boom")

        with mock.patch("socket.getaddrinfo", gai), \
             mock.patch("socket.create_connection", side_effect=fake_create_connection):
            classifier_proxy.query_external_classifier(
                "http://example.com/api", "", {"ping": True})
            self.assertEqual(gai.call_count, 1)
            for address in recorded:
                self.assertNotEqual(address[0], "127.0.0.1")

    def test_mixed_public_and_private_addresses_rejected(self):
        self.patch_env()
        mixed = self._addr_info(self.PUBLIC_IP) + self._addr_info("10.0.0.5")
        with mock.patch("socket.getaddrinfo", return_value=mixed):
            with self.assertRaises(ValueError):
                classifier_proxy.query_external_classifier(
                    "http://example.com/api", "", {"ping": True})

    def test_fallback_through_validated_ips(self):
        self.patch_env()
        ipv6 = "2606:2800:220:1:248:1893:25c8:1946"
        ipv4 = self.PUBLIC_IP
        addr_info = [
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", (ipv6, 80, 0, 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (ipv4, 80)),
        ]
        recorded = []

        def fake_create_connection(address, timeout=None, source_address=None):
            recorded.append(address)
            if address[0] == ipv6:
                raise OSError("first address down")
            raise ConnectionRefusedError("boom")

        with mock.patch("socket.getaddrinfo", return_value=addr_info) as gai, \
                mock.patch("socket.create_connection", side_effect=fake_create_connection):
            code, _res = classifier_proxy.query_external_classifier(
                "http://example.com/api", "", {"ping": True})
            self.assertEqual(code, 500)
            self.assertEqual(gai.call_count, 1)
            self.assertEqual(recorded, [(ipv6, 80), (ipv4, 80)])


def _raw_request(port, method, path, headers, body=b""):
    """Send a raw HTTP request with full control over Host/Origin headers."""
    sock = socket.create_connection(("127.0.0.1", port), timeout=5)
    try:
        all_headers = dict(headers)
        all_headers.setdefault("Connection", "close")
        all_headers["Content-Length"] = str(len(body))
        head = "\r\n".join(
            [f"{method} {path} HTTP/1.1"]
            + [f"{name}: {value}" for name, value in all_headers.items()]
        ) + "\r\n\r\n"
        sock.sendall(head.encode("latin-1") + body)
        data = b""
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            data += chunk
    finally:
        sock.close()
    head, _, tail = data.partition(b"\r\n\r\n")
    status = int(head.split(b"\r\n")[0].split()[1])
    try:
        payload = json.loads(tail.decode("utf-8"))
    except ValueError:
        payload = {}
    return status, payload


class LocalServerTests(unittest.TestCase, _EnvMixin):
    def setUp(self):
        self.patch_env()
        self.temp_dir = tempfile.mkdtemp()
        self.decks_dir = os.path.join(self.temp_dir, "decks")
        os.makedirs(self.decks_dir, exist_ok=True)
        self.original_decks_dir = server.DECKS_DIR
        server.DECKS_DIR = self.decks_dir
        deck = {
            "id": "sec-deck",
            "title": "Security deck",
            "default_actions": [
                {"id": "approve", "label": "Keep", "direction": "east", "key": "d", "color": "success"},
                {"id": "reject", "label": "Drop", "direction": "west", "key": "a", "color": "danger"},
            ],
            "items": [{"id": "item-1", "title": "Item one", "status": "pending",
                       "chosen_action": None, "decided_at": None}],
        }
        with open(os.path.join(self.decks_dir, "sec-deck.json"), "w", encoding="utf-8") as handle:
            json.dump(deck, handle)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.QuickPickHandler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(
            target=self.httpd.serve_forever, kwargs={"poll_interval": 0.05})
        self.thread.daemon = True
        self.thread.start()
        self.addCleanup(self.httpd.shutdown)
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(shutil.rmtree, self.temp_dir, True)
        self.addCleanup(setattr, server, "DECKS_DIR", self.original_decks_dir)

    def _post(self, path, headers, body):
        return _raw_request(self.port, "POST", path, headers, body)

    def test_post_wrong_content_type_rejected(self):
        status, payload = self._post(
            "/api/decks/sec-deck/decide",
            {"Host": "127.0.0.1", "Content-Type": "text/plain"},
            b"hello")
        self.assertEqual(status, 415)
        self.assertEqual(payload.get("error"), "unsupported_media_type")

    def test_post_evil_host_rejected(self):
        status, payload = self._post(
            "/api/decks/sec-deck/decide",
            {"Host": "evil.example", "Content-Type": "application/json"},
            b"{}")
        self.assertEqual(status, 403)
        self.assertEqual(payload.get("error"), "forbidden_host")

    def test_post_evil_origin_rejected(self):
        status, payload = self._post(
            "/api/decks/sec-deck/decide",
            {"Host": "localhost", "Content-Type": "application/json",
             "Origin": "http://evil.example"},
            b"{}")
        self.assertEqual(status, 403)
        self.assertEqual(payload.get("error"), "forbidden_origin")

    def test_valid_json_post_with_localhost_works(self):
        body = json.dumps({"item_id": "item-1", "action": "approve"}).encode("utf-8")
        status, _payload = self._post(
            "/api/decks/sec-deck/decide",
            {"Host": "localhost", "Content-Type": "application/json; charset=utf-8"},
            body)
        self.assertNotIn(status, (403, 415))
        self.assertEqual(status, 200)


class TokenAuthTests(unittest.TestCase, _EnvMixin):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.decks_dir = os.path.join(self.temp_dir, "decks")
        os.makedirs(self.decks_dir, exist_ok=True)
        self.original_decks_dir = server.DECKS_DIR
        server.DECKS_DIR = self.decks_dir
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.QuickPickHandler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(
            target=self.httpd.serve_forever, kwargs={"poll_interval": 0.05})
        self.thread.daemon = True
        self.thread.start()
        self.addCleanup(self.httpd.shutdown)
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(shutil.rmtree, self.temp_dir, True)
        self.addCleanup(setattr, server, "DECKS_DIR", self.original_decks_dir)

    def test_api_requires_token_and_static_stays_open(self):
        self.patch_env(QUICK_PICK_TOKEN="s3cret")
        status, payload = _raw_request(
            self.port, "GET", "/api/decks", {"Host": "127.0.0.1"}, b"")
        self.assertEqual(status, 401)
        self.assertEqual(payload.get("error"), "unauthorized")

        status, _payload = _raw_request(
            self.port, "GET", "/api/decks",
            {"Host": "127.0.0.1", "Authorization": "Bearer s3cret"}, b"")
        self.assertEqual(status, 200)

        status, _payload = _raw_request(
            self.port, "GET", "/", {"Host": "127.0.0.1"}, b"")
        self.assertEqual(status, 200)

    def test_check_bind_config(self):
        with self.assertRaises(ValueError):
            server.check_bind_config("0.0.0.0", "")
        self.assertTrue(server.check_bind_config("0.0.0.0", "x"))
        self.assertTrue(server.check_bind_config("127.0.0.1", ""))
        self.assertTrue(server.check_bind_config("::1", ""))


class PinnedHTTPSTests(unittest.TestCase):
    def test_pinned_https_uses_ip_but_sni_hostname(self):
        import ssl as ssl_module

        conn = classifier_proxy._PinnedHTTPSConnection(
            "example.com", 443, pinned_ip="93.184.216.34")
        conn._context = None
        fake_sock = object()
        fake_ctx = mock.Mock()
        with mock.patch("socket.create_connection",
                         return_value=fake_sock) as creator, \
             mock.patch("ssl.create_default_context",
                        return_value=fake_ctx) as factory:
            conn.connect()
            creator.assert_called_once_with(
                ("93.184.216.34", 443), conn.timeout, conn.source_address)
            factory.assert_called_once_with()
            fake_ctx.wrap_socket.assert_called_once_with(
                fake_sock, server_hostname="example.com")
        # Default context must verify hostnames.
        self.assertTrue(ssl_module.create_default_context().check_hostname)

    def test_token_redacted_in_logs(self):
        import io
        handler = server.QuickPickHandler.__new__(server.QuickPickHandler)
        captured = io.StringIO()
        with mock.patch("sys.stderr", captured):
            handler.log_message(
                '"GET /api/decks?token=s3cret-value HTTP/1.1" 200 -')
        out = captured.getvalue()
        self.assertNotIn("s3cret-value", out)
        self.assertIn("token=***", out)

    def test_origin_must_match_request_host(self):
        f = server.is_allowed_origin
        self.assertTrue(f("http://localhost:9000", server_port=8791, host_header="localhost:9000"))
        self.assertTrue(f("https://localhost", server_port=8791, host_header="localhost"))
        self.assertTrue(f("http://[::1]:8791", server_port=8791, host_header="[::1]:8791"))
        self.assertFalse(f("http://localhost:3000", server_port=8791, host_header="localhost:8791"))
        self.assertFalse(f("http://localhost", server_port=8791, host_header="localhost:8791"))
        self.assertFalse(f("http://127.0.0.1:8791", server_port=8791, host_header="localhost:8791"))
        self.assertFalse(f("http://evil.example:8791", server_port=8791, host_header="evil.example:8791"))

    def test_origin_without_port_compared_to_server_port(self):
        self.assertFalse(server.is_allowed_origin(
            "http://localhost", server_port=8791))
        self.assertTrue(server.is_allowed_origin(
            "http://localhost:8791", server_port=8791))
        self.assertTrue(server.is_allowed_origin(
            "http://localhost", server_port=80))
        self.assertTrue(server.is_allowed_origin(
            "https://localhost", server_port=443))
        self.assertFalse(server.is_allowed_origin(
            "https://localhost", server_port=8791))


class PredictRedirectTests(unittest.TestCase, _EnvMixin):
    def setUp(self):
        self.patch_env(QUICK_PICK_ALLOW_PRIVATE_ENDPOINTS="1")
        self.temp_dir = tempfile.mkdtemp()
        self.decks_dir = os.path.join(self.temp_dir, "decks")
        os.makedirs(self.decks_dir, exist_ok=True)
        self.original_decks_dir = server.DECKS_DIR
        server.DECKS_DIR = self.decks_dir
        RedirectTargetHandler.hits = 0
        self.target = ThreadingHTTPServer(("127.0.0.1", 0), RedirectTargetHandler)
        self.source = ThreadingHTTPServer(("127.0.0.1", 0), RedirectSourceHandler)
        RedirectSourceHandler.target_url = (
            f"http://127.0.0.1:{self.target.server_address[1]}/")
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.QuickPickHandler)
        self.port = self.httpd.server_address[1]
        self.servers = (self.target, self.source, self.httpd)
        self.threads = []
        for srv in self.servers:
            thread = threading.Thread(
                target=srv.serve_forever, kwargs={"poll_interval": 0.05})
            thread.daemon = True
            thread.start()
            self.threads.append(thread)
        for srv in self.servers:
            self.addCleanup(srv.shutdown)
        for srv in self.servers:
            self.addCleanup(srv.server_close)
        self.addCleanup(shutil.rmtree, self.temp_dir, True)
        self.addCleanup(setattr, server, "DECKS_DIR", self.original_decks_dir)

    def test_predict_redirect_yields_ok_false(self):
        endpoint = f"http://127.0.0.1:{self.source.server_address[1]}/classify"
        body = json.dumps(
            {"endpoint": endpoint, "api_key": "",
             "payload": {"ping": True}}).encode("utf-8")
        status, payload = _raw_request(
            self.port, "POST", "/api/classifier/predict",
            {"Host": "127.0.0.1", "Content-Type": "application/json"}, body)
        self.assertEqual(RedirectTargetHandler.hits, 0)
        self.assertEqual(status, 502)
        self.assertFalse(payload.get("ok"))
        self.assertEqual(payload.get("status"), 302)


class FrontendRegressionTests(unittest.TestCase):
    def _public(self, name):
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(base, "public", name), encoding="utf-8") as handle:
            return handle.read()

    def test_api_token_in_fragment_not_query(self):
        src = self._public("api.js")
        self.assertNotIn("location.search", src)
        self.assertIn("sessionStorage", src)

    def test_app_dock_escapes_deck_data(self):
        src = self._public("app.js")
        self.assertIn("escapeHtml(act.id)", src)
        self.assertIn("escapeHtml(act.color", src)


if __name__ == "__main__":
    unittest.main()


class FrontendImportGuardTests(unittest.TestCase):
    """Regression guard: helpers used in classifier.js must be imported."""

    def test_classifier_js_imports_used_api_helpers(self):
        import re
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "public", "classifier.js"), encoding="utf-8") as fh:
            src = fh.read()
        match = re.search(r'import\s*\{([^}]*)\}\s*from\s*"\./api\.js"', src)
        self.assertIsNotNone(match)
        imported = {name.strip() for name in match.group(1).split(",")}
        for helper in ("authFetch", "authHeaders"):
            if helper + "(" in src:
                self.assertIn(helper, imported)

