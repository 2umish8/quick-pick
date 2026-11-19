import contextlib
import datetime
import errno
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
    """Erreur explicite de validation ou manipulation des decks.

    `code` (optionnel) est un identifiant stable relayé par l'API (ex. too_many_items).
    """

    def __init__(self, message="", code=None):
        super().__init__(message)
        self.code = code


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


_FLOCK_UNSUPPORTED = {errno.ENOLCK, errno.ENOTSUP, errno.EOPNOTSUPP}
_FLOCK_DISABLED = False


def _disable_flock(err):
    """flock refusé par le système de fichiers : repli sur le verrou de processus seul (un seul avertissement)."""
    global _FLOCK_DISABLED
    if not _FLOCK_DISABLED:
        _FLOCK_DISABLED = True
        print(f"[quick-pick] flock_unsupported err={err} fallback=process_lock_only", file=sys.stderr)


def _open_lock_file(path):
    """Descripteur du fichier de verrou ; tolère un fichier existant en lecture seule (flock marche sans écriture)."""
    try:
        return os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    except PermissionError:
        return os.open(path, os.O_RDONLY | os.O_CREAT)


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
        if fcntl is not None and not _FLOCK_DISABLED:
            try:
                os.makedirs(DECKS_DIR, exist_ok=True)
                handle = _open_lock_file(os.path.join(DECKS_DIR, LOCK_FILENAME))
            except OSError as err:
                raise LockUnavailableError(f"Stockage indisponible : {err}")
            while True:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except (BlockingIOError, PermissionError):
                    if time.monotonic() >= deadline:
                        raise DeckBusyError()
                    time.sleep(LOCK_POLL_S)
                except OSError as err:
                    if err.errno in _FLOCK_UNSUPPORTED:
                        _disable_flock(err)
                        os.close(handle)
                        handle = None
                        break
                    raise LockUnavailableError(f"Stockage indisponible : {err}")
        _LOCK_STATE.depth = 1
        try:
            yield
        finally:
            _LOCK_STATE.depth = 0
    finally:
        if handle is not None:
            try:
                fcntl.flock(handle, fcntl.LOCK_UN)
            except OSError:
                pass
            os.close(handle)
        _PROCESS_LOCK.release()

MAX_DECK_TITLE_LENGTH = 120
MAX_DECK_DESCRIPTION_LENGTH = 500
MAX_DECK_ITEMS = 200
MAX_ITEM_TITLE_LENGTH = 500
MAX_ITEM_DESCRIPTION_LENGTH = 2000
MAX_ITEM_BULLETS = 10
MAX_BULLET_LENGTH = 300
CARD_LIMITS = {
    "title": MAX_ITEM_TITLE_LENGTH,
    "description": MAX_ITEM_DESCRIPTION_LENGTH,
    "bullets": MAX_ITEM_BULLETS,
    "bullet": MAX_BULLET_LENGTH,
}

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
    except (OSError, ValueError) as err:  # ValueError : JSONDecodeError et UnicodeDecodeError
        raise DeckError(f"Deck illisible : {deck_id} ({err})")
    if not isinstance(deck_data, dict):
        raise DeckError(f"Format de deck invalide : {deck_id}")
    validate_items(deck_data.get("items", []), deck_id)
    return deck_data


def validate_items(items, deck_id):
    """Reject decks whose items miss the fields the API reads without a default.

    Read-time only: nothing is rewritten on disk, a broken deck raises DeckError (4xx) instead of
    crashing the request handler (5xx).
    """
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


def _clean_limited_text(value, label, max_length):
    """Texte optionnel : None -> "", sinon chaîne retirée des espaces et bornée (jamais de troncature)."""
    if value is None:
        return ""
    if not isinstance(value, str):
        raise DeckError(f"{label} invalide (texte attendu)")
    clean = value.strip()
    if len(clean) > max_length:
        raise DeckError(f"{label} trop longue (max {max_length} caractères)")
    return clean


