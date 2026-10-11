# ⚡ Quick-Pick

> Interface de décision et tri rapide 1 carte à la fois (mobile & desktop).  
> Tranchez vos backlogs, relectures de code, idées ou audits sans distraction, avec swipe physique ou touches clavier, et assistance IA optionnelle (BYOK).

---

## ✨ Points Forts

* **Zéro Dépendance** : 100% Python standard library (`server.py`). Aucun bundler, démarre instantanément (installation par `pip` optionnelle).
* **Mobile-First & Clavier Desktop** : Swipe tactile physique fluide (`passive: false`) sur smartphone, flèches directionnelles et touches dédiées (`a`/`d`/`w`) sur desktop.
* **Anti-Fork & BYOK Intégré** : Support natif universel des APIs OpenAI-compatibles (OpenAI `gpt-4o-mini`, Ollama local `llama3.2`, Groq, OpenRouter) et des webhooks de scoring custom.
* **Persistance Simple & Propre** : Decks stockés en fichiers JSON lisibles et manipulables par scripts ou agents IA (`deck_cli.py`).
* **Ergonomie Sans Stress** : Pas de compteurs anxiogènes pendant le tri, historique de décision consultable à tout moment, champ note contextuel et annulation complète (`Ctrl+Z`).

---

## 🚀 Démarrage Rapide

### Option A : En local (5 secondes, zéro dépendance)

```bash
git clone https://github.com/2umish8/quick-pick.git
cd quick-pick
python3 server.py
```
👉 Ouvrez votre navigateur sur **`http://localhost:8791`**.

### Option B : Installation par pip

```bash
pip install quick-pick
quick-pick              # serveur web sur http://localhost:8791
quick-pick-cli list     # CLI de gestion des decks
```

L'installation embarque le front (`public/`) et les decks d'exemple (`examples/`). Le dépôt reste
utilisable tel quel : `python3 server.py` fonctionne toujours depuis un clone.

### Option C : Avec Docker Compose (Recommandé en Self-Host)

```bash
# Choisir un jeton d'API (obligatoire : le conteneur écoute sur 0.0.0.0)
export QUICK_PICK_TOKEN="un-jeton-long-et-aleatoire"
docker compose up -d
```
👉 Le service est immédiatement opérationnel avec persistance des données dans `./data/decks`. Ouvrez ensuite **`http://localhost:8791/#token=<votre-jeton>`** : le jeton est conservé pour la session de l'onglet uniquement (jamais dans la chaîne de requête), puis retiré du fragment d'URL, et joint automatiquement à chaque appel d'API. Sur une machine de confiance, ajoutez `&remember=1` (`#token=<jeton>&remember=1`) pour le conserver dans le `localStorage` ; sinon, vous pouvez aussi le saisir à l'invite affichée en cas de `401 unauthorized`.

L'image Docker est figée sur un digest (`python:3.12-alpine`), tourne sous un utilisateur non privilégié
(`quickpick`, UID 10001) et expose un `HEALTHCHECK` sur `/api/health`. Docker Compose lance le conteneur
avec l'UID de l'hôte (1000 par défaut) pour que le dossier `./data/decks` monté reste accessible :

```bash
# Si votre UID Linux est différent de 1000 :
export QUICK_PICK_UID=$(id -u) QUICK_PICK_GID=$(id -g)
docker compose up -d
```

Vérification rapide : `docker compose ps` doit afficher `(healthy)`, `curl -H "X-Quick-Pick-Token: $QUICK_PICK_TOKEN" http://localhost:8791/api/health` doit répondre `{"ok": true, ...}`.

---

## 🛠️ Variables d'Environnement

