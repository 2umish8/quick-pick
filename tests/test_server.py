#!/usr/bin/env python3
"""Tests unitaires et de non-régression pour quick-pick server."""
import http.client
import json
import os
import shutil
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from http.server import ThreadingHTTPServer

import deck_store
import server
from deck_store import DeckError, DeckExistsError


class QuickPickServerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.decks_dir = os.path.join(self.temp_dir, "decks")
        os.makedirs(self.decks_dir, exist_ok=True)
        # Patch DECKS_DIR pour isoler les tests
        self.original_decks_dir = server.DECKS_DIR
        server.DECKS_DIR = self.decks_dir

        # Création d'un deck de test
        self.sample_deck = {
            "id": "test-deck",
            "title": "Deck de Test",
            "description": "Validation du moteur",
            "category": "TEST",
            "default_actions": [
                {"id": "reject", "label": "Supprimer", "direction": "west", "key": "a", "color": "danger"},
                {"id": "review", "label": "À revoir", "direction": "north", "key": "s", "color": "warning"},
                {"id": "approve", "label": "Conserver", "direction": "east", "key": "d", "color": "success"}
            ],
            "items": [
                {
                    "id": "item-1",
                    "title": "Premier Item",
                    "badges": [{"label": "P1", "variant": "warning"}],
                    "bullets": ["Point un", "Point deux"],
                    "status": "pending",
                    "chosen_action": None,
                    "decided_at": None
                },
                {
                    "id": "item-2",
                    "title": "Deuxième Item",
                    "badges": [{"label": "P2", "variant": "neutral"}],
                    "bullets": ["Autre point"],
                    "status": "pending",
                    "chosen_action": None,
                    "decided_at": None
                }
            ]
        }
        with open(os.path.join(self.decks_dir, "test-deck.json"), "w", encoding="utf-8") as f:
            json.dump(self.sample_deck, f)

    def tearDown(self):
        server.DECKS_DIR = self.original_decks_dir
        shutil.rmtree(self.temp_dir)

    def test_list_available_decks_has_no_stress_counters(self):
        decks = server.list_available_decks()
        self.assertEqual(len(decks), 1)
        deck = decks[0]
        self.assertEqual(deck["id"], "test-deck")
        self.assertEqual(deck["title"], "Deck de Test")
        # Vérification stricte : aucun compteur anxiogène
        self.assertNotIn("total", deck)
        self.assertNotIn("remaining", deck)
        self.assertNotIn("count", deck)
        self.assertNotIn("progress", deck)

    def test_find_deck_state_and_actions_resolution(self):
        deck = server.load_deck("test-deck")
        state = server.find_deck_state(deck)
        self.assertFalse(state["is_completed"])
        self.assertTrue(state["has_next"])
        self.assertFalse(state["has_third"])
        self.assertEqual(state["current_item"]["id"], "item-1")
        self.assertEqual(len(state["current_item"]["actions"]), 3)

    def test_decide_and_undo_flow(self):
        deck = server.load_deck("test-deck")
        # 1. Décider sur item-1
        item_1 = deck["items"][0]
        item_1["status"] = "decided"
        item_1["chosen_action"] = "approve"
        item_1["decided_at"] = server.utc_now_iso()
        server.save_deck("test-deck", deck)

        # Vérifier l'état
        deck_reloaded = server.load_deck("test-deck")
        state = server.find_deck_state(deck_reloaded)
        self.assertEqual(state["current_item"]["id"], "item-2")
        self.assertFalse(state["has_next"])
        self.assertTrue(state["can_undo"])

        # 2. Undo
        items = deck_reloaded["items"]
        last_item = [i for i in items if i["status"] == "decided"][0]
        last_item["status"] = "pending"
        last_item["chosen_action"] = None
        last_item["decided_at"] = None
        server.save_deck("test-deck", deck_reloaded)

        deck_after_undo = server.load_deck("test-deck")
        state_after_undo = server.find_deck_state(deck_after_undo)
        self.assertEqual(state_after_undo["current_item"]["id"], "item-1")
        self.assertTrue(state_after_undo["has_next"])

    def test_summary_only_reveals_stats_at_completion(self):
        deck = server.load_deck("test-deck")
        for item in deck["items"]:
            item["status"] = "decided"
            item["chosen_action"] = "approve"
            item["decided_at"] = server.utc_now_iso()
        server.save_deck("test-deck", deck)

        summary = server.compute_deck_summary(deck)
        self.assertEqual(summary["total_decided"], 2)
        self.assertEqual(summary["actions_breakdown"]["approve"], 2)

    def test_stack_items_and_decided_pending_lists(self):
        deck = server.load_deck("test-deck")
        state = server.find_deck_state(deck)
        self.assertEqual(len(state["upcoming_items"]), 1)
        self.assertEqual(state["upcoming_items"][0]["id"], "item-2")
        self.assertEqual(len(state["pending_items"]), 2)
        self.assertEqual(len(state["decided_items"]), 0)

        # Simuler une décision
        deck["items"][0]["status"] = "decided"
        deck["items"][0]["chosen_action"] = "approve"
        deck["items"][0]["decided_at"] = server.utc_now_iso()
        server.save_deck("test-deck", deck)

        state2 = server.find_deck_state(deck)
        self.assertEqual(len(state2["pending_items"]), 1)
        self.assertEqual(len(state2["decided_items"]), 1)
        self.assertEqual(state2["decided_items"][0]["chosen_action"], "approve")

    def test_decision_with_comment_and_guidelines(self):
        deck = server.load_deck("test-deck")
        deck["guidelines"] = "Consigne de tri stricte"
        item = deck["items"][0]
        item["status"] = "decided"
        item["chosen_action"] = "reject"
        item["comment"] = "Trop verbeux"
        item["decided_at"] = server.utc_now_iso()
        server.save_deck("test-deck", deck)

        state = server.find_deck_state(server.load_deck("test-deck"))
        self.assertEqual(state["guidelines"], "Consigne de tri stricte")
        self.assertEqual(state["decided_items"][0]["comment"], "Trop verbeux")

        summary = server.compute_deck_summary(server.load_deck("test-deck"))
        self.assertEqual(summary["entries"][0]["comment"], "Trop verbeux")

    def test_recommended_action_resolution(self):
        deck = server.load_deck("test-deck")
        deck["items"][0]["recommended_action"] = "review"
        state = server.find_deck_state(deck)
        self.assertEqual(state["current_item"]["recommended_action"], "review")

    def test_skip_item_moves_to_bottom(self):
        deck = server.load_deck("test-deck")
        first_id = deck["items"][0]["id"]
        # Simuler un skip sur item-1
        idx = next((i for i, it in enumerate(deck["items"]) if it.get("id") == first_id), None)
        deck["items"].append(deck["items"].pop(idx))
        server.save_deck("test-deck", deck)

        state = server.find_deck_state(server.load_deck("test-deck"))
        self.assertEqual(state["current_item"]["id"], "item-2")
        self.assertEqual(deck["items"][-1]["id"], first_id)

    def test_targeted_undo_flow(self):
        deck = server.load_deck("test-deck")
        # Décider item-1 puis item-2
        deck["items"][0].update({"status": "decided", "chosen_action": "approve", "decided_at": "2026-10-11T12:00:00+00:00"})
        deck["items"][1].update({"status": "decided", "chosen_action": "reject", "decided_at": "2026-10-11T12:01:00+00:00"})
        server.save_deck("test-deck", deck)

        # Undo ciblé sur item-1 (au lieu du dernier item-2)
        decided = [it for it in deck["items"] if it.get("status") == "decided"]
        target = next((it for it in decided if it.get("id") == "item-1"), None)
        target.update({"status": "pending", "chosen_action": None, "decided_at": None, "comment": None})
        server.save_deck("test-deck", deck)

        reloaded = server.load_deck("test-deck")
        item_1 = next(it for it in reloaded["items"] if it["id"] == "item-1")
        item_2 = next(it for it in reloaded["items"] if it["id"] == "item-2")
        self.assertEqual(item_1["status"], "pending")
        self.assertEqual(item_2["status"], "decided")

    def test_summary_single_item_duration_and_breakdown(self):
        deck = server.load_deck("test-deck")
        # Un seul item décidé
        deck["items"][0].update({"status": "decided", "chosen_action": "approve", "decided_at": server.utc_now_iso()})
        server.save_deck("test-deck", deck)

        summary = server.compute_deck_summary(deck)
        self.assertEqual(summary["total_decided"], 1)
        self.assertEqual(summary["total_items"], 2)
        self.assertEqual(summary["pending_count"], 1)
        self.assertFalse(summary["is_completed"])
        self.assertGreaterEqual(summary["elapsed_seconds"], 1)

    def test_classifier_proxy_invalid_endpoint(self):
        import classifier_proxy
        with self.assertRaises(ValueError):
            classifier_proxy.test_external_classifier("invalid-url", "token")
        with self.assertRaises(ValueError):
            classifier_proxy.query_external_classifier("ftp://invalid", "token", {})

    def test_classifier_proxy_ssrf_metadata_blocked(self):
        import classifier_proxy
        with self.assertRaises(ValueError):
            classifier_proxy.test_external_classifier("http://169.254.169.254/latest/meta-data", "")
        with self.assertRaises(ValueError):
            classifier_proxy.query_external_classifier("http://169.254.169.254/secret", "", {})

    def test_deck_id_regex_security(self):
        from deck_store import DeckError, resolve_deck_path
        with self.assertRaises(DeckError):
            resolve_deck_path("../traversal")
        with self.assertRaises(DeckError):
            resolve_deck_path("deck/with/slash")
        with self.assertRaises(DeckError):
            resolve_deck_path("deck with spaces")
        # Valid ID
        path = resolve_deck_path("valid-deck_123")
        self.assertTrue(path.endswith("valid-deck_123.json"))

    def test_load_deck_rejects_items_without_id_or_title(self):
        from deck_store import DeckError
        invalid_items = [
            [{"title": "Pas d'identifiant"}],
            [{"id": "item-1"}],
            [{"id": "item-1", "title": "   "}],
            [{"id": "item-1", "title": "OK"}, "pas-un-objet"],
            {"id": "item-1"},
        ]
        for index, items in enumerate(invalid_items):
            deck_id = f"broken-{index}"
            with open(os.path.join(self.decks_dir, f"{deck_id}.json"), "w", encoding="utf-8") as handle:
                json.dump({"id": deck_id, "title": "Deck cassé", "items": items}, handle)
            with self.assertRaises(DeckError):
                server.load_deck(deck_id)

    def test_load_deck_keeps_accepting_decks_without_items(self):
        deck_id = "no-items"
        with open(os.path.join(self.decks_dir, f"{deck_id}.json"), "w", encoding="utf-8") as handle:
            json.dump({"id": deck_id, "title": "Deck vide", "default_actions": []}, handle)
        self.assertEqual(server.find_deck_state(server.load_deck(deck_id))["is_completed"], True)

    def test_summary_ignores_naive_unparsable_and_non_string_timestamps(self):
        deck = server.load_deck("test-deck")
        decided_at = [
            "2026-10-11T12:00:00",             # naive, assumed UTC
            "2026-10-11T12:00:30+00:00",       # aware
            "pas-une-date",                     # unparsable, ignored
            1752288030,                          # non-string, ignored
        ]
        for item, stamp in zip(deck["items"], decided_at):
            item.update({"status": "decided", "chosen_action": "approve", "decided_at": stamp})

        summary = server.compute_deck_summary(deck)
        self.assertEqual(summary["total_decided"], 2)
        self.assertEqual(summary["elapsed_seconds"], 30)

    def test_summary_with_a_single_valid_timestamp(self):
        deck = server.load_deck("test-deck")
        deck["items"][0].update({"status": "decided", "chosen_action": "approve", "decided_at": "2026-10-11T12:00:00"})
        deck["items"][1].update({"status": "decided", "chosen_action": "approve", "decided_at": "pas-une-date"})
        summary = server.compute_deck_summary(deck)
        self.assertEqual(summary["elapsed_seconds"], 1)


