#!/usr/bin/env python3
"""quick-pick CLI — Outil d'administration et d'interfaçage agent pour les decks."""
import argparse
import json
import sys
from deck_store import (
    DeckError,
    delete_deck,
    find_deck_state,
    list_available_decks,
    load_deck,
    reset_deck,
    save_deck,
)
from deck_summary import compute_deck_summary

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


def build_deck_payload(deck_id, title, description, category, template_name, items, guidelines="", custom_actions=None):
    if custom_actions and isinstance(custom_actions, list) and len(custom_actions) >= 2:
        actions = custom_actions
    else:
        actions = ACTION_TEMPLATES.get(template_name, ACTION_TEMPLATES["triage"])
    formatted_items = []
    for item in items:
        formatted_items.append({
            "id": item["id"],
            "title": item["title"],
            "badges": item.get("badges", []),
            "bullets": item.get("bullets", []),
            "description": item.get("description", ""),
            "status": "pending",
            "chosen_action": None,
            "recommended_action": item.get("recommended_action"),
            "decided_at": None,
        })
    return {
        "id": deck_id,
        "title": title,
        "description": description,
        "guidelines": guidelines,
        "category": category,
        "default_actions": actions,
        "items": formatted_items,
    }


def handle_create(args):
    if args.items_file == "-":
        raw = sys.stdin.read()
    else:
        with open(args.items_file, "r", encoding="utf-8") as handle:
            raw = handle.read()
    items = json.loads(raw)
    if not isinstance(items, list):
        raise DeckError("Le fichier d'items doit contenir un tableau JSON")
    if not items:
        raise DeckError("Le tableau d'items ne peut pas être vide")

    seen_ids = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise DeckError(f"Item #{index+1} invalide (doit être un objet JSON)")
        item_id = str(item.get("id") or "").strip()
        item_title = str(item.get("title") or "").strip()
        if not item_id:
            raise DeckError(f"Item #{index+1} sans identifiant 'id' valide")
        if not item_title:
            raise DeckError(f"Item '{item_id}' sans titre 'title' valide")
        if item_id in seen_ids:
            raise DeckError(f"Identifiant d'item en double : '{item_id}'")
        seen_ids.add(item_id)

    custom_actions = None
    if getattr(args, "actions_file", None):
        with open(args.actions_file, "r", encoding="utf-8") as act_handle:
            loaded_acts = json.load(act_handle)
        if not isinstance(loaded_acts, list) or len(loaded_acts) < 2:
            raise DeckError("Le fichier d'actions doit contenir un tableau JSON d'au moins 2 actions")
        for a_idx, act in enumerate(loaded_acts):
            if not isinstance(act, dict) or not act.get("id") or not act.get("label"):
                raise DeckError(f"Action #{a_idx+1} invalide (doit contenir 'id' et 'label')")
        custom_actions = loaded_acts

    deck = build_deck_payload(
        args.id,
        args.title,
        args.description or "",
        args.category or "GÉNÉRAL",
        args.template,
        items,
        guidelines=getattr(args, "guidelines", "") or "",
        custom_actions=custom_actions,
    )
    save_deck(args.id, deck)
    print(f"Deck créé avec succès : {args.id} ({len(items)} items)")


def handle_list(_args):
    decks = list_available_decks()
    print(json.dumps(decks, ensure_ascii=False, indent=2))


def handle_status(args):
    deck = load_deck(args.id)
    state = find_deck_state(deck)
    print(json.dumps(state, ensure_ascii=False, indent=2))


