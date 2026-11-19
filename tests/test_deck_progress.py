#!/usr/bin/env python3
"""Tests de deck_progress, active_seconds, normalize_card, add_items, wait et du Markdown du CLI."""
import http.client
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import deck_cli
import deck_store
import deck_summary
import server
from deck_store import DeckError

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TempDecksCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.decks_dir = os.path.join(self.temp_dir, "decks")
        os.makedirs(self.decks_dir)
        self.original_decks_dir = deck_store.DECKS_DIR
        deck_store.set_decks_dir(self.decks_dir)

    def tearDown(self):
        deck_store.set_decks_dir(self.original_decks_dir)
        shutil.rmtree(self.temp_dir)

    def write_deck(self, name, deck):
        with open(os.path.join(self.decks_dir, f"{name}.json"), "w", encoding="utf-8") as handle:
            json.dump(deck, handle)


def make_deck(deck_id, items, **extra):
    deck = {
        "id": deck_id,
        "title": "Deck " + deck_id,
        "default_actions": deck_store.ACTION_TEMPLATES["binary"],
        "items": items,
    }
    deck.update(extra)
    return deck


def decided(item_id, stamp, action="approve"):
    return {"id": item_id, "title": "T " + item_id, "status": "decided", "chosen_action": action, "decided_at": stamp}


def pending(item_id):
    return {"id": item_id, "title": "T " + item_id, "status": "pending", "chosen_action": None, "decided_at": None}


class DeckProgressTests(unittest.TestCase):
    def test_progress_of_a_half_decided_deck(self):
        deck = make_deck("x", [decided("a", "2026-11-19T10:00:00+00:00"), pending("b")])
        self.assertEqual(deck_store.deck_progress(deck), {"total": 2, "decided": 1, "is_completed": False, "completed_at": None})

    def test_completed_at_is_the_latest_parsable_stamp_and_ignores_junk(self):
        deck = make_deck("x", [
            decided("a", "2026-11-19T10:00:00+00:00"),
            decided("b", 1752288030),            # entier : ignoré
            decided("c", "pas-une-date"),        # non analysable : ignoré
            decided("d", "2026-11-19T12:30:00"), # naïf = UTC
        ])
        progress = deck_store.deck_progress(deck)
        self.assertTrue(progress["is_completed"])
        self.assertEqual(progress["completed_at"], "2026-11-19T12:30:00+00:00")

    def test_empty_deck_is_completed_without_completed_at(self):
        progress = deck_store.deck_progress(make_deck("x", []))
        self.assertTrue(progress["is_completed"])
        self.assertIsNone(progress["completed_at"])

    def test_state_and_summary_expose_completed_at(self):
        deck = make_deck("x", [decided("a", "2026-11-19T10:00:00+00:00"), decided("b", "2026-11-19T10:00:05+00:00")])
        self.assertEqual(deck_store.find_deck_state(deck)["completed_at"], "2026-11-19T10:00:05+00:00")
        self.assertEqual(deck_summary.compute_deck_summary(deck)["completed_at"], "2026-11-19T10:00:05+00:00")
        deck["items"][1] = pending("b")
        self.assertIsNone(deck_store.find_deck_state(deck)["completed_at"])

    def test_parse_decision_timestamp_lives_in_deck_store_and_is_reexported(self):
        self.assertIs(deck_summary.parse_decision_timestamp, deck_store.parse_decision_timestamp)

    def test_summary_keeps_its_own_empty_deck_definition(self):
        summary = deck_summary.compute_deck_summary(make_deck("x", []))
        self.assertFalse(summary["is_completed"])
        self.assertTrue(deck_store.find_deck_state(make_deck("x", []))["is_completed"])


