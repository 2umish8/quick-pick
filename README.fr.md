# Quick-Pick

**Votre agent IA vous pose 20 questions d'un coup, sous forme de cartes à swiper. Vous tranchez, il reprend vos décisions.** Fini le mur de texte dans les chats avec les LLM.

[English version](README.md)

<!-- TODO GIF (docs/demo.gif, pas encore dans le dépôt) : 10 s, swipe mobile -> clavier -> deck_cli summary -->

## Pourquoi

Quand on travaille avec des agents de code et des assistants (Claude, Cursor, Hermes, OpenCode, Aider…), ils ont souvent besoin de beaucoup de petites décisions : garder ou retirer cette dépendance, valider ou reformuler cette règle, maintenant ou plus tard pour ce ticket. Dans un chat, ça devient un long message avec 20 questions à choix multiples, lent et pénible à remplir.

Quick-Pick transforme ces questions en pile de cartes. L'agent crée le deck et vous envoie un lien ; vous tranchez une carte à la fois (swipe sur mobile, touches sur desktop) ; l'agent relit ensuite la synthèse de vos décisions et commentaires. L'outil sert aussi seul pour trier backlogs, relectures de code, idées ou audits : créez un deck depuis l'écran d'accueil en collant une liste, avec des suggestions IA optionnelles (BYOK, votre propre clé).

## Points forts

- **Zéro dépendance** : 100 % bibliothèque standard Python (`server.py`). Aucun `pip install` requis, aucun bundler, démarrage instantané.
- **Mobile d'abord, clavier sur desktop** : swipe tactile fluide sur smartphone (`passive: false`), flèches et touches dédiées (`a` / `d` / `w`) sur desktop.
- **Des decks créés n'importe où** : collez une liste dans l'interface web (une ligne = une carte), appelez `POST /api/decks` ou utilisez `deck_cli.py`.
- **BYOK intégré** : compatible avec toute API de type OpenAI (OpenAI `gpt-4o-mini`, Ollama local `llama3.2`, Groq, OpenRouter) et avec des webhooks de scoring personnalisés. Par défaut, la clé reste dans la session du navigateur.
- **Sécurisé par défaut** : jeton d'API optionnel (obligatoire dès que le serveur écoute au-delà de localhost), Content Security Policy stricte, proxy IA qui refuse les adresses privées et ne suit jamais les redirections.
- **Stockage JSON simple** : les decks sont des fichiers JSON lisibles, manipulables par des scripts ou des agents IA.
- **Pensé pour trier sans stress** : pas de compteur anxiogène pendant le tri, historique des décisions consultable à tout moment, champ note par carte et annulation complète (`Ctrl+Z`).

## Démarrage rapide

### Option A : en local (zéro dépendance)

```bash
git clone https://github.com/2umish8/quick-pick.git
cd quick-pick
python3 server.py
```

Ouvrez **`http://localhost:8791`** dans votre navigateur. Sur `127.0.0.1` (le défaut), aucun jeton n'est nécessaire.

### Option B : pip (depuis GitHub)

Quick-Pick n'est pas encore publié sur PyPI ; installez-le directement depuis le dépôt :

```bash
pip install git+https://github.com/2umish8/quick-pick.git
quick-pick              # serveur web sur http://localhost:8791
quick-pick-cli list     # CLI de gestion des decks
```

L'installation embarque le front (`public/`) et les decks d'exemple (`examples/`). `python3 server.py` fonctionne toujours depuis un clone.

### Option C : Docker Compose (recommandé en auto-hébergement)

Dans le conteneur, le serveur écoute sur `0.0.0.0` : un jeton d'API est donc obligatoire, et Compose refuse de démarrer sans `QUICK_PICK_TOKEN` :

```bash
# Choisir un jeton aléatoire (ou mettre QUICK_PICK_TOKEN=... dans un fichier .env à côté de docker-compose.yml)
export QUICK_PICK_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
docker compose up -d
```

