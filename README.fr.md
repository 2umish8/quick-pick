# Quick-Pick

**Votre agent IA vous pose 20 questions d'un coup, sous forme de cartes à swiper. Vous tranchez, il reprend vos décisions.** Fini le mur de texte dans les chats avec les LLM.

[English version](README.md)

<!-- TODO GIF: 10 s, swipe mobile -> clavier -> deck_cli summary -->
![Démo Quick-Pick : swipe sur mobile, clavier sur desktop, puis deck_cli summary](docs/demo.gif)

## Pourquoi

Quand on travaille avec des agents de code et des assistants (Claude, Cursor, Hermes, OpenCode, Aider…), ils ont souvent besoin de beaucoup de petites décisions : garder ou retirer cette dépendance, valider ou reformuler cette règle, maintenant ou plus tard pour ce ticket. Dans un chat, ça devient un long message avec 20 questions à choix multiples, lent et pénible à remplir.

Quick-Pick transforme ces questions en pile de cartes. L'agent crée le deck et vous envoie un lien ; vous tranchez une carte à la fois (swipe sur mobile, touches sur desktop) ; l'agent relit ensuite la synthèse de vos décisions et commentaires. L'outil sert aussi seul pour trier backlogs, relectures de code, idées ou audits, avec des suggestions IA optionnelles (BYOK, votre propre clé).

## Points forts

- **Zéro dépendance** : 100 % bibliothèque standard Python (`server.py`). Aucun `pip install`, aucun bundler, démarrage instantané.
- **Mobile d'abord, clavier sur desktop** : swipe tactile fluide sur smartphone (`passive: false`), flèches et touches dédiées (`a` / `d` / `w`) sur desktop.
- **BYOK intégré** : compatible avec toute API de type OpenAI (OpenAI `gpt-4o-mini`, Ollama local `llama3.2`, Groq, OpenRouter) et avec des webhooks de scoring personnalisés.
- **Stockage JSON simple** : les decks sont des fichiers JSON lisibles, manipulables par des scripts ou des agents IA (`deck_cli.py`).
- **Pensé pour trier sans stress** : pas de compteur anxiogène pendant le tri, historique des décisions consultable à tout moment, champ note par carte et annulation complète (`Ctrl+Z`).

## Démarrage rapide

### Option A : en local (zéro dépendance)

```bash
git clone https://github.com/2umish8/quick-pick.git
cd quick-pick
python3 server.py
```

Ouvrez **`http://localhost:8791`** dans votre navigateur.

### Option B : Docker Compose (recommandé en auto-hébergement)

```bash
docker compose up -d
```

Le service tourne sur le port `8791`, avec persistance des données dans `./data/decks`.

## Raccourcis clavier

| Touche | Action |
|---|---|
| `d` / `→` | Action de droite (ex. garder / valider) |
| `a` / `←` | Action de gauche (ex. élaguer / rejeter) |
| `w` / `↑` | Action du haut (ex. à revoir / plus tard) |
| `x` / `Échap` | Passer la carte |
| `c` | Aller au champ note |
| `Ctrl+Z` / `Cmd+Z` | Annuler |