class ActiveSecondsTests(unittest.TestCase):
    def test_two_decisions_three_hours_apart_count_at_most_the_cap(self):
        deck = make_deck("x", [decided("a", "2026-11-19T08:00:00+00:00"), decided("b", "2026-11-19T11:00:00+00:00")])
        summary = deck_summary.compute_deck_summary(deck)
        self.assertLessEqual(summary["active_seconds"], deck_summary.ACTIVE_GAP_CAP_S)
        self.assertEqual(summary["elapsed_seconds"], 3 * 3600)  # champ historique inchangé

    def test_gaps_are_summed_and_capped_one_by_one(self):
        deck = make_deck("x", [
            decided("a", "2026-11-19T08:00:00+00:00"),
            decided("b", "2026-11-19T08:00:10+00:00"),   # +10
            decided("c", "2026-11-19T09:00:00+00:00"),   # plafonné à 120
            decided("d", "2026-11-19T09:00:30+00:00"),   # +30
        ])
        self.assertEqual(deck_summary.compute_deck_summary(deck)["active_seconds"], 160)

    def test_integer_and_unparsable_stamps_do_not_crash(self):
        deck = make_deck("x", [
            decided("a", "2026-11-19T08:00:00+00:00"),
            decided("b", 1752288030),
            decided("c", "pas-une-date"),
            decided("d", "2026-11-19T08:00:20+00:00"),
        ])
        self.assertEqual(deck_summary.compute_deck_summary(deck)["active_seconds"], 20)

    def test_zero_or_one_decision_is_zero(self):
        self.assertEqual(deck_summary.compute_deck_summary(make_deck("x", []))["active_seconds"], 0)
        one = make_deck("x", [decided("a", "2026-11-19T08:00:00+00:00")])
        self.assertEqual(deck_summary.compute_deck_summary(one)["active_seconds"], 0)


class LabeledBreakdownTests(unittest.TestCase):
    def test_labels_in_first_appearance_order_with_none_as_sans_action(self):
        deck = make_deck("x", [
            decided("a", "2026-11-19T08:00:00+00:00", "reject"),
            decided("b", "2026-11-19T08:00:01+00:00", "approve"),
            decided("c", "2026-11-19T08:00:02+00:00", "reject"),
            decided("d", "2026-11-19T08:00:03+00:00", None),
        ])
        labeled = deck_summary.compute_deck_summary(deck)["actions_breakdown_labeled"]
        self.assertEqual(labeled, [
            {"id": "reject", "label": "Non / Rejeter", "count": 2},
            {"id": "approve", "label": "Oui / Valider", "count": 1},
            {"id": None, "label": "Sans action", "count": 1},
        ])


class NormalizeCardTests(unittest.TestCase):
    def test_string_and_blank_line(self):
        self.assertEqual(deck_store.normalize_card("  Titre  ", 1)["title"], "Titre")
        self.assertIsNone(deck_store.normalize_card("   ", 1))

    def test_whitelist_ignores_status_and_other_fields(self):
        card = deck_store.normalize_card({
            "title": "T", "description": "D", "bullets": ["a", "b"],
            "status": "decided", "chosen_action": "approve", "decided_seq": 9, "actions": [{"id": "x"}],
            "add_actions": [{"id": "y"}], "remove_actions": ["z"], "inconnu": 1, "id": "hack",
        }, 1)
        self.assertEqual(card, {"title": "T", "description": "D", "bullets": ["a", "b"],
                                "status": "pending", "chosen_action": None, "decided_at": None})

    def test_non_string_bullet_is_refused(self):
        for bad in (2, None, {"x": 1}, ["a"]):
            with self.subTest(bad=bad), self.assertRaises(DeckError) as ctx:
                deck_store.normalize_card({"title": "T", "bullets": ["ok", bad]}, 1)
            self.assertIn("format invalide", str(ctx.exception))

    def test_errors(self):
        bad = [
            (5, "format invalide"), (None, "format invalide"), ([], "format invalide"),
            ({"title": 3}, "format invalide"), ({"title": "  "}, "titre obligatoire"), ({}, "titre obligatoire"),
            ({"title": "T", "bullets": "a"}, "bullets doit être une liste"),
            ({"title": "x" * (deck_store.MAX_ITEM_TITLE_LENGTH + 1)}, "trop longue"),
            ({"title": "T", "description": "d" * (deck_store.MAX_ITEM_DESCRIPTION_LENGTH + 1)}, "description"),
            ({"title": "T", "description": 4}, "description"),
            ({"title": "T", "bullets": ["b"] * (deck_store.MAX_ITEM_BULLETS + 1)}, "bullets au maximum"),
            ({"title": "T", "bullets": ["b" * (deck_store.MAX_BULLET_LENGTH + 1)]}, "bullet trop long"),
        ]
        for raw, fragment in bad:
            with self.subTest(raw=raw), self.assertRaises(DeckError) as ctx:
                deck_store.normalize_card(raw, 3)
            self.assertIn(fragment, str(ctx.exception))
            self.assertIn("#3", str(ctx.exception))

    def test_limits_are_inclusive(self):
        card = deck_store.normalize_card({
            "title": "x" * deck_store.MAX_ITEM_TITLE_LENGTH,
            "description": "d" * deck_store.MAX_ITEM_DESCRIPTION_LENGTH,
            "bullets": ["b" * deck_store.MAX_BULLET_LENGTH] * deck_store.MAX_ITEM_BULLETS,
        }, 1)
        self.assertEqual(len(card["bullets"]), deck_store.MAX_ITEM_BULLETS)


