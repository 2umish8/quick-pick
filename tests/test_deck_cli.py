#!/usr/bin/env python3
"""Tests unitaires pour deck_cli."""
import io
import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

import deck_cli
import deck_store


class DeckCliTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.decks_dir = os.path.join(self.temp_dir, "decks")
        os.makedirs(self.decks_dir, exist_ok=True)
        self.original_decks_dir = deck_store.DECKS_DIR
        deck_store.set_decks_dir(self.decks_dir)

    def tearDown(self):
        deck_store.set_decks_dir(self.original_decks_dir)
        shutil.rmtree(self.temp_dir)

    def test_build_deck_payload(self):
        items = [{"id": "item-1", "title": "Test Title", "badges": [{"label": "T1", "variant": "success"}]}]
        payload = deck_cli.build_deck_payload(
            "test-deck", "Title", "Desc", "CAT", "binary", items
        )
        self.assertEqual(payload["id"], "test-deck")
        self.assertEqual(len(payload["default_actions"]), 2)
        self.assertEqual(payload["items"][0]["status"], "pending")
        self.assertEqual(payload["items"][0]["chosen_action"], None)

    def test_handle_create_and_load(self):
        items_file = os.path.join(self.temp_dir, "items.json")
        items = [
            {"id": "c1", "title": "Carte 1", "bullets": ["A", "B"]},
            {"id": "c2", "title": "Carte 2", "bullets": ["C"]}
        ]
        with open(items_file, "w", encoding="utf-8") as f:
            json.dump(items, f)

        parser = deck_cli.build_parser()
        args = parser.parse_args([
            "create", "--id", "cli-deck", "--title", "Mon Deck CLI",
            "--category", "TEST", "--template", "triage", "--items-file", items_file
        ])
        with patch("sys.stdout"):
            deck_cli.handle_create(args)

        deck = deck_store.load_deck("cli-deck")
        self.assertEqual(deck["id"], "cli-deck")
        self.assertEqual(len(deck["items"]), 2)

    def test_handle_create_validation_rejects_malformed_items(self):
        parser = deck_cli.build_parser()
        # 1. Tableau vide
        f_empty = os.path.join(self.temp_dir, "empty.json")
        with open(f_empty, "w") as f: json.dump([], f)
        args_empty = parser.parse_args(["create", "--id", "d1", "--title", "T1", "--items-file", f_empty])
        with self.assertRaises(deck_store.DeckError):
            deck_cli.handle_create(args_empty)

        # 2. Item sans id
        f_no_id = os.path.join(self.temp_dir, "no_id.json")
        with open(f_no_id, "w") as f: json.dump([{"title": "Sans ID"}], f)
        args_no_id = parser.parse_args(["create", "--id", "d2", "--title", "T2", "--items-file", f_no_id])
        with self.assertRaises(deck_store.DeckError):
            deck_cli.handle_create(args_no_id)

        # 3. Item sans titre
        f_no_title = os.path.join(self.temp_dir, "no_title.json")
        with open(f_no_title, "w") as f: json.dump([{"id": "c1"}], f)
        args_no_title = parser.parse_args(["create", "--id", "d3", "--title", "T3", "--items-file", f_no_title])
        with self.assertRaises(deck_store.DeckError):
            deck_cli.handle_create(args_no_title)

        # 4. Doublon d'id
        f_dup = os.path.join(self.temp_dir, "dup.json")
        with open(f_dup, "w") as f: json.dump([{"id": "dup", "title": "A"}, {"id": "dup", "title": "B"}], f)
        args_dup = parser.parse_args(["create", "--id", "d4", "--title", "T4", "--items-file", f_dup])
        with self.assertRaises(deck_store.DeckError):
            deck_cli.handle_create(args_dup)

    def test_handle_reset_and_delete(self):
        items_file = os.path.join(self.temp_dir, "items.json")
        items = [{"id": "c1", "title": "Carte 1"}]
        with open(items_file, "w", encoding="utf-8") as f: json.dump(items, f)

        parser = deck_cli.build_parser()
        args = parser.parse_args([
            "create", "--id", "test-ops", "--title", "Ops", "--items-file", items_file
        ])
        with patch("sys.stdout"): deck_cli.handle_create(args)

        # Simuler une décision
        deck = deck_store.load_deck("test-ops")
        deck["items"][0]["status"] = "decided"
        deck["items"][0]["chosen_action"] = "approve"
        deck_store.save_deck("test-ops", deck)

        # Reset
        args_reset = parser.parse_args(["reset", "test-ops"])
        with patch("sys.stdout"): deck_cli.handle_reset(args_reset)
        reset_deck = deck_store.load_deck("test-ops")
        self.assertEqual(reset_deck["items"][0]["status"], "pending")
        self.assertIsNone(reset_deck["items"][0]["chosen_action"])

        # Delete
        args_delete = parser.parse_args(["delete", "test-ops"])
        with patch("sys.stdout"): deck_cli.handle_delete(args_delete)
        with self.assertRaises(deck_store.DeckError):
            deck_store.load_deck("test-ops")

    def test_handle_summary_markdown_format(self):
        items_file = os.path.join(self.temp_dir, "items.json")
        items = [{"id": "c1", "title": "Carte 1"}]
        with open(items_file, "w", encoding="utf-8") as f: json.dump(items, f)

        parser = deck_cli.build_parser()
        args_create = parser.parse_args([
            "create", "--id", "deck-md", "--title", "Deck Markdown", "--items-file", items_file
        ])
        with patch("sys.stdout"): deck_cli.handle_create(args_create)

        deck = deck_store.load_deck("deck-md")
        deck["items"][0]["status"] = "decided"
        deck["items"][0]["chosen_action"] = "approve"
        deck["items"][0]["comment"] = "Validation rapide"
        deck_store.save_deck("deck-md", deck)

        args_summary = parser.parse_args(["summary", "deck-md", "--format", "md"])
        out = io.StringIO()
        with patch("sys.stdout", out):
            deck_cli.handle_summary(args_summary)
        output_text = out.getvalue()
        self.assertIn("# Synthèse Quick-Pick : Deck Markdown", output_text)
        self.assertIn("1/1 décidés", output_text)
        self.assertIn("Validation rapide", output_text)

    def test_handle_create_with_custom_actions_file(self):
        items_file = os.path.join(self.temp_dir, "items.json")
        items = [{"id": "c1", "title": "Carte 1"}]
        with open(items_file, "w", encoding="utf-8") as f: json.dump(items, f)

        actions_file = os.path.join(self.temp_dir, "actions.json")
        custom_actions = [
            {"id": "win", "label": "Gagner", "direction": "east", "color": "success"},
            {"id": "lose", "label": "Perdre", "direction": "west", "color": "danger"},
        ]
        with open(actions_file, "w", encoding="utf-8") as f: json.dump(custom_actions, f)

        parser = deck_cli.build_parser()
        args = parser.parse_args([
            "create", "--id", "custom-act-deck", "--title", "Custom Actions",
            "--items-file", items_file, "--actions-file", actions_file
        ])
        with patch("sys.stdout"):
            deck_cli.handle_create(args)

        deck = deck_store.load_deck("custom-act-deck")
        self.assertEqual(len(deck["default_actions"]), 2)
        self.assertEqual(deck["default_actions"][0]["id"], "win")
        self.assertEqual(deck["default_actions"][1]["label"], "Perdre")


if __name__ == "__main__":
    unittest.main()