Le port n'est publié que sur la boucle locale de l'hôte (`127.0.0.1:8791`) et les decks sont conservés dans `./data/decks`. Ouvrez ensuite **`http://localhost:8791/#token=<votre-jeton>`** : le jeton est lu dans le fragment d'URL (jamais dans la chaîne de requête), retiré de la barre d'adresse, conservé pour la session de l'onglet uniquement et joint à chaque appel d'API. Sur une machine de confiance, ajoutez `&remember=1` (`#token=<jeton>&remember=1`) pour le conserver dans le `localStorage`. Vous pouvez aussi le saisir à l'invite affichée après un `401 unauthorized`.

L'image est figée sur un digest (`python:3.12-alpine`), tourne sous un utilisateur non privilégié (`quickpick`, UID 10001) et expose un `HEALTHCHECK` sur `/api/health`. Compose lance le conteneur avec l'UID de l'hôte (1000 par défaut) pour que le dossier `./data/decks` monté reste accessible en écriture :

```bash
# Si votre UID Linux est différent de 1000 :
export QUICK_PICK_UID=$(id -u) QUICK_PICK_GID=$(id -g)
docker compose up -d
```

Vérification rapide : `docker compose ps` doit afficher `(healthy)`, et `curl -H "X-Quick-Pick-Token: $QUICK_PICK_TOKEN" http://localhost:8791/api/health` doit répondre `{"ok": true, ...}`.

## Créer un deck depuis l'interface web

Sans terminal : sur l'écran d'accueil, cliquez sur **Créer un deck**, donnez un titre, choisissez un modèle de décision (`triage`, `binary` ou `priority`) et collez vos éléments, **une ligne par carte**. Le deck est créé et le tri démarre immédiatement. Depuis le récapitulatif, le bouton **Copier en Markdown** exporte vos décisions avec leurs libellés.

L'équivalent par l'API (pratique pour les agents) :

```bash
curl -X POST http://localhost:8791/api/decks \
  -H 'Content-Type: application/json' \
  -d '{
        "title": "Tri du backlog Q4",
        "template": "triage",
        "items": ["Migrer la base vers Postgres", "Supprimer le module legacy"]
      }'
# Si QUICK_PICK_TOKEN est défini, ajoutez : -H "Authorization: Bearer $QUICK_PICK_TOKEN"
```

| Champ | Requis | Règle de validation |
|---|---|---|
| `title` | oui | non vide, 120 caractères max |
| `items` | oui | tableau de lignes non vides, 500 caractères par carte, 200 cartes max |
| `template` | non (`triage`) | `triage`, `binary` ou `priority` |
| `id` | non | slug généré depuis le titre ; sinon `^[a-zA-Z0-9_-]{1,128}$` |

