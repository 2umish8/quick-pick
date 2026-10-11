from datetime import datetime, timezone
from deck_store import resolve_item_actions


def parse_decision_timestamp(value):
    """Parse a decision timestamp; naive values are assumed to be UTC, junk is dropped."""
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def compute_deck_summary(deck):
    items = deck.get("items", [])
    decided_items = [it for it in items if it.get("status") == "decided"]
    actions_count = {}
    timestamps = []
    recap_entries = []
    default_actions = deck.get("default_actions", [])

    for item in decided_items:
        action_id = item.get("chosen_action")
        actions_count[action_id] = actions_count.get(action_id, 0) + 1
        decided_at = item.get("decided_at")
        if decided_at:
            timestamps.append(decided_at)
        resolved = resolve_item_actions(default_actions, item)
        action_label = next(
            (a["label"] for a in resolved if a.get("id") == action_id),
            action_id or "(inconnu)",
        )
        recap_entries.append({
            "id": item.get("id"),
            "title": item.get("title"),
            "badges": item.get("badges", []),
            "chosen_action": action_id,
            "action_label": action_label,
            "comment": item.get("comment"),
            "decided_at": decided_at,
        })

    elapsed_seconds = 0
    stamps = [stamp for stamp in map(parse_decision_timestamp, timestamps) if stamp is not None]
    if len(stamps) >= 2:
        elapsed_seconds = max(0, int((max(stamps) - min(stamps)).total_seconds()))
    elif len(stamps) == 1:
        elapsed_seconds = 1

    return {
        "deck_id": deck.get("id"),
        "title": deck.get("title"),
        "total_items": len(items),
        "total_decided": len(decided_items),
        "pending_count": len(items) - len(decided_items),
        "is_completed": len(items) > 0 and len(decided_items) == len(items),
        "actions_breakdown": actions_count,
        "elapsed_seconds": elapsed_seconds,
        "entries": recap_entries,
    }