class CreateDeckTests(TempDecksCase):
    def test_description_and_object_cards(self):
        deck = deck_store.create_deck("Titre", ["Simple", {"title": "Riche", "description": "Détail", "bullets": ["p1"]}],
                                      description="  Une description  ")
        self.assertEqual(deck["description"], "Une description")
        self.assertEqual([i["id"] for i in deck["items"]], ["item-1", "item-2"])
        self.assertEqual(deck["items"][1]["description"], "Détail")
        self.assertEqual(deck_store.load_deck(deck["id"]), deck)

    def test_description_limit(self):
        with self.assertRaises(DeckError):
            deck_store.create_deck("Titre", ["a"], description="d" * (deck_store.MAX_DECK_DESCRIPTION_LENGTH + 1))
        with self.assertRaises(DeckError):
            deck_store.create_deck("Titre", ["a"], description=12)
        self.assertEqual([n for n in os.listdir(self.decks_dir) if not n.startswith(".")], [])

    def test_too_many_items_carries_a_code(self):
        with self.assertRaises(DeckError) as ctx:
            deck_store.create_deck("Titre", ["a"] * (deck_store.MAX_DECK_ITEMS + 1))
        self.assertEqual(ctx.exception.code, "too_many_items")


class LoadDeckErrorTests(TempDecksCase):
    def test_broken_json_and_oserror_become_deck_error(self):
        with open(os.path.join(self.decks_dir, "casse.json"), "w", encoding="utf-8") as handle:
            handle.write("{pas du json")
        with self.assertRaises(DeckError):
            deck_store.load_deck("casse")
        self.write_deck("ok", make_deck("ok", [pending("a")]))
        with patch("builtins.open", side_effect=PermissionError("refusé")), self.assertRaises(DeckError):
            deck_store.load_deck("ok")

    def test_items_null_or_not_a_list_is_a_deck_error(self):
        for index, value in enumerate((None, "x", 3, {"a": 1})):
            deck_id = f"nul{index}"
            with open(os.path.join(self.decks_dir, deck_id + ".json"), "w", encoding="utf-8") as handle:
                json.dump({"id": deck_id, "title": "T", "items": value}, handle)
            with self.subTest(items=value), self.assertRaises(DeckError):
                deck_store.load_deck(deck_id)

    def test_disappearance_between_isfile_and_open_is_a_deck_error(self):
        self.write_deck("ok", make_deck("ok", [pending("a")]))
        with patch("builtins.open", side_effect=FileNotFoundError()), self.assertRaises(DeckError):
            deck_store.load_deck("ok")


class ListAvailableDecksTests(TempDecksCase):
    def test_half_decided_invalid_and_mismatched_id(self):
        self.write_deck("half", make_deck("half", [decided("a", "2026-11-19T10:00:00+00:00"), pending("b")]))
        self.write_deck("done", make_deck("done", [decided("a", "2026-11-19T10:00:00+00:00")]))
        self.write_deck("bad", make_deck("bad", ["x"]))
        self.write_deck("file-name", make_deck("inner-id", [pending("a")]))
        with open(os.path.join(self.decks_dir, "json-casse.json"), "w", encoding="utf-8") as handle:
            handle.write("{nope")
        listed = {d["id"]: d for d in deck_store.list_available_decks()}
        self.assertEqual(set(listed), {"half", "done", "bad", "file-name"})  # JSON cassé : non listé
        self.assertEqual((listed["half"]["total"], listed["half"]["decided"], listed["half"]["is_completed"]), (2, 1, False))
        self.assertTrue(listed["done"]["is_completed"])
        self.assertFalse(listed["half"]["invalid"])
        for key in ("bad", "file-name"):
            self.assertTrue(listed[key]["invalid"])
            self.assertIsNone(listed[key]["total"])
            self.assertIsNone(listed[key]["decided"])
        self.assertNotIn("inner-id", listed)  # jamais l'id interne d'un deck invalide