def normalize_card(raw, position, limits=None):
    """Normalise une carte brute (chaîne ou objet) ; renvoie None pour une ligne vide (à sauter).

    Liste blanche : seuls title, description et bullets d'un objet sont lus (status, chosen_action,
    actions... sont ignorés). Aucun `id` n'est produit : l'appelant l'attribue.
    """
    limits = limits or CARD_LIMITS
    if isinstance(raw, str):
        if not raw.strip():
            return None  # ligne vide : sautée
        raw = {"title": raw}
    elif not isinstance(raw, dict):
        raise DeckError(f"Carte #{position} : format invalide")
    title = raw.get("title")
    if title is not None and not isinstance(title, str):
        raise DeckError(f"Carte #{position} : format invalide")
    title = (title or "").strip()
    if not title:
        raise DeckError(f"Carte #{position} : titre obligatoire")
    if len(title) > limits["title"]:
        raise DeckError(f"Carte #{position} trop longue (max {limits['title']} caractères)")
    description = _clean_limited_text(raw.get("description"), f"Carte #{position} : description", limits["description"])
    bullets_raw = raw.get("bullets")
    if bullets_raw is None:
        bullets_raw = []
    if not isinstance(bullets_raw, list):
        raise DeckError(f"Carte #{position} : bullets doit être une liste")
    if len(bullets_raw) > limits["bullets"]:
        raise DeckError(f"Carte #{position} : {limits['bullets']} bullets au maximum")
    bullets = []
    for bullet in bullets_raw:
        if not isinstance(bullet, str):
            raise DeckError(f"Carte #{position} : format invalide (chaque bullet doit être du texte)")
        text = bullet.strip()
        if len(text) > limits["bullet"]:
            raise DeckError(f"Carte #{position} : bullet trop long (max {limits['bullet']} caractères)")
        if text:
            bullets.append(text)
    return {
        "title": title,
        "description": description,
        "bullets": bullets,
        "status": "pending",
        "chosen_action": None,
        "decided_at": None,
    }


def _too_many_items():
    return DeckError(f"Maximum {MAX_DECK_ITEMS} cartes par deck", code="too_many_items")


def validate_new_deck(title, items, template="triage", deck_id=None, description=None):
    """Validations pures (sans disque, sans verrou). Renvoie (titre, cartes, id demandé ou None)."""
    clean_title = str(title or "").strip()
    if not clean_title:
        raise DeckError("Titre de deck obligatoire")
    if len(clean_title) > MAX_DECK_TITLE_LENGTH:
        raise DeckError(f"Titre trop long (max {MAX_DECK_TITLE_LENGTH} caractères)")
    _clean_limited_text(description, "Description", MAX_DECK_DESCRIPTION_LENGTH)
    if not isinstance(template, str) or template not in ACTION_TEMPLATES:
        raise DeckError(f"Modèle d'actions inconnu : {template!r}")
    if not isinstance(items, list):
        raise DeckError("La liste des cartes doit être un tableau de lignes")

    cards = []
    for position, raw in enumerate(items, start=1):
        card = normalize_card(raw, position)
        if card is not None:
            cards.append(card)
    if not cards:
        raise DeckError("Ajoutez au moins une carte à trancher")
    if len(cards) > MAX_DECK_ITEMS:
        raise _too_many_items()

    requested_id = None
    if deck_id is not None and str(deck_id).strip():
        requested_id = str(deck_id).strip()
        resolve_deck_path(requested_id)  # rejette les ids dangereux (traversée, espaces, ..)
    return clean_title, cards, requested_id


def create_deck(title, items, template="triage", deck_id=None, description=None):
    """Crée et persiste un deck depuis une liste brute (une ligne ou un objet par carte)."""
    clean_title, cards, requested_id = validate_new_deck(title, items, template, deck_id, description)
    clean_description = _clean_limited_text(description, "Description", MAX_DECK_DESCRIPTION_LENGTH)
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
            "description": clean_description,
            "category": "GÉNÉRAL",
            "default_actions": ACTION_TEMPLATES[template],
            "items": [dict(card, id=f"item-{index}") for index, card in enumerate(cards, start=1)],
        }
        save_deck(target_id, deck)
    return deck