| Variable | Défaut | Description |
|---|---|---|
| `QUICK_PICK_HOST` | `127.0.0.1` (`0.0.0.0` dans Docker) | Adresse IP d'écoute du serveur |
| `QUICK_PICK_PORT` | `8791` | Port d'écoute HTTP |
| `QUICK_PICK_DATA_DIR` | `./data/decks` | Dossier de stockage des fichiers JSON de decks (non versionné, seedé depuis `examples/decks/` au premier lancement) |
| `QUICK_PICK_ALLOW_PRIVATE_ENDPOINTS` | `0` | Autoriser le proxy IA à requêter des endpoints privés/locaux (ex : Ollama sur `127.0.0.1:11434`). Mettre à `1` pour utiliser un LLM local (voir § Assistance IA) |
| `QUICK_PICK_CLASSIFIER_ALLOWED_HOSTS` | (vide) | Liste optionnelle de noms d'hôtes autorisés pour le proxy IA, séparés par des virgules (ex : `api.openai.com`). Si renseignée, tout endpoint dont l'hôte n'est pas listé est refusé |
| `QUICK_PICK_TOKEN` | (vide) | Jeton d'authentification de l'API (`Authorization: Bearer <jeton>` ou `X-Quick-Pick-Token: <jeton>`). Obligatoire si le serveur écoute sur une adresse non locale |
| `QUICK_PICK_ALLOWED_HOSTS` | (vide) | Noms d'hôtes supplémentaires acceptés dans l'en-tête `Host`, séparés par des virgules (le serveur accepte toujours `localhost`, `127.0.0.1` et `::1`) |

> **Note :** si un en-tête `Origin` est présent, il doit correspondre exactement à l'en-tête `Host` de la requête (même hôte et même port) ; derrière un reverse-proxy, transmettez l'en-tête `Host` d'origine et ajoutez le nom public à `QUICK_PICK_ALLOWED_HOSTS`.

---

## 🤖 Assistance IA & BYOK (Bring Your Own Key)

Quick-Pick n'impose aucun modèle payant ou propriétaire. Cliquez sur l'icône **⚙️** dans l'en-tête pour configurer vos suggestions :

1. **Protocole OpenAI / Ollama / Groq** :
   - **Base URL** : `https://api.openai.com/v1`, `http://localhost:11434/v1`, ou `https://api.groq.com/openai/v1`
   - **Modèle** : `gpt-4o-mini`, `llama3.2`, `mistral`, etc.
   - **Clé API** : Votre clé privée (conservée uniquement dans le `localStorage` de votre navigateur).
2. **Webhook / API Custom** :
   - Renseignez l'URL de votre endpoint de scoring interne recevant le payload `{ id, title, description, bullets, candidate_actions }`.

> **LLM local (Ollama) :** les endpoints privés et locaux sont bloqués par défaut. Pour utiliser Ollama ou un modèle local, démarrez le serveur avec `QUICK_PICK_ALLOW_PRIVATE_ENDPOINTS=1`. En Docker, le conteneur ne peut pas joindre `127.0.0.1` de l'hôte : utilisez `host.docker.internal` comme hôte d'endpoint (ex : `http://host.docker.internal:11434/v1`) avec `QUICK_PICK_ALLOW_PRIVATE_ENDPOINTS=1`. Sous Linux, décommentez le bloc `extra_hosts` du `docker-compose.yml` pour résoudre `host.docker.internal` via `host-gateway`. Pour restreindre davantage le proxy, renseignez `QUICK_PICK_CLASSIFIER_ALLOWED_HOSTS` (ex : `QUICK_PICK_CLASSIFIER_ALLOWED_HOSTS=api.openai.com`).

---

## 🦾 Intégration Agents IA (Pair-Programming & Assistants Autonomes)

Quick-Pick résout le problème du **« mur de texte »** dans les chats avec les LLM (Hermes, Claude, Cursor, OpenCode, Aider). Au lieu de poser 20 questions à choix multiples par message, un agent prépare une pile de cartes, donne le lien à l'humain, puis récupère les décisions arbitrées :

