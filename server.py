#!/usr/bin/env python3
"""quick-pick — Serveur HTTP & API de décision (SOLID / SRP)."""
import hmac
import ipaddress
import json, os, re, sys, threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
import deck_store
from deck_store import DeckError, find_deck_state, list_available_decks, load_deck, save_deck, resolve_item_actions
from deck_summary import compute_deck_summary

BIND_HOST = os.environ.get("QUICK_PICK_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("QUICK_PICK_PORT", "8791"))
QUICK_PICK_TOKEN = os.environ.get("QUICK_PICK_TOKEN", "")
PUBLIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public")
STATE_LOCK = threading.Lock()
MAX_BODY_SIZE = 2 * 1024 * 1024  # 2 Mo

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
_WILDCARD_HOSTS = {"", "0.0.0.0", "::"}


def get_effective_token():
    """Return the configured API token (env first, module fallback)."""
    env = os.environ.get("QUICK_PICK_TOKEN")
    if env is not None:
        return env
    return QUICK_PICK_TOKEN or ""


def _is_loopback_host(host):
    """Return True for loopback bind addresses (127.0.0.0/8, ::1, localhost)."""
    if (host or "").strip().lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address((host or "").strip()).is_loopback
    except ValueError:
        return False


def check_bind_config(host, token):
    """Validate that a non-loopback bind has a token. Raise ValueError if not."""
    if _is_loopback_host(host):
        return True
    if token:
        return True
    raise ValueError(
        f"Refusing to listen on non-loopback address '{host}' without QUICK_PICK_TOKEN set")


def is_token_authorized(headers, token=None):
    """Check the request carries the configured API token. Testable helper."""
    expected = token if token is not None else get_effective_token()
    if not expected:
        return True
    if headers is None:
        return False
    provided = None
    auth = headers.get("Authorization")
    if auth and auth.strip().lower().startswith("bearer "):
        provided = auth.strip()[7:].strip()
    elif headers.get("X-Quick-Pick-Token"):
        provided = headers.get("X-Quick-Pick-Token").strip()
    if provided is None:
        return False
    return hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


def _parse_extra_hosts():
    raw = os.environ.get("QUICK_PICK_ALLOWED_HOSTS", "")
    return {h.strip().lower() for h in raw.split(",") if h.strip()}


def _strip_host_port(host_header):
    """Strip the port from a Host header, handling [::1]:port brackets."""
    value = (host_header or "").strip()
    if not value:
        return ""
    if value.startswith("["):
        end = value.find("]")
        if end == -1:
            return ""
        return value[1:end].strip().lower()
    # Bare IPv6 without port contains multiple colons: keep as-is.
    if value.count(":") > 1:
        return value.lower()
    return value.split(":")[0].strip().lower()


def get_allowed_hosts(bind_host=None, extra=None):
    """Return the set of allowed Host/Origin hostnames (lowercase)."""
    allowed = set(_LOCAL_HOSTS)
    if extra:
        allowed.update(h.lower() for h in extra)
    bind = bind_host if bind_host is not None else BIND_HOST
    if bind and bind.strip().lower() not in _WILDCARD_HOSTS:
        allowed.add(bind.strip().lower())
    return allowed


def is_allowed_host(host_header, extra=None, bind_host=None):
    """Check a Host header against the allowlist. Testable helper."""
    host = _strip_host_port(host_header)
    if not host:
        return False
    if extra is None:
        extra = _parse_extra_hosts()
    return host in get_allowed_hosts(bind_host=bind_host, extra=extra)


def is_allowed_origin(origin, allowed_hosts=None, server_port=None, host_header=None):
    """Check an Origin header. Missing header is allowed; 'null' is rejected.

    When host_header is given, the Origin must be same-origin with the request
    Host (hostname and port, scheme default port when absent). This keeps
    reverse proxies and remapped Docker ports working. Otherwise the Origin
    port is compared to server_port.
    """
    if origin is None or origin == "":
        return True
    if origin.strip().lower() == "null":
        return False
    try:
        parsed = urlparse(origin.strip())
    except Exception:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    allowed = allowed_hosts if allowed_hosts is not None else get_allowed_hosts(
        extra=_parse_extra_hosts())
    if host not in allowed:
        return False
    try:
        origin_port = parsed.port
    except ValueError:
        return False
    if origin_port is None:
        origin_port = 443 if parsed.scheme == "https" else 80
    if host_header:
        req_host = _strip_host_port(host_header)
        value = host_header.strip()
        tail = value[value.find("]") + 1:] if value.startswith("[") else (
            "" if value.count(":") > 1 else value)
        req_port = None
        if ":" in tail:
            try:
                req_port = int(tail.rsplit(":", 1)[1])
            except ValueError:
                return False
        if req_port is None:
            req_port = 443 if parsed.scheme == "https" else 80
        return host == req_host and origin_port == req_port
    if server_port is not None and origin_port != server_port:
        return False
    return True


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


from classifier_proxy import query_external_classifier, test_external_classifier


class QuickPickHandler(BaseHTTPRequestHandler):
    server_version = "quick-pick/2"

    def log_message(self, fmt, *args):
        line = fmt % args if args else fmt
        line = re.sub(r"token=[^&\s\"']*", "token=***", line)
        print(f"[quick-pick] {line}", file=sys.stderr, flush=True)

    def _set_security_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")

    def send_json(self, status, payload, head_only=False):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._set_security_headers()
        self.end_headers()
        if not head_only:
            self.wfile.write(body)

    def serve_static(self, filename, head_only=False):
        safe = filename.lstrip("/") or "index.html"
        if ".." in safe or safe.startswith("/"):
            return self.send_json(400, {"error": "bad_path"}, head_only=head_only)
        disk_path = os.path.realpath(os.path.join(PUBLIC_DIR, safe))
        if not disk_path.startswith(os.path.realpath(PUBLIC_DIR)):
            return self.send_json(400, {"error": "bad_path"}, head_only=head_only)
        if safe == "favicon.ico" and not os.path.isfile(disk_path):
            safe = "favicon.svg"
            disk_path = os.path.join(PUBLIC_DIR, safe)
        if not os.path.isfile(disk_path):
            return self.send_json(404, {"error": "not_found"}, head_only=head_only)
        ctypes = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".svg": "image/svg+xml",
            ".ico": "image/x-icon",
            ".png": "image/png",
        }
        ctype = ctypes.get(os.path.splitext(safe)[1].lower(), "text/plain; charset=utf-8")
        with open(disk_path, "rb") as h:
            body = h.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self._set_security_headers()
        self.end_headers()
        if not head_only:
            self.wfile.write(body)

    def read_json_body(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY_SIZE:
                return None, {"error": "payload_too_large", "detail": f"Max {MAX_BODY_SIZE} octets"}
            payload = json.loads((self.rfile.read(length) if length else b"{}").decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError) as err:
            return None, {"error": "invalid_json", "detail": str(err)}
        # A JSON array/scalar/string is syntactically valid but unusable: callers read payload as an object.
        if not isinstance(payload, dict):
            return None, {"error": "invalid_json", "detail": "Le corps JSON doit être un objet"}
        return payload, None

    def do_HEAD(self): self.do_GET(head_only=True)

    def _deny(self, status, error, head_only=False):
        return self.send_json(status, {"error": error}, head_only=head_only)

    def _check_host(self, head_only=False):
        if not is_allowed_host(self.headers.get("Host")):
            self._deny(403, "forbidden_host", head_only=head_only)
            return False
        return True

    def _check_api_auth(self, path, head_only=False):
        if path.startswith("/api/") and not is_token_authorized(self.headers):
            self._deny(401, "unauthorized", head_only=head_only)
            return False
        return True

    def _check_origin(self, path, head_only=False):
        if self.command == "POST" or path.startswith("/api/"):
            origin = self.headers.get("Origin")
            if origin is not None:
                try:
                    server_port = self.server.server_address[1]
                except Exception:
                    server_port = None
                if not is_allowed_origin(origin, server_port=server_port,
                                         host_header=self.headers.get("Host")):
                    self._deny(403, "forbidden_origin", head_only=head_only)
                    return False
        return True

    def _check_post_content_type(self, head_only=False):
        media = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if media != "application/json":
            self._deny(415, "unsupported_media_type", head_only=head_only)
            return False
        return True

    def do_GET(self, head_only=False):
        path = urlparse(self.path).path
        if not self._check_host(head_only=head_only): return
        if not self._check_api_auth(path, head_only=head_only): return
        if not self._check_origin(path, head_only=head_only): return
        if path in ("/", "/index.html"): return self.serve_static("index.html", head_only=head_only)
        if path == "/api/health": return self.send_json(200, {"ok": True, "time": utc_now_iso()}, head_only=head_only)
        if path == "/api/decks": return self.send_json(200, {"decks": list_available_decks()}, head_only=head_only)
        if path.startswith("/api/decks/"):
            p = [x for x in path.split("/") if x]
            if len(p) == 3:
                try:
                    with STATE_LOCK: return self.send_json(200, find_deck_state(load_deck(p[2])), head_only=head_only)
                except DeckError as err: return self.send_json(404, {"error": str(err)}, head_only=head_only)
            if len(p) == 4 and p[3] == "summary":
                try:
                    with STATE_LOCK: return self.send_json(200, compute_deck_summary(load_deck(p[2])), head_only=head_only)
                except DeckError as err: return self.send_json(404, {"error": str(err)}, head_only=head_only)
        return self.serve_static(path, head_only=head_only)

    def do_POST(self):
        raw_path = urlparse(self.path).path
        if not self._check_host(): return
        if not self._check_api_auth(raw_path): return
        if not self._check_origin(raw_path): return
        if not self._check_post_content_type(): return
        p = [x for x in raw_path.split("/") if x]
        payload, body_err = self.read_json_body()
        if body_err: return self.send_json(400, body_err)

        if len(p) >= 3 and p[0] == "api" and p[1] == "classifier":
            action = p[2]
            if action == "test":
                try:
                    code, reachable, msg = test_external_classifier(payload.get("endpoint"), payload.get("api_key"))
                    return self.send_json(200, {"ok": reachable, "status": code, "message": msg})
                except Exception as err:
                    return self.send_json(400, {"ok": False, "error": str(err)})
            elif action == "predict":
                try:
                    code, res = query_external_classifier(payload.get("endpoint"), payload.get("api_key"), payload.get("payload") or {})
                    ok = code < 300
                    status = 200 if ok else (502 if 300 <= code < 400 else code)
                    return self.send_json(status, {"ok": ok, "status": code, "data": res})
                except Exception as err:
                    return self.send_json(400, {"ok": False, "error": str(err)})
            return self.send_json(404, {"error": "action_inconnue"})

        if len(p) < 4 or p[0] != "api" or p[1] != "decks": return self.send_json(404, {"error": "not_found"})
        deck_id, action = p[2], p[3]

        with STATE_LOCK:
            try: deck = load_deck(deck_id)
            except DeckError as err: return self.send_json(404, {"error": str(err)})
            items = deck.get("items", [])
            if action == "decide":
                item_id, act_id = payload.get("item_id"), payload.get("action")
                target = next((it for it in items if it.get("id") == item_id), None)
                if not target: return self.send_json(404, {"error": "item_not_found"})
                valid = [a.get("id") for a in resolve_item_actions(deck.get("default_actions", []), target)]
                if act_id not in valid: return self.send_json(400, {"error": "invalid_action", "valid": valid})
                raw_c = payload.get("comment")
                clean_c = raw_c.strip() if isinstance(raw_c, str) and raw_c.strip() else None
                target.update({"status": "decided", "chosen_action": act_id, "decided_at": utc_now_iso(), "comment": clean_c})
            elif action == "undo":
                target_id = payload.get("item_id")
                decided = [it for it in items if it.get("status") == "decided"]
                if not decided: return self.send_json(409, {"error": "no_decision_to_undo"})
                if target_id:
                    target = next((it for it in decided if it.get("id") == target_id), None)
                    if not target: return self.send_json(404, {"error": "item_not_found"})
                    target.update({"status": "pending", "chosen_action": None, "decided_at": None, "comment": None})
                else:
                    decided.sort(key=lambda it: it.get("decided_at") or "", reverse=True)
                    decided[0].update({"status": "pending", "chosen_action": None, "decided_at": None, "comment": None})
            elif action == "skip":
                idx = next((i for i, it in enumerate(items) if it.get("id") == payload.get("item_id")), None)
                if idx is None: return self.send_json(404, {"error": "item_not_found"})
                items.append(items.pop(idx))
            else: return self.send_json(404, {"error": f"action_inconnue_{action}"})
            save_deck(deck_id, deck)
            return self.send_json(200, {"ok": True, **find_deck_state(deck)})


def set_decks_dir(path):
    deck_store.set_decks_dir(path)


class _ModuleSync(sys.modules[__name__].__class__):
    @property
    def DECKS_DIR(self):
        return deck_store.DECKS_DIR

    @DECKS_DIR.setter
    def DECKS_DIR(self, val):
        deck_store.set_decks_dir(val)


sys.modules[__name__].__class__ = _ModuleSync


def main():
    host = os.environ.get("QUICK_PICK_HOST", BIND_HOST)
    try:
        check_bind_config(host, get_effective_token())
    except ValueError as err:
        print(f"[quick-pick] error: {err}", file=sys.stderr, flush=True)
        sys.exit(2)
    port = int(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("QUICK_PICK_PORT", str(DEFAULT_PORT)))
    deck_store.seed_example_decks()
    server = ThreadingHTTPServer((host, port), QuickPickHandler)
    print(f"[quick-pick] http://{host}:{port} ({deck_store.DECKS_DIR})", flush=True)
    try: server.serve_forever()
    finally: server.server_close()


if __name__ == "__main__": main()