def handle_summary(args):
    deck = load_deck(args.id)
    summary = compute_deck_summary(deck)
    if getattr(args, "format", "json") == "md":
        lines = [
            f"# Synthèse Quick-Pick : {summary.get('title', args.id)}",
            "",
            f"- **Deck ID** : `{summary.get('deck_id')}`",
            f"- **Progression** : {summary.get('total_decided')}/{summary.get('total_items')} décidés",
            f"- **Temps total** : {summary.get('elapsed_seconds')}s",
            "",
            "## Répartition des choix",
        ]
        for act_id, count in summary.get("actions_breakdown", {}).items():
            lines.append(f"- **{act_id}** : {count}")
        lines.append("")
        lines.append("## Détail des décisions")
        entries = summary.get("entries", [])
        if not entries:
            lines.append("- *(Aucune décision prise)*")
        for entry in entries:
            label = entry.get("action_label") or entry.get("chosen_action")
            comment = f" — *« {entry['comment']} »*" if entry.get("comment") else ""
            lines.append(f"- [{label}] **{entry.get('title')}**{comment}")
        print("\n".join(lines))
    else:
        print(json.dumps(summary, ensure_ascii=False, indent=2))


def handle_reset(args):
    deck = reset_deck(args.id)
    print(f"Deck réinitialisé avec succès : {args.id} ({len(deck.get('items', []))} items remis en attente)")


def handle_delete(args):
    delete_deck(args.id)
    print(f"Deck supprimé avec succès : {args.id}")


def handle_classifier(args):
    from classifier_proxy import test_external_classifier
    try:
        code, reachable, msg = test_external_classifier(args.endpoint, args.api_key)
        if reachable:
            print(f"✅ {msg}")
        else:
            print(f"❌ {msg}", file=sys.stderr)
            sys.exit(1)
    except Exception as err:
        print(f"❌ Erreur : {err}", file=sys.stderr)
        sys.exit(1)


def build_parser():
    parser = argparse.ArgumentParser(description="Gestion CLI des decks quick-pick")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_p = subparsers.add_parser("create", help="Créer un nouveau deck")
    create_p.add_argument("--id", required=True, help="Identifiant unique du deck")
    create_p.add_argument("--title", required=True, help="Titre visible du deck")
    create_p.add_argument("--description", default="", help="Description courte")
    create_p.add_argument("--guidelines", default="", help="Consignes et critères optionnels d'arbitrage")
    create_p.add_argument("--category", default="GÉNÉRAL", help="Catégorie (ex: AUDIT, DOCTRINE)")
    create_p.add_argument("--template", choices=list(ACTION_TEMPLATES.keys()), default="triage")
    create_p.add_argument("--actions-file", default=None, help="Fichier JSON d'actions personnalisées (remplace --template)")
    create_p.add_argument("--items-file", required=True, help="Fichier JSON d'items (ou '-' pour stdin)")
    create_p.set_defaults(func=handle_create)

    list_p = subparsers.add_parser("list", help="Lister les decks disponibles")
    list_p.set_defaults(func=handle_list)

    status_p = subparsers.add_parser("status", help="État courant d'un deck")
    status_p.add_argument("id", help="Identifiant du deck")
    status_p.set_defaults(func=handle_status)

    summary_p = subparsers.add_parser("summary", help="Résumé des décisions prises")
    summary_p.add_argument("id", help="Identifiant du deck")
    summary_p.add_argument("--format", choices=["json", "md"], default="json", help="Format de sortie (json ou md)")
    summary_p.set_defaults(func=handle_summary)

    reset_p = subparsers.add_parser("reset", help="Réinitialiser toutes les décisions d'un deck")
    reset_p.add_argument("id", help="Identifiant du deck")
    reset_p.set_defaults(func=handle_reset)

    delete_p = subparsers.add_parser("delete", help="Supprimer un deck existant")
    delete_p.add_argument("id", help="Identifiant du deck")
    delete_p.set_defaults(func=handle_delete)

    clf_p = subparsers.add_parser("classifier", help="Tester la connexion à un classifieur externe")
    clf_p.add_argument("--endpoint", required=True, help="URL de l'endpoint du classifieur")
    clf_p.add_argument("--api-key", default="", help="Clé API / Bearer Token optionnel")
    clf_p.set_defaults(func=handle_classifier)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except (DeckError, json.JSONDecodeError, OSError) as err:
        print(f"Erreur quick-pick CLI : {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