1. **Génération directe par un agent** :
   ```bash
   # L'agent peut piper du JSON directement dans le CLI
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
2. **Notification à l'humain** :
   > *"J'ai préparé un lot de 5 décisions sur http://localhost:8791/#pr-review. Fais un swipe rapide quand tu as 30 secondes."*
3. **Récupération instantanée par l'agent** :
   ```bash
   python3 deck_cli.py summary pr-review --format md
   ```
   L'agent récupère les arbitrages et commentaires pour reprendre son exécution de manière asynchrone sans bloquer la conversation.
4. **Skill Agent standardisé** : le fichier [`skills/quick-pick/SKILL.md`](skills/quick-pick/SKILL.md) est directement importable dans vos environnements d'agents (`~/.agents/skills/quick-pick/`).

---

## 📋 Utilisation en Ligne de Commande (`deck_cli.py`)

Les scripts d'automatisation et agents d'IA peuvent piloter les decks directement en ligne de commande :

```bash
# 1. Créer un deck depuis un fichier JSON d'items
python3 deck_cli.py create \
  --id "sprint-42" \
  --title "Triage Sprint 42" \
  --category "PRODUIT" \
  --template "triage" \
  --items-file items.json

# Templates intégrés : triage (3 voies), binary (oui/non), priority (immédiat/tard/ignorer)
# Actions sur-mesure : utilisez le flag --actions-file actions.json

# 2. Lister les decks
python3 deck_cli.py list

# 3. Consulter l'état courant (progression)
python3 deck_cli.py status sprint-42

# 4. Obtenir le rapport de synthèse des décisions (Markdown ou JSON)
python3 deck_cli.py summary sprint-42 --format md

# 5. Réinitialiser un deck
python3 deck_cli.py reset sprint-42

# 6. Supprimer un deck
python3 deck_cli.py delete sprint-42
```

---

## 📄 Format d'un Deck (`data/decks/<id>.json`)

Le dossier `data/` n'est **pas** versionné : il contient vos decks. Au premier lancement, s'il ne
contient aucun deck, les decks d'exemple de `examples/decks/` y sont copiés tels quels. Un deck
existant n'est jamais écrasé ni supprimé (ni au démarrage, ni pendant une mise à jour) : pour repartir
des exemples, supprimez le fichier concerné de `data/decks/` puis relancez le serveur.

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

---

## 🔒 Sécurité & Déploiement en Production

Quick-Pick est conçu comme une application mono-utilisateur ou d'équipe interne :
- Pour une exposition publique sur Internet, placez-le derrière un reverse-proxy avec authentification (Caddy avec Basic Auth, Traefik, Authelia, Cloudflare Access ou réseau privé Tailscale).
- En-têtes de sécurité intégrés par défaut (`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`).
- Protection contre l'exfiltration de métadonnées cloud (AWS/GCP) et limitation de taille de payload (2 Mo).
- Durcissement intégré : le proxy IA refuse par défaut les adresses privées/locales et ne suit jamais les redirections ; le serveur vérifie l'en-tête `Host`, exige `Content-Type: application/json` sur les requêtes POST et contrôle l'en-tête `Origin`. Si le serveur écoute sur une adresse non locale (`QUICK_PICK_HOST=0.0.0.0`, Docker), un `QUICK_PICK_TOKEN` est exigé au démarrage et chaque appel `/api/*` doit le présenter. Le jeton ne transite jamais par la chaîne de requête : passez-le dans le fragment d'URL (`http://localhost:8791/#token=<jeton>`, conservé pour la session de l'onglet ; `&remember=1` pour le persister dans le `localStorage` sur une machine de confiance) ou saisissez-le à l'invite.
- Sur les réseaux utilisant un DNS « fake-IP » (`198.18.0.0/15`, par ex. certains VPN/proxys/bacs à sable comme les modes Clash/Surge/TUN), les noms d'hôtes d'API publiques résolvent vers des adresses non globales et sont donc refusés par défaut. Contournement : désactivez le fake-IP pour ces domaines / utilisez un vrai DNS, ou (en connaissance de cause) combinez `QUICK_PICK_ALLOW_PRIVATE_ENDPOINTS=1` avec `QUICK_PICK_CLASSIFIER_ALLOWED_HOSTS=api.openai.com` pour restreindre les cibles.

---

## 🧪 Tests

```bash
PYTHONPATH=. python3 -m unittest discover -s tests
ruff check .                                        # optionnel : pip install -e ".[dev]"
```

Les mêmes vérifications tournent dans la CI à chaque pull request.

---

## 📄 Licence

Distribué sous licence **MIT**. Libre d'utilisation, de modification et d'auto-hébergement.
