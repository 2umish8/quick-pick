---
name: quick-pick
description: "Use when you need a human to arbitrate 4+ independent items (backlog, rules, skills, PRs, options) as a swipe-card deck instead of a long chat questionnaire; not for a single blocking question."
version: 2.2.1
license: MIT
platforms: [linux, macos, windows]
category: orchestration
metadata:
  tags: [triage, arbitration, decision, review, swipe, mobile-first, async]
---

# Quick-Pick : arbitrages par cartes

L'agent prépare un deck, l'humain le tranche en swipant (téléphone) ou au clavier (PC), l'agent lit les décisions et reprend. Chaîne complète : **créer → prévenir → attendre → lire → agir → signaler la prise en compte**.

## Quand l'utiliser
- 4 éléments indépendants ou plus à faire trancher : tri de backlog ou de tickets, règles à garder / modifier / supprimer, skills ou dépendances à purger, options d'architecture, PRs.
- Pas pour une question unique et bloquante : la poser directement.
- Jamais de secret ni de jeton dans les cartes : les decks sont des fichiers JSON en clair (et leurs sauvegardes aussi).

## Où lancer
Les commandes `deck_cli.py` se lancent **depuis le dossier du dépôt** (`cd <dépôt> && python3 deck_cli.py …`) : hors de ce dossier, le fichier est introuvable. `QUICK_PICK_DATA_DIR` change le dossier des decks (utile pour tester sur un dossier temporaire sans toucher aux vrais decks).
L'API de l'agent est sur `http://127.0.0.1:8791` (port par défaut) : réservée à l'agent. **Ce lien-là ne se donne jamais à l'humain** : il reçoit l'URL publique de l'instance (celle que la règle d'environnement de l'agent prescrit pour les outils servis), suivie de `/#<deck_id>`.

## 1. Créer un deck