class AddItemsTests(TempDecksCase):
    def test_arbitrary_cli_ids_no_duplicate_and_decision_hits_right_card(self):
        self.write_deck("cli", make_deck("cli", [pending("alpha"), pending("item-7"), pending("item-2"), pending("zeta")]))
        deck = deck_store.add_items("cli", ["Nouvelle 1", {"title": "Nouvelle 2"}, "Nouvelle 3"])
        ids = [i["id"] for i in deck["items"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids[4:], ["item-8", "item-9", "item-10"])
        self.assertEqual([i["title"] for i in deck["items"][4:]], ["Nouvelle 1", "Nouvelle 2", "Nouvelle 3"])

    def test_snapshot_taken_and_reopens_a_completed_deck(self):
        self.write_deck("done", make_deck("done", [decided("a", "2026-11-19T10:00:00+00:00")]))
        deck_store.add_items("done", ["Encore"])
        self.assertEqual(len(deck_store.list_history("done")), 1)
        self.assertFalse(deck_store.find_deck_state(deck_store.load_deck("done"))["is_completed"])

    def test_limit_counts_existing_plus_added(self):
        self.write_deck("big", make_deck("big", [pending(f"item-{i}") for i in range(1, 199)]))
        deck_store.add_items("big", ["a", "b"])  # 200 : accepté
        with self.assertRaises(DeckError) as ctx:
            deck_store.add_items("big", ["c"])
        self.assertEqual(ctx.exception.code, "too_many_items")
        self.assertEqual(len(deck_store.load_deck("big")["items"]), 200)

    def test_empty_payloads_have_a_code_and_change_nothing(self):
        self.write_deck("d", make_deck("d", [pending("a")]))
        for raw in (None, [], "texte", ["  ", ""], {"items": []}):
            with self.subTest(raw=raw), self.assertRaises(DeckError) as ctx:
                deck_store.add_items("d", raw)
            self.assertEqual(ctx.exception.code, "empty_items")
        self.assertEqual(deck_store.list_history("d"), [])

    def test_api_object_with_status_decided_is_added_pending(self):
        self.write_deck("d", make_deck("d", [pending("a")]))
        deck = deck_store.add_items("d", [{"title": "Piège", "status": "decided", "chosen_action": "approve"}])
        added = deck["items"][-1]
        self.assertEqual((added["status"], added["chosen_action"]), ("pending", None))


def run_cli(*argv):
    out, err = io.StringIO(), io.StringIO()
    code = 0
    with patch.object(sys, "argv", ["deck_cli.py", *argv]), patch("sys.stdout", out), patch("sys.stderr", err):
        try:
            deck_cli.main()
        except SystemExit as exit_info:
            code = exit_info.code
    return code, out.getvalue(), err.getvalue()


class CliTests(TempDecksCase):
    def test_main_does_not_reseed_example_decks(self):
        code, _out, _err = run_cli("list")
        self.assertEqual(code, 0)
        self.assertEqual([n for n in os.listdir(self.decks_dir) if n.endswith(".json")], [])
        self.assertTrue(os.path.isdir(deck_store.EXAMPLES_DIR))  # les exemples existent : c'est bien le CLI qui ne sème plus

    def test_markdown_shows_labels_not_raw_ids_and_temps_actif(self):
        self.write_deck("md", make_deck("md", [
            decided("a", "2026-11-19T08:00:00+00:00", "approve"),
            decided("b", "2026-11-19T08:00:40+00:00", "reject"),
        ]))
        code, out, _err = run_cli("summary", "md", "--format", "md")
        self.assertEqual(code, 0)
        self.assertIn("**Oui / Valider** : 1", out)
        self.assertIn("**Non / Rejeter** : 1", out)
        self.assertNotIn("**approve**", out)
        self.assertNotIn("**reject**", out)
        self.assertIn("**Temps actif** : 40s", out)
        self.assertNotIn("Temps total", out)

    def test_wait_non_finite_timeout_exits_1(self):
        self.write_deck("w", make_deck("w", [pending("a")]))
        for value in ("nan", "inf"):
            with self.subTest(value=value):
                code, _out, err = run_cli("wait", "w", "--timeout", value)
                self.assertEqual(code, 1)
                self.assertIn("timeout", err)

    def test_wait_negative_timeout_exits_1(self):
        self.write_deck("w", make_deck("w", [pending("a")]))
        code, _out, err = run_cli("wait", "w", "--timeout", "-1")
        self.assertEqual(code, 1)
        self.assertIn("timeout", err)

    def test_wait_on_completed_deck_returns_at_once_with_json_line(self):
        self.write_deck("w", make_deck("w", [decided("a", "2026-11-19T08:00:00+00:00")]))
        code, out, _err = run_cli("wait", "w")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), {"deck_id": "w", "is_completed": True, "decided": 1, "total": 1})

    def test_wait_empty_deck_exits_0(self):
        self.write_deck("w", make_deck("w", []))
        self.assertEqual(run_cli("wait", "w")[0], 0)


