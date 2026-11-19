import contextlib
import datetime
import json
import os
import re
import shutil
import sys
import threading
import time

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows: in-process RLock only
    fcntl = None

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


class StorageError(Exception):
    """Erreur de stockage (verrou, instantané) : pas une erreur de validation."""

    http_status = 500
    code = "storage_error"
    detail = "Stockage indisponible."

    def __init__(self, message=None):
        super().__init__(message or self.detail)


class DeckBusyError(StorageError):
    http_status = 503
    code = "busy"
    detail = "Deck occupé, réessayez."


class SnapshotError(StorageError):
    http_status = 500
    code = "snapshot_failed"
    detail = "Copie de sécurité impossible, rien n'a été modifié."


class LockUnavailableError(StorageError):
    http_status = 500
    code = "storage_error"
    detail = "Stockage indisponible."


class DeckExistsError(DeckError):
    """Le deck demandé existe déjà : jamais d'écrasement silencieux."""


DECK_ID_REGEX = re.compile(r"^[a-zA-Z0-9_\-]{1,128}$")

LOCK_FILENAME = ".quick-pick.lock"
HISTORY_DIRNAME = ".history"
LOCK_TIMEOUT_S = 5
LOCK_POLL_S = 0.05
HISTORY_KEEP = 10
VERSION_REGEX = re.compile(r"^[0-9]{8}T[0-9]{12}Z-[a-z]+$")

_PROCESS_LOCK = threading.RLock()
_LOCK_STATE = threading.local()


@contextlib.contextmanager
def deck_lock():
    """Verrou exclusif sur tout le dossier des decks, ré-entrant par thread.

    Seul le niveau le plus extérieur prend le RLock du processus puis un flock sur
    <DECKS_DIR>/.quick-pick.lock (partagé avec les autres processus : CLI, serveur).
    Une seule borne d'attente (LOCK_TIMEOUT_S) pour l'ensemble. Sans fcntl : RLock seul.
    """
    depth = getattr(_LOCK_STATE, "depth", 0)
    if depth:
        _LOCK_STATE.depth = depth + 1
        try:
            yield
        finally:
            _LOCK_STATE.depth -= 1
        return
    deadline = time.monotonic() + LOCK_TIMEOUT_S
    if not _PROCESS_LOCK.acquire(timeout=LOCK_TIMEOUT_S):
        raise DeckBusyError()
    handle = None
    try:
        if fcntl is not None:
            try:
                os.makedirs(DECKS_DIR, exist_ok=True)
                handle = open(os.path.join(DECKS_DIR, LOCK_FILENAME), "a")
            except OSError as err:
                raise LockUnavailableError(f"Stockage indisponible : {err}")
            while True:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except (BlockingIOError, PermissionError):
                    if time.monotonic() >= deadline:
                        raise DeckBusyError()
                    time.sleep(LOCK_POLL_S)
                except OSError as err:
                    raise LockUnavailableError(f"Stockage indisponible : {err}")
        _LOCK_STATE.depth = 1
        try:
            yield
        finally:
            _LOCK_STATE.depth = 0
    finally:
        if handle is not None:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
            handle.close()
        _PROCESS_LOCK.release()

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
    try:
        with open(file_path, "r", encoding="utf-8") as handle:
            deck_data = json.load(handle)
    except FileNotFoundError:
        raise DeckError(f"Deck introuvable : {deck_id}")
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
    tmp_path = f"{file_path}.{os.getpid()}.{threading.get_ident()}.tmp"
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


def validate_new_deck(title, items, template="triage", deck_id=None):
    """Validations pures (sans disque, sans verrou). Renvoie (titre, cartes, id demandé ou None)."""
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

    requested_id = None
    if deck_id is not None and str(deck_id).strip():
        requested_id = str(deck_id).strip()
        resolve_deck_path(requested_id)  # rejette les ids dangereux (traversée, espaces, ..)
    return clean_title, cards, requested_id


