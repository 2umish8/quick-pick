#!/usr/bin/env python3
"""Frontend regression tests for public/api.js, run under Node when available."""
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_JS = os.path.join(ROOT, "public", "api.js")
NODE = shutil.which("node")

PRELUDE = """
const store = () => { const m = new Map(); return {
  getItem: k => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)),
  removeItem: k => m.delete(k) }; };
globalThis.sessionStorage = store();
globalThis.localStorage = store();
globalThis.__replaced = [];
globalThis.history = { replaceState: (a, b, u) => globalThis.__replaced.push(u) };
"""


@unittest.skipUnless(NODE, "node not installed")
class FrontendNodeTests(unittest.TestCase):
    def run_node(self, body):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        script = os.path.join(tmp, "t.mjs")
        with open(script, "w", encoding="utf-8") as fh:
            fh.write(PRELUDE + body.replace("__API__", "file://" + API_JS))
        proc = subprocess.run([NODE, script], capture_output=True, text=True, timeout=20)
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        return proc.stdout.strip()

    def test_malformed_fragment_token_is_still_stripped(self):
        out = self.run_node("""
globalThis.location = { hash: "#deck-a&token=%zz", href: "http://localhost:8791/?q=1#deck-a&token=%zz" };
await import("__API__");
if (globalThis.__replaced.length !== 1) throw new Error("replaceState not called");
if (globalThis.__replaced[0].includes("token")) throw new Error("token left in URL: " + globalThis.__replaced[0]);
if (globalThis.__replaced[0] !== "http://localhost:8791/?q=1#deck-a") throw new Error(globalThis.__replaced[0]);
if (sessionStorage.getItem("quickPickToken") !== null) throw new Error("malformed token stored");
console.log("ok");
""")
        self.assertEqual(out, "ok")

    def test_retry_after_401_prompt_sends_new_token(self):
        out = self.run_node("""
globalThis.location = { hash: "#token=OLD", href: "http://localhost:8791/#token=OLD" };
const seen = [];
globalThis.window = { prompt: () => "NEW" };
const reply = (status, obj) => ({ status, ok: status < 400,
  headers: { get: () => "application/json" },
  json: async () => obj, clone() { return this; }, text: async () => JSON.stringify(obj) });
globalThis.fetch = async (url, opts) => {
  seen.push(opts.headers.Authorization);
  return seen.length === 1 ? reply(401, { error: "unauthorized" }) : reply(200, { ok: true });
};
const api = await import("__API__");
// request() with caller headers that include a stale Authorization.
await api.request("/api/decks", { headers: { Authorization: "Bearer STALE" } });
if (seen.join(",") !== "Bearer OLD,Bearer NEW") throw new Error("request: " + seen.join(","));
seen.length = 0;
sessionStorage.setItem("quickPickToken", "OLD");
await api.authFetch("/api/classifier/test", { method: "POST",
  headers: { "Content-Type": "application/json", Authorization: "Bearer STALE" }, body: "{}" });
if (seen.join(",") !== "Bearer OLD,Bearer NEW") throw new Error("authFetch: " + seen.join(","));
console.log("ok");
""")
        self.assertEqual(out, "ok")


if __name__ == "__main__":
    unittest.main()