class QuickPickHttpTests(unittest.TestCase):
    """End-to-end checks against a real server instance (no mocked handlers)."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.decks_dir = os.path.join(self.temp_dir, "decks")
        os.makedirs(self.decks_dir, exist_ok=True)
        self.original_decks_dir = server.DECKS_DIR
        server.DECKS_DIR = self.decks_dir
        with open(os.path.join(self.decks_dir, "test-deck.json"), "w", encoding="utf-8") as handle:
            json.dump({
                "id": "test-deck",
                "title": "Deck de Test",
                "default_actions": [{"id": "approve", "label": "Conserver", "direction": "east", "key": "d", "color": "success"}],
                "items": [{"id": "item-1", "title": "Premier Item", "status": "pending"}],
            }, handle)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.QuickPickHandler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)
        server.DECKS_DIR = self.original_decks_dir
        shutil.rmtree(self.temp_dir)

    def _request(self, method, path, body=None):
        conn = HTTPConnection("127.0.0.1", self.httpd.server_address[1], timeout=10)
        try:
            conn.request(method, path, body=body, headers={"Content-Type": "application/json"})
            response = conn.getresponse()
            raw = response.read().decode("utf-8")
            return response.status, (json.loads(raw) if raw else {})
        finally:
            conn.close()

    def test_non_object_json_body_returns_400(self):
        for body in ("[]", '"chaine"', "42", "null", "true"):
            status, payload = self._request("POST", "/api/decks/test-deck/decide", body)
            self.assertEqual(status, 400, f"body={body} payload={payload}")
            self.assertEqual(payload["error"], "invalid_json")

    def test_malformed_json_body_still_returns_400(self):
        status, payload = self._request("POST", "/api/decks/test-deck/decide", "{not json")
        self.assertEqual(status, 400)
        self.assertEqual(payload["error"], "invalid_json")

    def test_valid_object_body_still_works(self):
        status, payload = self._request("POST", "/api/decks/test-deck/decide", '{"item_id": "item-1", "action": "approve"}')
        self.assertEqual(status, 200)
        self.assertEqual(payload["decided_count"], 1)

    def test_deck_with_invalid_items_returns_4xx_not_500(self):
        with open(os.path.join(self.decks_dir, "broken-deck.json"), "w", encoding="utf-8") as handle:
            json.dump({"id": "broken-deck", "title": "Deck cassé", "items": [{"title": "Pas d'identifiant"}]}, handle)
        for path in ("/api/decks/broken-deck", "/api/decks/broken-deck/summary"):
            status, payload = self._request("GET", path)
            self.assertEqual(status, 404, f"{path} -> {payload}")
        status, payload = self._request("POST", "/api/decks/broken-deck/decide", '{"item_id": "item-1"}')
        self.assertEqual(status, 404)

    def test_classifier_routes_also_reject_non_object_body(self):
        status, payload = self._request("POST", "/api/classifier/predict", "[]")
        self.assertEqual(status, 400)
        self.assertEqual(payload["error"], "invalid_json")


class SecurityHeaderTests(unittest.TestCase):
    """Security headers served on static pages and on the API."""

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
            response.read()
            return response
        finally:
            conn.close()

    def test_csp_and_permissions_policy_on_every_response(self):
        for path in ("/", "/index.html", "/api/health", "/api/unknown-route"):
            with self.subTest(path=path):
                response = self.get(path)
                csp = response.getheader("Content-Security-Policy") or ""
                permissions = response.getheader("Permissions-Policy") or ""
                self.assertIn("default-src 'self'", csp)
                self.assertIn("script-src 'self'", csp)
                self.assertIn("style-src 'self'", csp)
                self.assertIn("object-src 'none'", csp)
                self.assertIn("frame-ancestors 'none'", csp)
                self.assertNotIn("unsafe-inline", csp)
                self.assertNotIn("unsafe-eval", csp)
                self.assertIn("camera=()", permissions)
                self.assertIn("geolocation=()", permissions)
                self.assertIn("microphone=()", permissions)
                # Historical headers stay in place.
                self.assertEqual(response.getheader("X-Content-Type-Options"), "nosniff")
                self.assertEqual(response.getheader("X-Frame-Options"), "DENY")

    def test_connect_src_covers_direct_mode_and_accepts_extra_origins(self):
        csp = server.build_content_security_policy()
        self.assertIn("connect-src 'self' https://api.openai.com", csp)
        with patch.dict(os.environ, {"QUICK_PICK_CSP_CONNECT_SRC": "http://localhost:11434"}):
            csp = server.build_content_security_policy()
        self.assertIn("http://localhost:11434", csp)


class DeckCreationTests(unittest.TestCase):
    """Validation pure (deck_store.create_deck), sans HTTP."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.decks_dir = os.path.join(self.temp_dir, "decks")
        os.makedirs(self.decks_dir, exist_ok=True)
        self.original_decks_dir = deck_store.DECKS_DIR
        deck_store.set_decks_dir(self.decks_dir)

    def tearDown(self):
        deck_store.set_decks_dir(self.original_decks_dir)
        shutil.rmtree(self.temp_dir)

    def test_create_deck_builds_persisted_json_deck(self):
        deck = deck_store.create_deck(
            title="  Backlog Q4  ",
            items=["Migrer vers Postgres", "  ", "Supprimer le legacy", ""],
            template="priority",
        )
        self.assertEqual(deck["id"], "backlog-q4")
        self.assertEqual(deck["title"], "Backlog Q4")
        self.assertEqual(deck["category"], "GÉNÉRAL")
        # Lignes vides ignorées, cartes ordonnées et identifiées
        self.assertEqual([it["title"] for it in deck["items"]], ["Migrer vers Postgres", "Supprimer le legacy"])
        self.assertEqual([it["id"] for it in deck["items"]], ["item-1", "item-2"])
        self.assertTrue(all(it["status"] == "pending" and it["chosen_action"] is None for it in deck["items"]))
        # Actions du modèle demandé, cohérentes avec deck_cli
        self.assertEqual(deck["default_actions"], deck_store.ACTION_TEMPLATES["priority"])
        # Persistance réelle sur disque, relisible par le store
        self.assertEqual(deck_store.load_deck("backlog-q4"), deck)

    def test_create_deck_rejects_invalid_input(self):
        cases = [
            {"title": "", "items": ["a"]},
            {"title": "   ", "items": ["a"]},
            {"title": "T" * (deck_store.MAX_DECK_TITLE_LENGTH + 1), "items": ["a"]},
            {"title": "Titre", "items": "pas une liste"},
            {"title": "Titre", "items": []},
            {"title": "Titre", "items": ["  ", ""]},
            {"title": "Titre", "items": ["a" * (deck_store.MAX_ITEM_TITLE_LENGTH + 1)]},
            {"title": "Titre", "items": ["a"] * (deck_store.MAX_DECK_ITEMS + 1)},
            {"title": "Titre", "items": ["a"], "template": "inconnu"},
            {"title": "Titre", "items": ["a"], "deck_id": "../traversal"},
            {"title": "Titre", "items": ["a"], "deck_id": "deck with spaces"},
        ]
        for case in cases:
            with self.subTest(case=case.get("template") or case["items"][:1]), self.assertRaises(DeckError):
                deck_store.create_deck(**case)
        self.assertEqual(os.listdir(self.decks_dir), [])

    def test_create_deck_never_overwrites_existing_deck(self):
        deck_store.create_deck(title="Sprint", items=["a"], deck_id="sprint")
        with self.assertRaises(DeckExistsError):
            deck_store.create_deck(title="Autre sprint", items=["b"], deck_id="sprint")
        self.assertEqual([it["title"] for it in deck_store.load_deck("sprint")["items"]], ["a"])

    def test_create_deck_generates_unique_ids(self):
        self.assertEqual(deck_store.create_deck(title="Revue de PR", items=["a"])["id"], "revue-de-pr")
        self.assertEqual(deck_store.create_deck(title="Revue de PR !", items=["a"])["id"], "revue-de-pr-2")
        self.assertEqual(deck_store.create_deck(title="***", items=["a"])["id"], "deck")