Les actions exactes dépendent du deck (voir [format d'un deck](#format-dun-deck-datadecksidjson)).

## Variables d'environnement

| Variable | Défaut | Description |
|---|---|---|
| `QUICK_PICK_HOST` | `127.0.0.1` (`0.0.0.0` dans Docker) | Adresse d'écoute du serveur |
| `QUICK_PICK_PORT` | `8791` | Port HTTP |
| `QUICK_PICK_DATA_DIR` | `./data/decks` | Dossier de stockage des fichiers JSON de decks |
| `QUICK_PICK_ALLOW_PRIVATE_ENDPOINTS` | `1` | Autoriser le proxy IA à appeler des endpoints locaux ou privés (ex. Ollama sur `127.0.0.1:11434`) |

## Assistance IA et BYOK (votre propre clé)

Quick-Pick n'impose aucun modèle payant ou propriétaire. Cliquez sur l'icône **⚙️** dans l'en-tête pour configurer les suggestions :

1. **Protocole OpenAI / Ollama / Groq** :
   - **URL de base** : `https://api.openai.com/v1`, `http://localhost:11434/v1` ou `https://api.groq.com/openai/v1`
   - **Modèle** : `gpt-4o-mini`, `llama3.2`, `mistral`, etc.
   - **Clé API** : votre clé privée. Elle est enregistrée en clair dans le `localStorage` de votre navigateur et n'est pas stockée par le serveur. Elle est en revanche envoyée à votre serveur Quick-Pick à chaque test et à chaque demande de suggestion, et le serveur la transmet en en-tête `Authorization: Bearer` à l'endpoint configuré. Ne la saisissez que sur une instance Quick-Pick que vous contrôlez.
2. **Webhook / API personnalisée** :
   - Renseignez l'URL de votre endpoint de scoring. Il reçoit le payload `{ id, title, description, bullets, candidate_actions }`.

## Utiliser Quick-Pick avec des agents IA

Quick-Pick résout le problème du **« mur de texte »** dans les chats avec les LLM (Hermes, Claude, Cursor, OpenCode, Aider). Au lieu de poser 20 questions à choix multiples dans un message, l'agent prépare une pile de cartes, donne le lien à l'humain, puis récupère les décisions :

1. **L'agent crée le deck** :
   ```bash
   # L'agent peut envoyer du JSON directement au CLI
   cat << 'EOF' | python3 deck_cli.py create --id "pr-review" --title "Revue PR #42" --items-file -
   [
     {
       "id": "item-1",
       "title": "Supprimer la dépendance legacy XYZ",
       "bullets": ["Non maintenue depuis 2 ans", "Remplaçable par 10 lignes natives"]
     }
   ]
   EOF
   ```
2. **L'agent prévient l'humain** :
   > *« J'ai préparé 5 décisions sur http://localhost:8791/#pr-review. Fais un swipe rapide quand tu as 30 secondes. »*
3. **L'agent récupère les décisions** :
   ```bash
   python3 deck_cli.py summary pr-review --format md
   ```
   L'agent récupère les arbitrages et les commentaires, puis reprend son travail de façon asynchrone, sans bloquer la conversation.
4. **Skill agent** : le fichier [`skills/quick-pick/SKILL.md`](skills/quick-pick/SKILL.md) s'importe directement dans votre environnement d'agents (`~/.agents/skills/quick-pick/`).

## Ligne de commande (`deck_cli.py`)

Les scripts et les agents IA peuvent piloter les decks en ligne de commande :

```bash
# 1. Créer un deck depuis un fichier JSON d'items
python3 deck_cli.py create \
  --id "sprint-42" \
  --title "Triage sprint 42" \
  --category "PRODUIT" \
  --template "triage" \
  --items-file items.json

# Templates intégrés : triage (3 voies), binary (oui/non), priority (immédiat/plus tard/ignorer)
# Actions sur mesure : option --actions-file actions.json
# Optionnel : --description, --guidelines (critères d'arbitrage affichés à l'humain)

# 2. Lister les decks
python3 deck_cli.py list

# 3. Consulter l'état courant (progression)
python3 deck_cli.py status sprint-42

# 4. Obtenir la synthèse des décisions (Markdown ou JSON, JSON par défaut)
python3 deck_cli.py summary sprint-42 --format md

# 5. Réinitialiser un deck
python3 deck_cli.py reset sprint-42

# 6. Supprimer un deck
python3 deck_cli.py delete sprint-42

# 7. Tester la connexion à un classifieur externe
python3 deck_cli.py classifier --endpoint http://localhost:11434/v1
```

## Format d'un deck (`data/decks/<id>.json`)

Chaque deck est un document JSON autonome :

```json
{
  "id": "mon-arbitrage",
  "title": "Titre du sujet",
  "description": "Description contextuelle",
  "category": "AUDIT",
  "default_actions": [
    { "id": "approve", "label": "Garder", "direction": "east", "key": "d", "color": "success" },
    { "id": "reject", "label": "Élaguer", "direction": "west", "key": "a", "color": "danger" },
    { "id": "review", "label": "Reformuler", "direction": "north", "key": "w", "color": "warning" }
  ],
  "items": [
    {
      "id": "item-1",
      "title": "Nom de l'élément",
      "badges": [{ "label": "URGENT", "variant": "warning" }],
      "bullets": ["Point clé 1", "Point clé 2"],
      "description": "Détail optionnel",
      "status": "pending",
      "chosen_action": null,
      "comment": null,
      "decided_at": null
    }
  ]
}
```

## Sécurité et déploiement en production

Quick-Pick est conçu pour un usage mono-utilisateur ou en équipe interne :

- Il n'y a pas d'authentification intégrée. Pour une exposition sur Internet, placez-le derrière un reverse proxy avec authentification (Caddy avec Basic Auth, Traefik, Authelia, Cloudflare Access) ou sur un réseau privé comme Tailscale.
- Toute personne qui peut joindre le serveur peut aussi utiliser son proxy IA (`/api/classifier/*`). Avec `QUICK_PICK_ALLOW_PRIVATE_ENDPOINTS=1` (valeur par défaut), cela inclut les adresses locales et privées ; passez-la à `0` si vous n'utilisez pas de modèle local.
- En-têtes de sécurité activés par défaut (`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`).
- Le proxy IA bloque les services de métadonnées cloud (AWS/GCP) et les adresses link-local, et la taille des requêtes est limitée à 2 Mo.

## Tests

```bash
python3 -m unittest discover tests
```

## Licence

Distribué sous licence **MIT**. Libre d'utilisation, de modification et d'auto-hébergement.

Quick-Pick by [Mowtif](https://mowtif.com)
