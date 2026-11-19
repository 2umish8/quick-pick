import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest import mock

import deck_cli
import deck_store
import server

try:
    import fcntl  # noqa: F401
    HAS_FCNTL = True
except ImportError:
    HAS_FCNTL = False

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHILD = os.path.join(ROOT, "tests", "helpers", "lock_child.py")


class TempDecksCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="qp-lock-")
        self.decks_dir = os.path.join(self.temp_dir, "decks")
        os.makedirs(self.decks_dir)
        self.original_dir = deck_store.DECKS_DIR
        deck_store.set_decks_dir(self.decks_dir)

    def tearDown(self):
        deck_store.set_decks_dir(self.original_dir)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def make_deck(self, deck_id="d", count=3):
        return deck_store.create_deck(title="Deck " + deck_id, items=[f"carte {i}" for i in range(count)], deck_id=deck_id)

    def deck_bytes(self, deck_id="d"):
        with open(os.path.join(self.decks_dir, deck_id + ".json"), "rb") as handle:
            return handle.read()

    def deck_json(self, deck_id="d"):
        with open(os.path.join(self.decks_dir, deck_id + ".json"), encoding="utf-8") as handle:
            return json.load(handle)

    def decided(self, deck_id="d"):
        return len([i for i in self.deck_json(deck_id)["items"] if i["status"] == "decided"])

    def run_cli(self, *argv):
        env = dict(os.environ, QUICK_PICK_DATA_DIR=self.decks_dir, PYTHONPATH=ROOT)
        return subprocess.run([sys.executable, os.path.join(ROOT, "deck_cli.py")] + list(argv),
                              capture_output=True, text=True, env=env, timeout=60)


@unittest.skipUnless(HAS_FCNTL, "fcntl indisponible")
class DeckLockProcessTest(TempDecksCase):
    def spawn_children(self, mode, count=8):
        self.make_deck("d", count)
        barrier = os.path.join(self.temp_dir, "barrier")
        os.makedirs(barrier)
        procs = [subprocess.Popen([sys.executable, CHILD, self.decks_dir, "d", f"item-{i}", mode, barrier, str(count)])
                 for i in range(1, count + 1)]
        codes = [proc.wait(timeout=60) for proc in procs]
        self.assertEqual(codes, [0] * count)

    def test_eight_processes_with_lock_keep_all_decisions(self):
        self.spawn_children("lock")
        self.assertEqual(self.decided(), 8)

    def test_control_without_lock_loses_decisions(self):
        # Témoin : sans verrou, la barrière force la course et une seule décision survit.
        self.spawn_children("nolock")
        self.assertEqual(self.decided(), 1)


