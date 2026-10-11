import json
import os
import re
import shutil
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DECKS_DIR = os.path.abspath(os.environ.get("QUICK_PICK_DATA_DIR", os.path.join(BASE_DIR, "data", "decks")))
EXAMPLES_DIR = os.path.join(BASE_DIR, "examples", "decks")


def set_decks_dir(path):
    global DECKS_DIR
    DECKS_DIR = os.path.abspath(path)


def get_decks_dir():
    return DECKS_DIR


def seed_example_decks():
    """Copy the bundled example decks into DECKS_DIR when it holds no deck yet.

    User decks are never deleted nor overwritten: seeding only happens on an
    empty decks directory, and any existing file is kept as is.
    """
    existing = os.listdir(DECKS_DIR) if os.path.isdir(DECKS_DIR) else []
    if any(name.endswith(".json") for name in existing):
        return []
    if not os.path.isdir(EXAMPLES_DIR):
        return []
    os.makedirs(DECKS_DIR, exist_ok=True)
    seeded = []
    for name in sorted(os.listdir(EXAMPLES_DIR)):
        if not name.endswith(".json"):
            continue
        target = os.path.join(DECKS_DIR, name)
        if os.path.exists(target):
            continue
        shutil.copyfile(os.path.join(EXAMPLES_DIR, name), target)
        seeded.append(name)
    if seeded:
        print(f"[quick-pick] example_decks_seeded count={len(seeded)} dir={DECKS_DIR}", file=sys.stderr)
    return seeded


class DeckError(Exception):
    """Erreur explicite de validation ou manipulation des decks."""


class DeckExistsError(DeckError):
    """Le deck demandé existe déjà : jamais d'écrasement silencieux."""


DECK_ID_REGEX = re.compile(r"^[a-zA-Z0-9_\-]{1,128}$")

MAX_DECK_TITLE_LENGTH = 120
MAX_DECK_ITEMS = 200
MAX_ITEM_TITLE_LENGTH = 500

# Modèles d'actions déclaratifs, cohérents avec SKILL.md et deck_cli.
ACTION_TEMPLATES = {
    "triage": [
        {"id": "approve", "label": "Conserver / Valider", "direction": "east", "key": "d", "color": "success"},
        {"id": "reject", "label": "Élaguer / Rejeter", "direction": "west", "key": "a", "color": "danger"},
        {"id": "review", "label": "À revoir / Modifier", "direction": "north", "key": "w", "color": "warning"},
    ],
    "binary": [
        {"id": "approve", "label": "Oui / Valider", "direction": "east", "key": "d", "color": "success"},
        {"id": "reject", "label": "Non / Rejeter", "direction": "west", "key": "a", "color": "danger"},
    ],
    "priority": [
        {"id": "now", "label": "Immédiat", "direction": "east", "key": "d", "color": "success"},
        {"id": "drop", "label": "Ignorer", "direction": "west", "key": "a", "color": "danger"},
        {"id": "later", "label": "Plus tard", "direction": "north", "key": "w", "color": "warning"},
    ],
}


def resolve_deck_path(deck_id):
    if not deck_id or not isinstance(deck_id, str):
        raise DeckError("Identifiant de deck manquant ou invalide")
    clean_id = deck_id.strip()
    if not DECK_ID_REGEX.match(clean_id):
        raise DeckError(f"Identifiant de deck suspect : {deck_id!r}")
    return os.path.join(DECKS_DIR, f"{clean_id}.json")


def load_deck(deck_id):
    file_path = resolve_deck_path(deck_id)
    if not os.path.isfile(file_path):
        raise DeckError(f"Deck introuvable : {deck_id}")
    with open(file_path, "r", encoding="utf-8") as handle:
        deck_data = json.load(handle)
    if not isinstance(deck_data, dict):
        raise DeckError(f"Format de deck invalide : {deck_id}")
    validate_items(deck_data.get("items"), deck_id)
    return deck_data


def validate_items(items, deck_id):
    """Reject decks whose items miss the fields the API reads without a default.

    Read-time only: nothing is rewritten on disk, a broken deck raises DeckError (4xx) instead of
    crashing the request handler (5xx).
    """
    if items is None:
        return
    if not isinstance(items, list):
        raise DeckError(f"Items de deck invalides : {deck_id} (tableau JSON attendu)")
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise DeckError(f"Item #{index + 1} invalide dans le deck {deck_id} (objet JSON attendu)")
        for field in ("id", "title"):
            if not str(item.get(field) or "").strip():
                raise DeckError(f"Item #{index + 1} sans '{field}' valide dans le deck {deck_id}")


def save_deck(deck_id, deck_data):
    file_path = resolve_deck_path(deck_id)
    os.makedirs(DECKS_DIR, exist_ok=True)
    tmp_path = file_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(deck_data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(tmp_path, file_path)


def deck_exists(deck_id):
    return os.path.isfile(resolve_deck_path(deck_id))


def _slugify_deck_id(title):
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:64].strip("-")
    return slug or "deck"


def _unique_deck_id(base_id):
    candidate, suffix = base_id, 2
    while deck_exists(candidate):
        candidate = f"{base_id}-{suffix}"
        suffix += 1
    return candidate


