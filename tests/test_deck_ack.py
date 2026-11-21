#!/usr/bin/env python3
"""Prise en compte par l'agent (ack) : route, CLI, validité calculée, péremption, liste des decks."""
import http.client
import io
import json
import os
import shutil
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import deck_cli
import deck_store
import server


def make_deck(deck_id, n_decided, n_pending=0):
    items = []
    for i in range(1, n_decided + 1):
        items.append({"id": f"c{i}", "title": f"Carte {i}", "status": "decided", "chosen_action": "approve",
                      "decided_at": f"2026-11-18T10:00:{i:02d}+00:00", "decided_seq": i, "comment": None})
    for j in range(n_decided + 1, n_decided + n_pending + 1):
        items.append({"id": f"c{j}", "title": f"Carte {j}", "status": "pending", "chosen_action": None, "decided_at": None})
    return {"id": deck_id, "title": "mock data " + deck_id, "description": "mock data",
            "default_actions": deck_store.ACTION_TEMPLATES["binary"], "items": items}


class AckBase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.decks_dir = os.path.join(self.temp_dir, "decks")
        os.makedirs(self.decks_dir)
        self.original = deck_store.DECKS_DIR
        deck_store.set_decks_dir(self.decks_dir)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.QuickPickHandler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        deck_store.set_decks_dir(self.original)
        shutil.rmtree(self.temp_dir)

    def write(self, name, deck):
        with open(os.path.join(self.decks_dir, f"{name}.json"), "w", encoding="utf-8") as handle:
            json.dump(deck, handle)

    def post(self, path, payload=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.httpd.server_address[1], timeout=10)
        try:
            conn.request("POST", path, body=json.dumps(payload or {}), headers={"Content-Type": "application/json"})
            response = conn.getresponse()
            return response.status, json.loads(response.read().decode("utf-8") or "{}")
        finally:
            conn.close()

    def get(self, path):
        conn = http.client.HTTPConnection("127.0.0.1", self.httpd.server_address[1], timeout=10)
        try:
            conn.request("GET", path)
            response = conn.getresponse()
            return response.status, json.loads(response.read().decode("utf-8") or "{}")
        finally:
            conn.close()

    def listed(self, deck_id):
        return next(d for d in self.get("/api/decks")[1]["decks"] if d["id"] == deck_id)

    def ack(self, deck_id="d", agent="agent-test", note="fait"):
        return self.post(f"/api/decks/{deck_id}/ack", {"agent": agent, "note": note})


class AckRouteTests(AckBase):
    def test_ack_ok_then_exposed_everywhere(self):
        self.write("d", make_deck("d", 3))
        self.assertEqual(self.listed("d")["ack_state"], "none")
        status, data = self.ack()
        self.assertEqual(status, 200)
        self.assertEqual(data["ack_state"], "valid")
        self.assertEqual(data["ack"]["agent"], "agent-test")
        self.assertEqual(data["ack"]["note"], "fait")
        entry = self.listed("d")
        self.assertEqual(entry["ack_state"], "valid")
        self.assertEqual(entry["ack"]["agent"], "agent-test")
        self.assertIn("at", entry["ack"])
        self.assertNotIn("fingerprint", entry["ack"])
        status, state = self.get("/api/decks/d")
        self.assertEqual((status, state["ack_state"]), (200, "valid"))

    def test_ack_409_when_not_completed(self):
        self.write("d", make_deck("d", 2, 1))
        status, data = self.ack()
        self.assertEqual((status, data["code"]), (409, "deck_not_completed"))
        self.assertNotIn("ack", deck_store.load_deck("d"))

    def test_ack_409_on_empty_deck(self):
        self.write("d", make_deck("d", 0))
        status, data = self.ack()
        self.assertEqual((status, data["code"]), (409, "deck_empty"))
        self.assertEqual(self.listed("d")["ack_state"], "none")

    def test_ack_input_validation(self):
        self.write("d", make_deck("d", 1))
        self.assertEqual(self.post("/api/decks/d/ack", {})[0], 400)
        self.assertEqual(self.post("/api/decks/d/ack", {"agent": "  "})[0], 400)
        self.assertEqual(self.post("/api/decks/d/ack", {"agent": "a" * 41})[0], 400)
        self.assertEqual(self.post("/api/decks/d/ack", {"agent": "a" * 40})[0], 200)
        self.assertEqual(self.post("/api/decks/d/ack", {"agent": "a", "note": "n" * 281})[0], 400)
        self.assertEqual(self.post("/api/decks/d/ack", {"agent": "a", "note": "n" * 280})[0], 200)
        self.assertEqual(self.post("/api/decks/d/ack", {"agent": "a", "note": 5})[0], 400)
        self.assertEqual(self.post("/api/decks/inconnu/ack", {"agent": "a"})[0], 404)

    def test_note_is_optional(self):
        self.write("d", make_deck("d", 1))
        status, data = self.post("/api/decks/d/ack", {"agent": "a"})
        self.assertEqual((status, data["ack"]["note"]), (200, ""))


