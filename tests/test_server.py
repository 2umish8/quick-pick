#!/usr/bin/env python3
"""Tests unitaires et de non-régression pour quick-pick server."""
import json
import os
import shutil
import tempfile
import unittest

import server


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


if __name__ == "__main__":
    unittest.main()