def _history_dir(deck_id):
    resolve_deck_path(deck_id)  # valide l'id avant tout chemin
    return os.path.join(DECKS_DIR, HISTORY_DIRNAME, deck_id.strip())


def _copy_snapshot(src, dst):
    """Copie vers un temporaire (jamais un nom de version valide) puis os.replace : pas de version partielle."""
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = dst + ".tmp"
    try:
        shutil.copyfile(src, tmp)
        os.replace(tmp, dst)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


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


def add_items(deck_id, raw_items):
    """Ajoute des cartes (chaînes ou objets) à un deck existant, après instantané. Renvoie le deck."""
    with deck_lock():
        deck = load_deck(deck_id)
        if not isinstance(raw_items, list) or not raw_items:
            raise DeckError("Aucune carte à ajouter", code="empty_items")
        cards = []
        for position, raw in enumerate(raw_items, start=1):
            card = normalize_card(raw, position)
            if card is not None:
                cards.append(card)
        if not cards:
            raise DeckError("Aucune carte à ajouter", code="empty_items")
        items = deck.setdefault("items", [])
        if items is None:
            items = deck["items"] = []
        if len(items) + len(cards) > MAX_DECK_ITEMS:
            raise _too_many_items()
        snapshot_deck(deck_id, "items")
        used = {str(it.get("id")) for it in items}
        numbers = [int(m.group(1)) for m in (re.match(r"^item-([0-9]+)$", i) for i in used) if m]
        counter = max(numbers + [len(items)])
        for card in cards:
            counter += 1
            while f"item-{counter}" in used:
                counter += 1
            card_id = f"item-{counter}"
            used.add(card_id)
            items.append(dict(card, id=card_id))
        save_deck(deck_id, deck)
    return deck


def parse_decision_timestamp(value):
    """Parse a decision timestamp; naive values are assumed to be UTC, junk is dropped."""
    try:
        parsed = datetime.datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=datetime.timezone.utc)


def deck_progress(deck):
    """Avancement calculé (jamais stocké) d'un deck déjà validé par validate_items.

    is_completed : tous décidés (vrai pour un deck vide). completed_at : plus grand decided_at
    analysable (ISO UTC) quand le deck est terminé, sinon None.
    """
    items = deck.get("items") or []
    decided = [it for it in items if it.get("status") == "decided"]
    is_completed = len(decided) == len(items)
    completed_at = None
    if is_completed:
        stamps = [s for s in (parse_decision_timestamp(it.get("decided_at")) for it in decided) if s is not None]
        if stamps:
            completed_at = max(stamps).astimezone(datetime.timezone.utc).isoformat(timespec="seconds")
    return {"total": len(items), "decided": len(decided), "is_completed": is_completed, "completed_at": completed_at}


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
        except (ValueError, OSError) as err:
            print(f"[quick-pick] deck_read_error file={filename} err={err}", file=sys.stderr)
            continue
        if not (isinstance(deck, dict) and deck.get("id") and deck.get("title")):
            continue
        file_id = filename[:-len(".json")]
        entry = {
            "id": deck["id"],
            "title": deck["title"],
            "description": deck.get("description", ""),
            "category": deck.get("category", "GÉNÉRAL"),
            "invalid": False,
        }
        try:
            if deck["id"] != file_id or not DECK_ID_REGEX.match(file_id):
                raise DeckError(f"Identifiant incohérent avec le nom de fichier : {file_id}")
            validate_items(deck.get("items", []), file_id)
            progress = deck_progress(deck)
            entry.update(total=progress["total"], decided=progress["decided"], is_completed=progress["is_completed"])
        except DeckError:
            # Never expose the inner id of a broken deck: actions (delete) must hit this very file.
            entry.update(id=file_id, invalid=True, total=None, decided=None, is_completed=False)
        decks.append(entry)
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
    progress = deck_progress(deck)
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
        "is_completed": progress["is_completed"],
        "completed_at": progress["completed_at"],
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