class AckStalenessTests(AckBase):
    """La validité est calculée à la lecture : tout changement de décisions la périme."""

    def setUp(self):
        super().setUp()
        self.write("d", make_deck("d", 3))
        self.assertEqual(self.ack()[0], 200)

    def state(self):
        return self.listed("d")["ack_state"]

    def test_undo_makes_stale(self):
        self.assertEqual(self.post("/api/decks/d/undo", {"item_id": "c2"})[0], 200)
        self.assertEqual(self.state(), "stale")
        self.assertEqual(self.listed("d")["ack"]["agent"], "agent-test")  # l'ancienne prise en compte reste lisible

    def test_redecision_of_same_action_makes_stale(self):
        self.post("/api/decks/d/undo", {"item_id": "c3"})
        self.assertEqual(self.post("/api/decks/d/decide", {"item_id": "c3", "action": "approve"})[0], 200)
        deck = deck_store.load_deck("d")
        self.assertTrue(deck_store.deck_progress(deck)["is_completed"])
        self.assertEqual(self.state(), "stale")  # même action, mais decided_seq/decided_at ont changé

    def test_redecision_in_same_second_changes_fingerprint(self):
        before = deck_store.deck_fingerprint(deck_store.load_deck("d"))
        deck = deck_store.load_deck("d")
        deck["items"][2]["decided_seq"] += 1  # même seconde, séquence différente
        self.assertNotEqual(before, deck_store.deck_fingerprint(deck))

    def test_added_cards_make_stale(self):
        self.assertEqual(self.post("/api/decks/d/items", {"items": ["nouvelle carte"]})[0], 200)
        self.assertEqual(self.state(), "stale")

    def test_reset_makes_stale(self):
        self.assertEqual(self.post("/api/decks/d/reset")[0], 200)
        self.assertEqual(self.state(), "stale")

    def test_back_to_identical_state_is_valid_again(self):
        # Restaurer un instantané identique à l'état acquitté redonne une prise en compte valide : voulu.
        version = deck_store.snapshot_deck("d", "manual")
        self.post("/api/decks/d/reset")
        self.assertEqual(self.state(), "stale")
        deck_store.restore_deck("d", version)
        self.assertEqual(self.state(), "valid")

    def test_restore_of_snapshot_taken_before_the_ack_is_not_valid(self):
        deck_store.save_deck("d", make_deck("d", 3))  # état sans ack
        version = deck_store.snapshot_deck("d", "manual")
        self.assertEqual(self.ack()[0], 200)
        self.assertEqual(self.state(), "valid")
        self.post("/api/decks/d/items", {"items": ["extra"]})
        self.assertEqual(self.state(), "stale")
        deck_store.restore_deck("d", version)  # instantané d'avant l'acquittement : pas d'ack du tout
        self.assertNotEqual(self.state(), "valid")

    def test_restore_of_pre_ack_snapshot_with_stale_ack_fingerprint(self):
        # Instantané pris avant des décisions modifiées mais qui porte un ack : empreinte différente.
        self.post("/api/decks/d/undo", {"item_id": "c1"})
        version = deck_store.snapshot_deck("d", "manual")  # c1 en attente + ack ancien
        self.post("/api/decks/d/decide", {"item_id": "c1", "action": "approve"})
        deck_store.restore_deck("d", version)
        self.assertEqual(self.state(), "stale")

    def test_state_none_without_ack_and_stale_never_stored(self):
        self.assertNotIn("state", deck_store.load_deck("d")["ack"])  # rien de dérivé n'est stocké
        self.assertEqual(set(deck_store.load_deck("d")["ack"]), {"agent", "note", "at", "fingerprint"})

    def test_empty_deck_is_never_valid(self):
        deck = make_deck("e", 0)
        deck["ack"] = {"agent": "a", "note": "", "at": "2026-11-21T10:00:00+00:00",
                       "fingerprint": deck_store.deck_fingerprint(deck)}
        self.write("e", deck)
        self.assertEqual(self.listed("e")["ack_state"], "stale")