class DeckCreationApiTests(unittest.TestCase):
    """Route POST /api/decks via un vrai serveur HTTP éphémère."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.decks_dir = os.path.join(self.temp_dir, "decks")
        os.makedirs(self.decks_dir, exist_ok=True)
        self.original_decks_dir = deck_store.DECKS_DIR
        deck_store.set_decks_dir(self.decks_dir)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.QuickPickHandler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        deck_store.set_decks_dir(self.original_decks_dir)
        shutil.rmtree(self.temp_dir)

    def post(self, path, payload):
        conn = http.client.HTTPConnection("127.0.0.1", self.httpd.server_address[1], timeout=5)
        try:
            body = json.dumps(payload).encode("utf-8")
            conn.request("POST", path, body=body, headers={"Content-Type": "application/json"})
            response = conn.getresponse()
            return response.status, json.loads(response.read().decode("utf-8") or "{}")
        finally:
            conn.close()

    def test_post_decks_creates_and_returns_playable_state(self):
        status, data = self.post("/api/decks", {
            "title": "Nettoyage deps",
            "template": "binary",
            "items": ["Retirer lodash", "Garder zod"],
        })
        self.assertEqual(status, 201)
        self.assertTrue(data["ok"])
        self.assertEqual(data["deck_id"], "nettoyage-deps")
        # L'état renvoyé est directement jouable par le front
        state = data["deck"]
        self.assertEqual(state["id"], "nettoyage-deps")
        self.assertFalse(state["is_completed"])
        self.assertEqual(state["current_item"]["title"], "Retirer lodash")
        self.assertEqual([a["id"] for a in state["current_item"]["actions"]], ["approve", "reject"])
        self.assertEqual(state["pending_count"], 2)
        # Le deck apparaît dans la liste et l'état est rechargable par l'API
        self.assertEqual([d["id"] for d in deck_store.list_available_decks()], ["nettoyage-deps"])
        self.assertEqual(self.post("/api/decks/nettoyage-deps/undo", {})[0], 409)  # rien à annuler

    def test_post_decks_defaults_to_triage_template(self):
        status, data = self.post("/api/decks", {"title": "Audit", "items": ["a"]})
        self.assertEqual(status, 201)
        self.assertEqual(data["deck"]["current_item"]["actions"], deck_store.ACTION_TEMPLATES["triage"])

    def test_post_decks_4xx_on_invalid_input(self):
        for payload in (
            {"items": ["a"]},
            {"title": "Titre", "items": []},
            {"title": "Titre", "items": ["a"], "template": "nope"},
            {"title": "Titre", "items": ["a"], "id": "../evil"},
        ):
            with self.subTest(payload=payload):
                status, body = self.post("/api/decks", payload)
                self.assertEqual(status, 400)
                self.assertTrue(body.get("error"))
        self.assertEqual(os.listdir(self.decks_dir), [])

    def test_post_decks_409_on_existing_id(self):
        self.assertEqual(self.post("/api/decks", {"title": "A", "items": ["x"], "id": "same"})[0], 201)
        status, body = self.post("/api/decks", {"title": "B", "items": ["y"], "id": "same"})
        self.assertEqual(status, 409)
        self.assertIn("existe déjà", body["error"])
        self.assertEqual([it["title"] for it in deck_store.load_deck("same")["items"]], ["x"])


if __name__ == "__main__":
    unittest.main()