def create_deck(title, items, template="triage", deck_id=None):
    """Crée et persiste un deck depuis une liste brute (une ligne = une carte)."""
    clean_title = str(title or "").strip()
    if not clean_title:
        raise DeckError("Titre de deck obligatoire")
    if len(clean_title) > MAX_DECK_TITLE_LENGTH:
        raise DeckError(f"Titre trop long (max {MAX_DECK_TITLE_LENGTH} caractères)")
    if not isinstance(template, str) or template not in ACTION_TEMPLATES:
        raise DeckError(f"Modèle d'actions inconnu : {template!r}")
    if not isinstance(items, list):
        raise DeckError("La liste des cartes doit être un tableau de lignes")

    cards = []
    for position, raw in enumerate(items, start=1):
        line = str(raw or "").strip()
        if not line:
            continue
        if len(line) > MAX_ITEM_TITLE_LENGTH:
            raise DeckError(f"Carte #{position} trop longue (max {MAX_ITEM_TITLE_LENGTH} caractères)")
        cards.append(line)
    if not cards:
        raise DeckError("Ajoutez au moins une carte à trancher")
    if len(cards) > MAX_DECK_ITEMS:
        raise DeckError(f"Maximum {MAX_DECK_ITEMS} cartes par deck")

    if deck_id is not None and str(deck_id).strip():
        target_id = str(deck_id).strip()
        resolve_deck_path(target_id)  # rejette les ids dangereux (traversée, espaces, ..)
        if deck_exists(target_id):
            raise DeckExistsError(f"Un deck nommé '{target_id}' existe déjà")
    else:
        target_id = _unique_deck_id(_slugify_deck_id(clean_title))

    deck = {
        "id": target_id,
        "title": clean_title,
        "description": "",
        "category": "GÉNÉRAL",
        "default_actions": ACTION_TEMPLATES[template],
        "items": [
            {"id": f"item-{index}", "title": line, "status": "pending", "chosen_action": None, "decided_at": None}
            for index, line in enumerate(cards, start=1)
        ],
    }
    save_deck(target_id, deck)
    return deck


def delete_deck(deck_id):
    file_path = resolve_deck_path(deck_id)
    if not os.path.isfile(file_path):
        raise DeckError(f"Deck introuvable : {deck_id}")
    os.remove(file_path)


def reset_deck(deck_id):
    deck = load_deck(deck_id)
    for item in deck.get("items", []):
        item["status"] = "pending"
        item["chosen_action"] = None
        item["decided_at"] = None
        item["comment"] = None
    save_deck(deck_id, deck)
    return deck


def list_available_decks():
    if not os.path.isdir(DECKS_DIR):
        return []
    decks = []
    for filename in sorted(os.listdir(DECKS_DIR)):
        if not filename.endswith(".json"):
            continue
        filepath = os.path.join(DECKS_DIR, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as handle:
                deck = json.load(handle)
            if isinstance(deck, dict) and deck.get("id") and deck.get("title"):
                decks.append({
                    "id": deck["id"],
                    "title": deck["title"],
                    "description": deck.get("description", ""),
                    "category": deck.get("category", "GÉNÉRAL"),
                })
        except (json.JSONDecodeError, OSError) as err:
            print(f"[quick-pick] deck_read_error file={filename} err={err}", file=sys.stderr)
    return decks


def resolve_item_actions(default_actions, item):
    if item.get("actions") and isinstance(item["actions"], list):
        return item["actions"]
    actions = [dict(action) for action in default_actions]
    removed_ids = set(item.get("remove_actions") or [])
    if removed_ids:
        actions = [a for a in actions if a.get("id") not in removed_ids]
    additions = item.get("add_actions") or []
    if isinstance(additions, list):
        actions.extend(additions)
    return actions


def prepare_item_payload(deck, item):
    actions = resolve_item_actions(deck.get("default_actions", []), item)
    return {
        "id": item["id"],
        "title": item["title"],
        "badges": item.get("badges", []),
        "bullets": item.get("bullets", []),
        "description": item.get("description", ""),
        "recommended_action": item.get("recommended_action"),
        "actions": actions,
    }


def find_deck_state(deck):
    items = deck.get("items", [])
    default_actions = deck.get("default_actions", [])
    pending = [it for it in items if it.get("status") != "decided"]
    decided = [it for it in items if it.get("status") == "decided"]

    current_item = prepare_item_payload(deck, pending[0]) if pending else None
    upcoming_items = [prepare_item_payload(deck, it) for it in pending[1:4]]
    pending_list = [{"id": it["id"], "title": it["title"], "badges": it.get("badges", [])} for it in pending]

    decided_list = []
    for it in decided:
        act_id = it.get("chosen_action")
        actions = resolve_item_actions(default_actions, it)
        label = next((a["label"] for a in actions if a.get("id") == act_id), act_id or "")
        decided_list.append({
            "id": it.get("id"),
            "title": it.get("title"),
            "badges": it.get("badges", []),
            "chosen_action": act_id,
            "action_label": label,
            "comment": it.get("comment"),
            "decided_at": it.get("decided_at"),
        })

    return {
        "id": deck.get("id"),
        "title": deck.get("title"),
        "description": deck.get("description", ""),
        "category": deck.get("category", ""),
        "guidelines": deck.get("guidelines", ""),
        "is_completed": current_item is None,
        "current_item": current_item,
        "upcoming_items": upcoming_items,
        "pending_items": pending_list,
        "decided_items": decided_list,
        "has_next": len(pending) > 1,
        "has_third": len(pending) > 2,
        "can_undo": len(decided) > 0,
        "decided_count": len(decided),
        "pending_count": len(pending),
    }