class ListingTests(AckBase):
    def test_last_activity_and_unreadable_decks(self):
        self.write("d", make_deck("d", 3, 1))
        empty = os.path.join(self.decks_dir, "vide.json")
        self.write("vide", make_deck("vide", 0))
        os.utime(empty, (1700000000, 1700000000))
        with open(os.path.join(self.decks_dir, "casse.json"), "w", encoding="utf-8") as handle:
            handle.write('{"id": "casse", ')
        with patch("sys.stderr", new_callable=io.StringIO):
            decks = {d["id"]: d for d in self.get("/api/decks")[1]["decks"]}
        self.assertEqual(decks["d"]["last_activity"], "2026-11-18T10:00:03+00:00")  # max des decided_at
        self.assertTrue(decks["vide"]["last_activity"].startswith("2023-11-14"))  # sinon date du fichier
        self.assertTrue(decks["casse"]["invalid"])
        self.assertEqual(decks["casse"]["title"], "casse")
        self.assertTrue(decks["casse"]["error"])
        self.assertTrue(decks["casse"]["last_activity"])


class AckCliTests(AckBase):
    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with patch("sys.argv", ["deck_cli.py", *argv]), redirect_stdout(out), redirect_stderr(err):
            try:
                deck_cli.main()
                code = 0
            except SystemExit as exit_:
                code = exit_.code
        return code, out.getvalue(), err.getvalue()

    def test_cli_ack_ok(self):
        self.write("d", make_deck("d", 2))
        code, out, _ = self.run_cli("ack", "--id", "d", "--agent", "cli-agent", "--note", "appliqué")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["ack_state"], "valid")
        self.assertEqual(self.listed("d")["ack"]["agent"], "cli-agent")

    def test_cli_ack_409_equivalent_exit_1_when_not_completed(self):
        self.write("d", make_deck("d", 1, 1))
        code, _, err = self.run_cli("ack", "--id", "d", "--agent", "cli-agent")
        self.assertEqual(code, 1)
        self.assertIn("non terminé", err)
        self.assertEqual(self.listed("d")["ack_state"], "none")

    def test_cli_ack_empty_deck_and_missing_args(self):
        self.write("d", make_deck("d", 0))
        self.assertEqual(self.run_cli("ack", "--id", "d", "--agent", "a")[0], 1)
        self.assertEqual(self.run_cli("ack", "--agent", "a")[0], 1)
        with self.assertRaises(SystemExit):
            with redirect_stderr(io.StringIO()):
                with patch("sys.argv", ["deck_cli.py", "ack", "--id", "d"]):
                    deck_cli.main()  # --agent obligatoire


if __name__ == "__main__":
    unittest.main()