CLI (recommandé) :
```bash
python3 deck_cli.py create --id mon-arbitrage --title "Titre explicite" \
  --items-file items.json            # ou --items-file - pour lire stdin
```
Options : `--description`, `--guidelines` (critères d'arbitrage), `--category`, `--template triage|binary|priority`, `--actions-file` (remplace le template ; liste d'au moins 2 actions `{id, label}`).
- `--id` : lettres, chiffres, `_` et `-`, 128 caractères max. Il doit être neuf : un `id` existant sort en code 1 (« supprimez-le d'abord avec delete »).
- `items.json` : liste de `{ "id", "title", "description"?, "bullets"?, "badges"? }` ; `id` et `title` obligatoires par carte (`badges` : `[{label, variant}]`).
- Le CLI ne limite pas le nombre de cartes ; viser 200 maximum comme l'interface et l'API.

API HTTP (`POST /api/decks`, JSON) : `title`, `items` (lignes ; ou objets `{title, description, bullets}`), `template`, `id`?, `description`?. 200 cartes max, 500 caractères par titre. **`category`, `guidelines` et `badges` y sont ignorés** (utiliser le CLI). Sans `id`, il est dérivé du titre et un doublon donne `mon-arbitrage-2` : **lire `deck_id` dans la réponse `201`**, pas le deviner. Avec un `id` explicite déjà pris : `409`.
Dans l'interface, une ligne `titre :: détail` crée une carte avec description.

Actions par défaut (polarité et touches constantes) : Est `d` Conserver / Valider · Ouest `a` Élaguer / Rejeter · Nord `w` À revoir / Modifier · Sud `s` option spéciale. `binary` : Oui / Non. `priority` : Immédiat (`now`) / Ignorer (`drop`) / Plus tard (`later`). Les valeurs de `chosen_action` sont `approve` / `reject` / `review` (triage), `now` / `drop` / `later` (priority), `approve` / `reject` (binary).

## 2. Prévenir l'humain
Dire où il tranche, avec l'URL publique et le deck : « Deck prêt : <URL_PUBLIQUE>/#mon-arbitrage ». Il peut ajouter un commentaire par carte, différer (`Echap` ou `x`), annuler (`Ctrl+Z`) et, depuis l'écran de fin, **revenir à la dernière carte**. **L'agent ne tranche jamais à la place de l'humain** (la route `decide` existe pour l'interface, pas pour l'agent).

## 3. Attendre, lire, agir
```bash
python3 deck_cli.py status mon-arbitrage           # is_completed, pending_count, decided_count
python3 deck_cli.py wait mon-arbitrage --timeout 60
python3 deck_cli.py summary mon-arbitrage --format md   # ou --format json
```
- `wait` sonde toutes les 2 s et affiche une ligne JSON `{deck_id, is_completed, decided, total}`. Sortie **0** terminé, **3** délai écoulé (normal : relancer), **1** deck absent ou stockage en erreur. Garder `--timeout` court (≈ 60 s).
- **Attente longue** : si l'humain n'a pas fini après ~1 h, ne pas boucler : le deck persiste, noter la reprise (handoff) et passer à autre chose.
- `summary` : ventilation avec libellés, « Temps actif » ; en JSON `active_seconds`, `completed_at`, `actions_breakdown_labeled`.
- Un deck terminé se laisse en place (l'humain peut y revenir) ; `delete` seulement sur demande.

## 4. Remise à zéro, ajout, sauvegardes
L'interface propose « Remettre à zéro », « Supprimer » et « Ajouter des cartes » (`POST /api/decks/<id>/reset|delete|items`) ; le CLI a `reset` et `delete`. Avant chacune de ces opérations (et avant `restore`), le deck est copié dans `<dossier des decks>/.history/<id>/` (10 versions les plus récentes). **C'est l'agent qui restaure**, l'humain n'a aucune commande à taper :
```bash
python3 deck_cli.py history mon-arbitrage              # la plus récente d'abord
python3 deck_cli.py restore mon-arbitrage <version>    # aussi pour un deck supprimé
```
Une version est l'état **avant** l'opération indiquée par son suffixe (`-reset`, `-delete`, `-items`, `-restore`) ; un `restore` crée lui-même une copie.
Le serveur sème des decks d'exemple au démarrage si le dossier est vide ; le CLI, non.

## 5. Suggestions IA (optionnel)
Le classifieur ajoute des badges de pré-qualification, réglé dans l'interface (bouton « réglages », engrenage) : endpoint, modèle, clé de l'humain. **Ne jamais passer une clé en argument** : `QUICK_PICK_API_KEY` ou `--api-key-stdin` pour un test (`deck_cli.py classifier --endpoint <URL>`). Un endpoint local ou privé exige `QUICK_PICK_ALLOW_PRIVATE_ENDPOINTS=1`. Détail de ce que stocke le navigateur et de ce que voit le serveur : README, section « Where your API key lives ».

## 6. Signaler la prise en compte (étape finale obligatoire)
Une fois la décision **réellement appliquée** (pas avant), l'agent le dit à l'humain dans le deck :
```bash
python3 deck_cli.py ack --id mon-arbitrage --agent <ton-nom> --note "ce qui a été fait, en une phrase"
```
`--note` est facultative (280 caractères au plus, `--agent` 40). L'accueil range alors le deck dans « Pris en compte » avec ton nom, la date et la note ; sans cette étape il reste dans « Tranché, en attente de l'agent » et l'humain croit que rien n'a été fait. Code 1 si le deck n'est pas terminé ou n'a aucune carte. Si l'humain change une décision après coup (annulation, nouvelle décision, cartes ajoutées, remise à zéro), la prise en compte devient périmée (« modifié depuis la prise en compte ») : relire la synthèse, ré-appliquer, puis relancer `ack`. Même route en HTTP : `POST /api/decks/<id>/ack` (`{"agent": "...", "note": "..."}`).
