#!/usr/bin/env python3
"""Tests unitaires pour le seed des decks d'exemple."""
import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

import deck_store


class SeedExampleDecksTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.decks_dir = os.path.join(self.temp_dir, "decks")
        self.examples_dir = os.path.join(self.temp_dir, "examples", "decks")
        os.makedirs(self.examples_dir, exist_ok=True)
        with open(os.path.join(self.examples_dir, "sample.json"), "w", encoding="utf-8") as handle:
            json.dump({"id": "sample", "title": "Deck d'exemple", "items": []}, handle)
        self.original_decks_dir = deck_store.DECKS_DIR
        self.original_examples_dir = deck_store.EXAMPLES_DIR
        deck_store.set_decks_dir(self.decks_dir)
        deck_store.EXAMPLES_DIR = self.examples_dir

    def tearDown(self):
        deck_store.set_decks_dir(self.original_decks_dir)
        deck_store.EXAMPLES_DIR = self.original_examples_dir
        shutil.rmtree(self.temp_dir)

    def write_user_deck(self, deck_id="user-deck", title="Deck utilisateur"):
        os.makedirs(self.decks_dir, exist_ok=True)
        path = os.path.join(self.decks_dir, f"{deck_id}.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"id": deck_id, "title": title, "items": []}, handle)
        return path

    def test_seeds_examples_when_decks_dir_is_empty(self):
        os.makedirs(self.decks_dir, exist_ok=True)
        self.assertEqual(deck_store.seed_example_decks(), ["sample.json"])
        self.assertTrue(os.path.isfile(os.path.join(self.decks_dir, "sample.json")))

    def test_creates_missing_decks_dir(self):
        self.assertEqual(deck_store.seed_example_decks(), ["sample.json"])
        self.assertEqual([d["id"] for d in deck_store.list_available_decks()], ["sample"])

    def test_never_overwrites_or_adds_when_a_deck_exists(self):
        path = self.write_user_deck()
        self.assertEqual(deck_store.seed_example_decks(), [])
        self.assertEqual(sorted(os.listdir(self.decks_dir)), ["user-deck.json"])
        with open(path, encoding="utf-8") as handle:
            self.assertEqual(json.load(handle)["title"], "Deck utilisateur")

    def test_no_seeding_without_examples(self):
        deck_store.EXAMPLES_DIR = os.path.join(self.temp_dir, "absent")
        self.assertEqual(deck_store.seed_example_decks(), [])
        self.assertFalse(os.path.exists(self.decks_dir))

    def test_shipped_examples_are_valid_decks(self):
        with patch.object(deck_store, "EXAMPLES_DIR", os.path.join(deck_store.BASE_DIR, "examples", "decks")):
            self.assertEqual(deck_store.seed_example_decks(), ["code-review.json", "product-backlog.json"])
        self.assertEqual(sorted(d["id"] for d in deck_store.list_available_decks()), ["code-review", "product-backlog"])