def create_deck(title, items, template="triage", deck_id=None):
    """Crée et persiste un deck depuis une liste brute (une ligne = une carte)."""
    clean_title, cards, requested_id = validate_new_deck(title, items, template, deck_id)
    with deck_lock():
        if requested_id is not None:
            target_id = requested_id
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


def _history_dir(deck_id):
    resolve_deck_path(deck_id)  # valide l'id avant tout chemin
    return os.path.join(DECKS_DIR, HISTORY_DIRNAME, deck_id.strip())


def _copy_snapshot(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copyfile(src, dst)


def list_history(deck_id):
    """Versions (sans .json) d'un deck, la plus récente d'abord."""
    history = _history_dir(deck_id)
    if not os.path.isdir(history):
        return []
    names = [n[:-5] for n in os.listdir(history) if n.endswith(".json") and VERSION_REGEX.match(n[:-5])]
    return sorted(names, reverse=True)


def snapshot_deck(deck_id, motif):
    """Copie brute du deck avant une opération destructrice. Renvoie la version, ou None si rien à copier.

    Un instantané identique octet pour octet au plus récent n'est pas recréé ; on garde les
    HISTORY_KEEP plus récents. Impossible -> SnapshotError (l'appelant refuse l'opération).
    """
    if not isinstance(motif, str) or not re.match(r"^[a-z]+$", motif):
        raise DeckError(f"Motif d'instantané invalide : {motif!r}")
    src = resolve_deck_path(deck_id)
    with deck_lock():
        if not os.path.isfile(src):
            return None
        history = _history_dir(deck_id)
        try:
            with open(src, "rb") as handle:
                current = handle.read()
            versions = list_history(deck_id)
            if versions:
                with open(os.path.join(history, versions[0] + ".json"), "rb") as handle:
                    if handle.read() == current:
                        return versions[0]
            now = datetime.datetime.now(datetime.timezone.utc)
            while True:
                version = now.strftime("%Y%m%dT%H%M%S") + f"{now.microsecond:06d}Z-{motif}"
                if not os.path.exists(os.path.join(history, version + ".json")):
                    break
                now += datetime.timedelta(microseconds=1)
            _copy_snapshot(src, os.path.join(history, version + ".json"))
            for old in list_history(deck_id)[HISTORY_KEEP:]:
                os.remove(os.path.join(history, old + ".json"))
        except OSError as err:
            raise SnapshotError(f"Copie de sécurité impossible ({err}), rien n'a été modifié.")
        return version


def restore_deck(deck_id, version):
    """Restaure une version de l'historique (aussi un deck supprimé). L'état courant est photographié avant."""
    if not isinstance(version, str) or not VERSION_REGEX.match(version):
        raise DeckError(f"Version invalide : {version!r}")
    version_path = os.path.join(_history_dir(deck_id), version + ".json")
    with deck_lock():
        try:
            with open(version_path, "r", encoding="utf-8") as handle:
                deck_data = json.load(handle)
        except FileNotFoundError:
            raise DeckError(f"Version introuvable : {deck_id} {version}")
        except (OSError, ValueError) as err:
            raise DeckError(f"Version illisible : {deck_id} {version} ({err})")
        if not isinstance(deck_data, dict) or deck_data.get("id") != deck_id.strip():
            raise DeckError(f"Version incohérente avec le deck {deck_id}")
        snapshot_deck(deck_id, "restore")
        save_deck(deck_id, deck_data)
    return deck_data


def delete_deck(deck_id):
    file_path = resolve_deck_path(deck_id)
    with deck_lock():
        if not os.path.isfile(file_path):
            raise DeckError(f"Deck introuvable : {deck_id}")
        snapshot_deck(deck_id, "delete")
        os.remove(file_path)


def reset_deck(deck_id):
    with deck_lock():
        deck = load_deck(deck_id)
        snapshot_deck(deck_id, "reset")
        for item in deck.get("items", []):
            item["status"] = "pending"
            item["chosen_action"] = None
            item["decided_at"] = None
            item["comment"] = None
            item.pop("decided_seq", None)
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
