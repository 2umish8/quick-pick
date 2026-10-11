#!/usr/bin/env python3
"""quick-pick — Serveur HTTP & API de décision (SOLID / SRP)."""
import json, os, sys, threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
import deck_store
from deck_store import DeckError, find_deck_state, list_available_decks, load_deck, save_deck, resolve_item_actions
from deck_summary import compute_deck_summary

BIND_HOST = os.environ.get("QUICK_PICK_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("QUICK_PICK_PORT", "8791"))
PUBLIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public")
STATE_LOCK = threading.Lock()
MAX_BODY_SIZE = 2 * 1024 * 1024  # 2 Mo


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


from classifier_proxy import query_external_classifier, test_external_classifier


class QuickPickHandler(BaseHTTPRequestHandler):
    server_version = "quick-pick/2"

    def log_message(self, fmt, *args):
        print(f"[quick-pick] {fmt % args}", file=sys.stderr, flush=True)

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
            return json.loads((self.rfile.read(length) if length else b"{}").decode("utf-8") or "{}"), None
        except (ValueError, UnicodeDecodeError) as err:
            return None, {"error": "invalid_json", "detail": str(err)}

    def do_HEAD(self): self.do_GET(head_only=True)

    def do_GET(self, head_only=False):
        path = urlparse(self.path).path
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
        p = [x for x in urlparse(self.path).path.split("/") if x]
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
                    return self.send_json(200 if code < 400 else code, {"ok": code < 400, "status": code, "data": res})
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
    port = int(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("QUICK_PICK_PORT", str(DEFAULT_PORT)))
    server = ThreadingHTTPServer((BIND_HOST, port), QuickPickHandler)
    print(f"[quick-pick] http://{BIND_HOST}:{port} ({deck_store.DECKS_DIR})", flush=True)
    try: server.serve_forever()
    finally: server.server_close()


if __name__ == "__main__": main()