class WaitEndToEndTests(TempDecksCase):
    """`deck_cli wait` lancé comme vrai processus, deck décidé par l'API HTTP."""

    def setUp(self):
        super().setUp()
        self.assertTrue(os.path.abspath(self.decks_dir).startswith(os.path.abspath(tempfile.gettempdir())))
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.QuickPickHandler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        super().tearDown()

    def post(self, path, payload):
        conn = http.client.HTTPConnection("127.0.0.1", self.httpd.server_address[1], timeout=5)
        try:
            conn.request("POST", path, body=json.dumps(payload), headers={"Content-Type": "application/json"})
            response = conn.getresponse()
            return response.status, json.loads(response.read().decode("utf-8") or "{}")
        finally:
            conn.close()

    def cli(self, *argv):
        env = dict(os.environ, QUICK_PICK_DATA_DIR=self.decks_dir, PYTHONPATH=REPO_DIR)
        return subprocess.Popen([sys.executable, os.path.join(REPO_DIR, "deck_cli.py"), *argv],
                                cwd=REPO_DIR, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def test_wait_exits_0_once_every_card_is_decided_through_the_api(self):
        self.write_deck("e2e", make_deck("e2e", [pending("a"), pending("b")]))
        proc = self.cli("wait", "e2e", "--timeout", "30")
        try:
            time.sleep(0.5)
            self.assertIsNone(proc.poll())  # pas terminé : l'attente continue
            for item_id in ("a", "b"):
                self.assertEqual(self.post("/api/decks/e2e/decide", {"item_id": item_id, "action": "approve"})[0], 200)
            out, _err = proc.communicate(timeout=15)
        finally:
            if proc.poll() is None:
                proc.kill()
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(json.loads(out), {"deck_id": "e2e", "is_completed": True, "decided": 2, "total": 2})

    def test_wait_times_out_with_exit_3_and_json_line(self):
        self.write_deck("never", make_deck("never", [pending("a")]))
        proc = self.cli("wait", "never", "--timeout", "1")
        out, _err = proc.communicate(timeout=15)
        self.assertEqual(proc.returncode, 3)
        self.assertEqual(json.loads(out), {"deck_id": "never", "is_completed": False, "decided": 0, "total": 1})

    def test_wait_on_absent_deck_exits_1(self):
        proc = self.cli("wait", "absent", "--timeout", "1")
        _out, err = proc.communicate(timeout=15)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("introuvable", err)

    def test_wait_exits_1_when_the_deck_disappears_while_waiting(self):
        self.write_deck("gone", make_deck("gone", [pending("a")]))
        proc = self.cli("wait", "gone", "--timeout", "30")
        try:
            time.sleep(0.5)
            self.assertEqual(self.post("/api/decks/gone/delete", {})[0], 200)
            _out, err = proc.communicate(timeout=15)
        finally:
            if proc.poll() is None:
                proc.kill()
        self.assertEqual(proc.returncode, 1)
        self.assertIn("introuvable", err)


if __name__ == "__main__":
    unittest.main()