Réponses : `201` avec l'état du deck, `400` sur une entrée invalide, `409` si l'identifiant demandé existe déjà (un deck n'est **jamais** écrasé). Pour une description, une catégorie ou des actions sur mesure, passez par `deck_cli.py create`.

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
| `QUICK_PICK_DATA_DIR` | `./data/decks` | Dossier de stockage des fichiers JSON de decks (non versionné, alimenté depuis `examples/decks/` au premier lancement) |
| `QUICK_PICK_TOKEN` | *(vide)* | Jeton d'API (`Authorization: Bearer <jeton>` ou `X-Quick-Pick-Token: <jeton>`). Obligatoire si le serveur écoute sur une adresse non locale : sans lui, le serveur refuse de démarrer |
| `QUICK_PICK_ALLOWED_HOSTS` | *(vide)* | Noms d'hôtes supplémentaires acceptés dans l'en-tête `Host`, séparés par des virgules (`localhost`, `127.0.0.1` et `::1` sont toujours acceptés) |
| `QUICK_PICK_ALLOW_PRIVATE_ENDPOINTS` | `0` | Autoriser le proxy IA à appeler des endpoints privés ou locaux (ex. Ollama sur `127.0.0.1:11434`). Mettre à `1` pour utiliser un LLM local (voir [Assistance IA](#assistance-ia-et-byok-votre-propre-clé)). Les adresses de métadonnées cloud restent bloquées |
| `QUICK_PICK_CLASSIFIER_ALLOWED_HOSTS` | *(vide)* | Liste optionnelle de noms d'hôtes que le proxy IA peut appeler, séparés par des virgules (ex. `api.openai.com`). Si elle est renseignée, tout autre hôte est refusé |
| `QUICK_PICK_CSP_CONNECT_SRC` | *(vide)* | Origines supplémentaires autorisées par la CSP `connect-src` pour le mode direct navigateur, séparées par des espaces (ex. `http://localhost:11434`) |
| `QUICK_PICK_API_KEY` | *(vide)* | Clé API utilisée par `deck_cli.py classifier` quand `--api-key-stdin` n'est pas fourni |

> **Note :** si un en-tête `Origin` est présent, il doit correspondre exactement à l'en-tête `Host` de la requête (même hôte et même port). Derrière un reverse proxy, transmettez l'en-tête `Host` d'origine et ajoutez le nom public à `QUICK_PICK_ALLOWED_HOSTS`.

## Assistance IA et BYOK (votre propre clé)

Quick-Pick n'impose aucun modèle payant ou propriétaire. Cliquez sur l'icône **⚙️** dans l'en-tête pour configurer les suggestions :

1. **Protocole OpenAI / Ollama / Groq** :
   - **URL de base** : `https://api.openai.com/v1`, `http://localhost:11434/v1` ou `https://api.groq.com/openai/v1`
   - **Modèle** : `gpt-4o-mini`, `llama3.2`, `mistral`, etc.
   - **Clé API** : votre clé privée (voir plus bas où elle est conservée).
2. **Webhook / API personnalisée** :
   - Renseignez l'URL de votre endpoint de scoring. Il reçoit le payload `{ id, title, description, bullets, candidate_actions }`.

> **LLM local (Ollama) :** les endpoints privés et locaux sont bloqués par défaut. Pour utiliser Ollama ou un autre modèle local, démarrez le serveur avec `QUICK_PICK_ALLOW_PRIVATE_ENDPOINTS=1`. En Docker, le conteneur ne peut pas joindre le `127.0.0.1` de l'hôte : utilisez `host.docker.internal` comme hôte d'endpoint (ex. `http://host.docker.internal:11434/v1`) avec `QUICK_PICK_ALLOW_PRIVATE_ENDPOINTS=1`. Sous Linux, décommentez le bloc `extra_hosts` du `docker-compose.yml` pour résoudre `host.docker.internal` via `host-gateway`. Pour restreindre davantage le proxy, renseignez `QUICK_PICK_CLASSIFIER_ALLOWED_HOSTS` (ex. `QUICK_PICK_CLASSIFIER_ALLOWED_HOSTS=api.openai.com`).

### Où vit votre clé API

Le serveur n'écrit **jamais** la clé sur le disque, et Quick-Pick ne l'envoie à aucun tiers autre que le fournisseur que vous avez configuré. Deux emplacements possibles, choisis dans les réglages :

| Choix | Stockage | Durée de vie |
|---|---|---|
| Par défaut | `sessionStorage` du navigateur | Effacée à la fermeture de l'onglet |
| « Mémoriser la clé sur cet appareil » | `localStorage` du navigateur | Persiste, jusqu'au bouton **Oublier la clé** |

Une clé déjà enregistrée dans `localStorage` par une version antérieure reste utilisable telle quelle : elle est signalée comme mémorisée dans les réglages, avec le bouton pour l'oublier. Aucun réglage existant n'est écrasé silencieusement.

### Deux modes d'appel du fournisseur

| Mode | Quand | Où part la clé |
|---|---|---|
| **Via le serveur** (par défaut) | Toujours disponible | Elle **transite par votre serveur Quick-Pick**, qui la transmet en `Authorization: Bearer` |
| **Appel direct depuis le navigateur** | Option dans les réglages, API compatibles OpenAI uniquement | Elle reste dans le navigateur ; le serveur ne la voit jamais |

> ⚠️ **Mode proxy (défaut)** : la clé est transmise au fournisseur *par* le serveur Quick-Pick. Sur une instance partagée, l'opérateur du serveur pourrait la voir dans les journaux ou en mémoire. Utilisez le mode direct, ou votre propre instance, si ce n'est pas acceptable.

> ⚠️ **Mode direct** : réservé aux API compatibles OpenAI qui **autorisent les appels CORS** depuis l'origine de l'application (OpenAI, Groq et OpenRouter le font ; Ollama et vLLM selon leur configuration). Par défaut, la CSP `connect-src` n'autorise que ces fournisseurs connus : pour un fournisseur auto-hébergé, ajoutez son origine dans `QUICK_PICK_CSP_CONNECT_SRC` puis redémarrez le serveur. Les webhooks personnalisés n'ont pas de contrat CORS et passent toujours par le serveur.

## Utiliser Quick-Pick avec des agents IA

Quick-Pick résout le problème du **« mur de texte »** dans les chats avec les LLM (Hermes, Claude, Cursor, OpenCode, Aider). Au lieu de poser 20 questions à choix multiples dans un message, l'agent prépare une pile de cartes, donne le lien à l'humain, puis récupère les décisions :

1. **L'agent crée le deck** (avec le CLI ci-dessous, ou avec `POST /api/decks`) :
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

   Si l'instance utilise un jeton, le lien peut le porter dans le fragment : `http://localhost:8791/#pr-review&token=<jeton>`.
3. **L'agent récupère les décisions** :
   ```bash
   python3 deck_cli.py summary pr-review --format md
   ```
   L'agent récupère les arbitrages et les commentaires, puis reprend son travail de façon asynchrone, sans bloquer la conversation.
4. **Skill agent** : le fichier [`skills/quick-pick/SKILL.md`](skills/quick-pick/SKILL.md) s'importe directement dans votre environnement d'agents (`~/.agents/skills/quick-pick/`).

## Ligne de commande (`deck_cli.py`)

Les scripts et les agents IA peuvent piloter les decks en ligne de commande (`quick-pick-cli` est le même outil après une installation pip) :

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

# 7. Tester un classifieur externe (ne jamais passer la clé en argument)
echo "$MY_KEY" | python3 deck_cli.py classifier --endpoint https://api.openai.com/v1 --api-key-stdin
QUICK_PICK_API_KEY="$MY_KEY" python3 deck_cli.py classifier --endpoint https://api.openai.com/v1
```

> `--api-key` reste accepté pour compatibilité mais affiche un avertissement : la clé serait visible dans `ps` et dans l'historique du shell. Préférez `--api-key-stdin` ou `QUICK_PICK_API_KEY`.

## Format d'un deck (`data/decks/<id>.json`)

Le dossier `data/` n'est **pas** versionné : il contient vos decks. Au premier lancement, s'il ne contient encore aucun deck, les decks d'exemple de `examples/decks/` y sont copiés. Un deck existant n'est jamais écrasé ni supprimé (ni au démarrage, ni pendant une mise à jour). Pour retrouver un exemple, supprimez le fichier concerné de `data/decks/` puis relancez le serveur.

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

> **Validation à la lecture** : chaque deck est contrôlé au chargement : `items` doit être un tableau JSON et chaque item doit porter un `id` et un `title` non vides. Un deck non conforme renvoie une erreur `404` explicite ; le fichier n'est jamais réécrit ni corrigé automatiquement.

## Sécurité et déploiement en production

Quick-Pick est conçu pour un usage mono-utilisateur ou en équipe interne :

- **Jeton d'API** : si le serveur écoute sur une adresse non locale (`QUICK_PICK_HOST=0.0.0.0`, Docker), `QUICK_PICK_TOKEN` est exigé au démarrage et chaque appel `/api/*` doit le présenter. Le jeton ne transite jamais par la chaîne de requête : passez-le dans le fragment d'URL (`http://localhost:8791/#token=<jeton>`, conservé pour la session de l'onglet ; ajoutez `&remember=1` pour le garder dans le `localStorage` sur une machine de confiance) ou saisissez-le à l'invite.
- **Contrôles des requêtes** : le serveur vérifie l'en-tête `Host`, exige `Content-Type: application/json` sur les requêtes POST et contrôle l'en-tête `Origin`.
- **Durcissement du proxy IA** : adresses privées et locales refusées par défaut, adresses de métadonnées cloud (AWS/GCP/Alibaba) toujours refusées, chaque endpoint résolu une seule fois avec connexion épinglée aux adresses validées (DNS rebinding), redirections jamais suivies, et `QUICK_PICK_CLASSIFIER_ALLOWED_HOSTS` pour limiter les cibles à une liste. Taille des requêtes limitée à 2 Mo.
- **Durcissement côté navigateur** : en-têtes de sécurité sur toutes les réponses (`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`), `Content-Security-Policy` stricte sans script ni style inline (`script-src 'self'`, `style-src 'self'`, `frame-ancestors 'none'` ; `connect-src` autorise `'self'`, les fournisseurs connus et ce que vous ajoutez via `QUICK_PICK_CSP_CONNECT_SRC`), et `Permissions-Policy` qui coupe caméra, micro, géolocalisation, etc.
- **Exposition sur Internet** : le jeton est un secret partagé unique, pas un système de comptes. Pour exposer Quick-Pick sur Internet, placez-le derrière un reverse proxy avec authentification (Caddy avec Basic Auth, Traefik, Authelia, Cloudflare Access) ou sur un réseau privé comme Tailscale.
- **DNS « fake-IP »** : sur les réseaux qui utilisent un DNS fake-IP (`198.18.0.0/15`, par ex. certains modes VPN/proxy/bac à sable comme Clash/Surge/TUN), les noms d'hôtes d'API publiques résolvent vers des adresses non globales et sont donc refusés par défaut. Contournement : désactivez le fake-IP pour ces domaines / utilisez un vrai DNS, ou (en connaissance de cause) combinez `QUICK_PICK_ALLOW_PRIVATE_ENDPOINTS=1` avec `QUICK_PICK_CLASSIFIER_ALLOWED_HOSTS=api.openai.com` pour restreindre les cibles.

Signaler une faille : voir [SECURITY.md](SECURITY.md).

## Mise à niveau

Les notes de version et procédures de mise à niveau sont dans le [CHANGELOG.md](CHANGELOG.md) et sur la [page des releases](https://github.com/2umish8/quick-pick/releases). Depuis la 2.0.0, lisez d'abord les notes de sécurité de la 2.0.1 : Docker exige désormais `QUICK_PICK_TOKEN`, et un LLM local nécessite `QUICK_PICK_ALLOW_PRIVATE_ENDPOINTS=1`.

## Tests

```bash
PYTHONPATH=. python3 -m unittest discover -s tests
ruff check .                      # optionnel : pip install -e ".[dev]"
node --test tests/js/*.test.mjs   # front (classifieur, XSS, timeout, mobile & a11y)
```

Les mêmes vérifications tournent dans la CI à chaque pull request. Les checks front (`tests/js/*.test.mjs`, sans dépendance et sans DOM) sont aussi lancés par la suite unittest si `node` est installé, et ignorés sinon. Voir [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

Distribué sous licence **MIT**, © 2026 Mischael Radabanoro. Libre d'utilisation, de modification et d'auto-hébergement. Voir [LICENSE](LICENSE).

Quick-Pick by [Mowtif](https://mowtif.com)