class DeckLockBehaviourTest(TempDecksCase):
    def test_nested_lock_does_not_block(self):
        started = time.monotonic()
        with deck_store.deck_lock():
            with deck_store.deck_lock():
                with deck_store.deck_lock():
                    pass
        self.assertLess(time.monotonic() - started, 1)

    def test_lock_released_after_exception(self):
        with self.assertRaises(RuntimeError):
            with deck_store.deck_lock():
                raise RuntimeError("boom")
        started = time.monotonic()
        with deck_store.deck_lock():
            pass
        self.assertLess(time.monotonic() - started, 1)

    @unittest.skipUnless(HAS_FCNTL, "fcntl indisponible")
    def test_other_process_holding_lock_gives_busy_error(self):
        holder = subprocess.Popen(
            [sys.executable, "-c",
             "import sys,time;sys.path.insert(0,%r);import deck_store;deck_store.set_decks_dir(%r)\n"
             "with deck_store.deck_lock():\n print('held',flush=True);time.sleep(5)" % (ROOT, self.decks_dir)],
            stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(holder.stdout.readline().strip(), "held")
            with mock.patch.object(deck_store, "LOCK_TIMEOUT_S", 0.3):
                with self.assertRaises(deck_store.DeckBusyError) as ctx:
                    with deck_store.deck_lock():
                        pass
            self.assertEqual(ctx.exception.http_status, 503)
            self.assertEqual(ctx.exception.code, "busy")
        finally:
            holder.kill()
            holder.wait()

    def test_unusable_lock_path_raises_lock_unavailable(self):
        blocker = os.path.join(self.temp_dir, "file")
        with open(blocker, "w") as handle:
            handle.write("x")
        deck_store.set_decks_dir(os.path.join(blocker, "sub"))
        if deck_store.fcntl is None:
            self.skipTest("fcntl indisponible")
        with self.assertRaises(deck_store.LockUnavailableError) as ctx:
            with deck_store.deck_lock():
                pass
        self.assertEqual(ctx.exception.code, "storage_error")

    def test_validate_new_deck_never_creates_lock_file(self):
        shutil.rmtree(self.decks_dir)
        with self.assertRaises(deck_store.DeckError):
            deck_store.create_deck(title="", items=["a"])
        self.assertFalse(os.path.exists(self.decks_dir))


class SnapshotTest(TempDecksCase):
    def test_delete_then_restore_gives_identical_content(self):
        self.make_deck("d", 3)
        before = self.deck_bytes()
        deck_store.delete_deck("d")
        self.assertFalse(os.path.exists(os.path.join(self.decks_dir, "d.json")))
        versions = deck_store.list_history("d")
        self.assertEqual(len(versions), 1)
        self.assertTrue(versions[0].endswith("Z-delete"))
        deck_store.restore_deck("d", versions[0])
        self.assertEqual(self.deck_bytes(), before)

    def test_reset_snapshots_before_changing_and_identical_is_not_duplicated(self):
        self.make_deck("d", 2)
        deck = deck_store.load_deck("d")
        deck["items"][0]["status"] = "decided"
        deck_store.save_deck("d", deck)
        decided_bytes = self.deck_bytes()
        deck_store.reset_deck("d")
        versions = deck_store.list_history("d")
        self.assertEqual(len(versions), 1)
        with open(os.path.join(self.decks_dir, ".history", "d", versions[0] + ".json"), "rb") as handle:
            self.assertEqual(handle.read(), decided_bytes)
        deck_store.reset_deck("d")  # l'état remis à zéro diffère de la copie « décidée » : 2e version
        self.assertEqual(len(deck_store.list_history("d")), 2)
        deck_store.reset_deck("d")  # identique octet pour octet à la plus récente : pas de doublon
        self.assertEqual(len(deck_store.list_history("d")), 2)

    def test_retention_keeps_ten_most_recent_after_twelve_resets(self):
        self.make_deck("d", 2)
        for round_number in range(12):
            deck = deck_store.load_deck("d")
            deck["items"][0]["status"] = "decided"
            deck["items"][0]["comment"] = f"round {round_number}"
            deck_store.save_deck("d", deck)
            deck_store.reset_deck("d")
        versions = deck_store.list_history("d")
        self.assertEqual(len(versions), 10)
        self.assertEqual(versions, sorted(versions, reverse=True))
        # La plus ancienne des 10 est la 3e (rondes 0 et 1 élaguées).
        oldest = os.path.join(self.decks_dir, ".history", "d", versions[-1] + ".json")
        with open(oldest, encoding="utf-8") as handle:
            self.assertEqual(json.load(handle)["items"][0]["comment"], "round 2")

    def test_restore_oldest_of_ten_versions_succeeds(self):
        self.make_deck("d", 2)
        for round_number in range(12):
            deck = deck_store.load_deck("d")
            deck["items"][0]["status"] = "decided"
            deck["items"][0]["comment"] = f"round {round_number}"
            deck_store.save_deck("d", deck)
            deck_store.reset_deck("d")
        oldest = deck_store.list_history("d")[-1]
        restored = deck_store.restore_deck("d", oldest)
        self.assertEqual(restored["items"][0]["comment"], "round 2")
        self.assertEqual(self.deck_json()["items"][0]["comment"], "round 2")
        self.assertEqual(len(deck_store.list_history("d")), 10)  # le restore photographie l'état courant, élague

    def test_restore_refuses_bad_versions_and_paths(self):
        self.make_deck("d", 1)
        deck_store.delete_deck("d")
        for version in ("../x", "..", "20260101T000000000000Z", "x/../../y-reset", "20261119T120000123456Z-Reset",
                        "20261119T120000123456Z-reset.json", "", None):
            with self.subTest(version=version), self.assertRaises(deck_store.DeckError):
                deck_store.restore_deck("d", version)
        with self.assertRaises(deck_store.DeckError):
            deck_store.restore_deck("../d", "20261119T120000123456Z-reset")
        with self.assertRaises(deck_store.DeckError):
            deck_store.restore_deck("d", "20261119T120000123456Z-reset")  # inexistante

    def test_restore_refuses_version_of_another_deck(self):
        self.make_deck("a", 1)
        deck_store.delete_deck("a")
        version = deck_store.list_history("a")[0]
        os.makedirs(os.path.join(self.decks_dir, ".history", "b"))
        shutil.copy(os.path.join(self.decks_dir, ".history", "a", version + ".json"),
                    os.path.join(self.decks_dir, ".history", "b", version + ".json"))
        with self.assertRaises(deck_store.DeckError):
            deck_store.restore_deck("b", version)
        self.assertFalse(os.path.exists(os.path.join(self.decks_dir, "b.json")))

    def test_failed_snapshot_refuses_operation_and_keeps_deck(self):
        self.make_deck("d", 2)
        deck = deck_store.load_deck("d")
        deck["items"][0]["status"] = "decided"
        deck_store.save_deck("d", deck)
        before = self.deck_bytes()
        with mock.patch.object(deck_store, "_copy_snapshot", side_effect=OSError("disque plein")):
            for operation in (deck_store.reset_deck, deck_store.delete_deck):
                with self.subTest(operation=operation.__name__), self.assertRaises(deck_store.SnapshotError) as ctx:
                    operation("d")
                self.assertEqual(ctx.exception.http_status, 500)
                self.assertEqual(ctx.exception.code, "snapshot_failed")
                self.assertEqual(self.deck_bytes(), before)

    def test_snapshot_of_missing_deck_is_none_and_motif_validated(self):
        self.assertIsNone(deck_store.snapshot_deck("absent", "reset"))
        self.make_deck("d", 1)
        with self.assertRaises(deck_store.DeckError):
            deck_store.snapshot_deck("d", "../x")

    def test_history_and_restore_cli(self):
        self.make_deck("d", 2)
        self.assertEqual(self.run_cli("delete", "d").returncode, 0)
        listing = self.run_cli("history", "d")
        self.assertEqual(listing.returncode, 0)
        version = listing.stdout.strip().splitlines()[0]
        self.assertTrue(version.endswith("Z-delete"))
        restored = self.run_cli("restore", "d", version)
        self.assertEqual(restored.returncode, 0, restored.stderr)
        self.assertEqual(len(self.deck_json()["items"]), 2)
        bad = self.run_cli("restore", "d", "../x")
        self.assertEqual(bad.returncode, 1)
        self.assertIn("Erreur", bad.stderr)

    def test_cli_reports_storage_error_with_exit_1(self):
        self.make_deck("d", 1)
        with mock.patch.object(deck_store, "_copy_snapshot", side_effect=OSError("plein")), \
                mock.patch("sys.argv", ["deck_cli.py", "reset", "d"]), \
                mock.patch("sys.stderr"), self.assertRaises(SystemExit) as ctx:
            deck_cli.main()
        self.assertEqual(ctx.exception.code, 1)

    def test_history_and_lock_entries_do_not_appear_in_deck_list(self):
        self.make_deck("d", 1)
        deck_store.reset_deck("d")
        deck_store.delete_deck("d")
        self.make_deck("e", 1)
        self.assertEqual([d["id"] for d in deck_store.list_available_decks()], ["e"])


@unittest.skipUnless(HAS_FCNTL, "fcntl indisponible")
class ServerCliConcurrencyTest(TempDecksCase):
    def setUp(self):
        super().setUp()
        self.assertTrue(self.decks_dir.startswith(tempfile.gettempdir()))
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.QuickPickHandler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)
        super().tearDown()

    def post(self, path, body):
        conn = HTTPConnection("127.0.0.1", self.httpd.server_address[1], timeout=20)
        try:
            conn.request("POST", path, body=json.dumps(body), headers={"Content-Type": "application/json"})
            response = conn.getresponse()
            raw = response.read().decode("utf-8")
            return response.status, (json.loads(raw) if raw else {})
        finally:
            conn.close()

    def test_cli_reset_loop_during_http_decides_never_corrupts(self):
        self.make_deck("d", 3)
        env = dict(os.environ, QUICK_PICK_DATA_DIR=self.decks_dir, PYTHONPATH=ROOT)
        loop = ("import subprocess,sys\nfor _ in range(12):\n"
                " subprocess.run([sys.executable,%r,'reset','d'],check=True)\n" % os.path.join(ROOT, "deck_cli.py"))
        cli = subprocess.Popen([sys.executable, "-c", loop], env=env)
        statuses = []
        while cli.poll() is None:
            statuses.append(self.post("/api/decks/d/decide", {"item_id": "item-1", "action": "approve"})[0])
        self.assertEqual(cli.returncode, 0)
        self.assertTrue(statuses)
        self.assertEqual(set(statuses), {200})
        self.assertEqual(len(self.deck_json()["items"]), 3)
        self.assertEqual([n for n in os.listdir(self.decks_dir) if n.endswith(".tmp")], [])

    def test_parallel_http_creates_of_same_id_one_wins(self):
        results = []

        def create():
            results.append(self.post("/api/decks", {"title": "Sprint", "items": ["a"], "id": "same"})[0])

        threads = [threading.Thread(target=create) for _ in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sorted(results), [201] + [409] * 5)

    def test_cli_create_and_http_create_of_same_id_one_wins(self):
        items_file = os.path.join(self.temp_dir, "items.json")
        with open(items_file, "w", encoding="utf-8") as handle:
            json.dump([{"id": "x", "title": "X"}], handle)
        for round_number in range(5):
            deck_id = f"race-{round_number}"
            outcome = {}

            def http_create():
                outcome["http"] = self.post("/api/decks", {"title": "T", "items": ["a"], "id": deck_id})[0]

            thread = threading.Thread(target=http_create)
            thread.start()
            cli = self.run_cli("create", "--id", deck_id, "--title", "T", "--items-file", items_file)
            thread.join()
            self.assertEqual(sorted([outcome["http"] == 201, cli.returncode == 0]), [False, True],
                             f"{outcome} {cli.returncode} {cli.stderr}")
            self.assertIn(outcome["http"], (201, 409))

    def test_busy_returns_503_json_on_write_but_get_is_never_blocked(self):
        self.make_deck("d", 1)
        entered = threading.Event()
        release = threading.Event()

        def hold():
            with deck_store.deck_lock():
                entered.set()
                release.wait(10)

        holder = threading.Thread(target=hold)
        holder.start()
        try:
            self.assertTrue(entered.wait(5))
            with mock.patch.object(deck_store, "LOCK_TIMEOUT_S", 0.3):
                status, body = self.post("/api/decks/d/decide", {"item_id": "item-1", "action": "approve"})
                self.assertEqual((status, body["error"], body["detail"]), (503, "busy", "Deck occupé, réessayez."))
                status, body = self.post("/api/decks", {"title": "N", "items": ["a"]})
                self.assertEqual((status, body["error"]), (503, "busy"))
            conn = HTTPConnection("127.0.0.1", self.httpd.server_address[1], timeout=5)
            conn.request("GET", "/api/decks/d")
            self.assertEqual(conn.getresponse().status, 200)
            conn.close()
        finally:
            release.set()
            holder.join()

    def test_storage_unavailable_returns_500_json(self):
        # Verrou impossible à prendre : le serveur répond 500 JSON storage_error (reset/delete HTTP arrivent au lot 2).
        with mock.patch.object(deck_store, "fcntl", mock.Mock(flock=mock.Mock(side_effect=OSError("io")),
                                                              LOCK_EX=2, LOCK_NB=4, LOCK_UN=8)):
            status, body = self.post("/api/decks", {"title": "N", "items": ["a"]})
        self.assertEqual((status, body["error"], body["detail"]), (500, "storage_error", "Stockage indisponible."))


if __name__ == "__main__":
    unittest.main()
