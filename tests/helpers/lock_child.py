"""Child process for tests/test_deck_lock.py: decides one card of a deck, with or without deck_lock.

Usage: lock_child.py <decks_dir> <deck_id> <item_id> <mode: lock|nolock> <barrier_dir> <count>
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import deck_store  # noqa: E402


def decide(deck, item_id):
    for item in deck["items"]:
        if item["id"] == item_id:
            item["status"] = "decided"
            item["chosen_action"] = "approve"


def main():
    decks_dir, deck_id, item_id, mode, barrier_dir, count = sys.argv[1:7]
    deck_store.set_decks_dir(decks_dir)
    deck_store.LOCK_TIMEOUT_S = 60
    if mode == "lock":
        with deck_store.deck_lock():
            deck = deck_store.load_deck(deck_id)
            time.sleep(0.2)
            decide(deck, item_id)
            deck_store.save_deck(deck_id, deck)
        return
    deck = deck_store.load_deck(deck_id)
    with open(os.path.join(barrier_dir, item_id + ".ready"), "w") as handle:
        json.dump({}, handle)
    deadline = time.monotonic() + 30
    while len([n for n in os.listdir(barrier_dir) if n.endswith(".ready")]) < int(count):
        if time.monotonic() > deadline:
            sys.exit(3)
        time.sleep(0.02)
    decide(deck, item_id)
    deck_store.save_deck(deck_id, deck)


if __name__ == "__main__":
    main()
