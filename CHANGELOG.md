# CHANGELOG Quick-Pick

## 2.1.0 — 2026-10-11

### Nouveautés
- Création d'un deck depuis l'écran d'accueil (une ligne = une carte) et endpoint `POST /api/decks` (409 si le deck existe déjà, jamais d'écrasement) (#8, MOW-189).
- Mode d'appel direct optionnel depuis le navigateur pour les fournisseurs compatibles OpenAI autorisant CORS ; le mode via le serveur reste le défaut (#6).

### Sécurité et robustesse (MOW-188)
- CSP stricte (aucun script/style inline) et `Permissions-Policy` restrictive ; origines supplémentaires via `QUICK_PICK_CSP_CONNECT_SRC` (#6).
- Clé BYOK conservée en `sessionStorage` par défaut (option « Mémoriser sur cet appareil ») ; le CLI lit la clé depuis `QUICK_PICK_API_KEY` ou `--api-key-stdin` (#6).
- Échappement HTML de tous les champs de deck, réponses 4xx sur payload/deck invalide, timeout de requête et bannière « Réessayer » (#5).
- Mobile et accessibilité : dock d'actions tactile sous 640px, vrais boutons avec focus visible, tiroir en dialogue modal, `aria-keyshortcuts` (#7).
- CI GitHub Actions (unittest, ruff, node --check), image Docker épinglée et non-root avec healthcheck, CONTRIBUTING/SECURITY, `data/` n'est plus versionné et les decks d'exemple sont seedés au premier lancement (#4).

### Mise à niveau
1. Decks existants : aucune migration ; le seed n'écrit que les exemples absents et n'écrase jamais un deck. Si vous suiviez `data/decks/` dans un fork, ces fichiers ne sont plus versionnés (vos fichiers locaux restent en place).
2. Docker : l'image tourne désormais en UID 10001 ; Compose lance le conteneur avec votre UID (`QUICK_PICK_UID`/`QUICK_PICK_GID`, défaut 1000). Reconstruisez l'image (`docker compose build`). `QUICK_PICK_TOKEN` reste obligatoire (depuis 2.0.1).
3. Clé API du classifieur : une clé déjà stockée en `localStorage` reste utilisable. Le CLI affiche un avertissement si `--api-key` est utilisé ; préférez `QUICK_PICK_API_KEY`.
4. Mode direct vers un fournisseur auto-hébergé : ajoutez son origine dans `QUICK_PICK_CSP_CONNECT_SRC`.

## 2.0.1 — 2026-10-11 — sécurité (GHSA-33mm-m373-c8vj)

### Changements notables
- Le proxy du classifieur refuse désormais par défaut les endpoints privés et locaux (`QUICK_PICK_ALLOW_PRIVATE_ENDPOINTS` vaut `0`). Les redirections HTTP ne sont plus suivies et chaque endpoint est résolu une seule fois avant connexion.
- Nouveau jeton d'API optionnel `QUICK_PICK_TOKEN` : obligatoire lorsque le serveur écoute sur une adresse non locale (dont Docker). Chaque requête `/api/*` doit alors présenter le jeton (`Authorization: Bearer <jeton>` ou `X-Quick-Pick-Token: <jeton>`). Les pages statiques restent accessibles sans jeton.
- Le serveur contrôle l'en-tête `Host` (avec `QUICK_PICK_ALLOWED_HOSTS` pour les hôtes supplémentaires), exige `Content-Type: application/json` sur les requêtes POST et contrôle l'en-tête `Origin`.
- Nouveau filtre optionnel `QUICK_PICK_CLASSIFIER_ALLOWED_HOSTS` pour restreindre les hôtes joignables par le proxy.
- En Docker, le port publié est désormais `127.0.0.1:8791:8791` et le conteneur exige `QUICK_PICK_TOKEN`.

### Mise à niveau
1. Si vous utilisiez un LLM local (Ollama) : redémarrez avec `QUICK_PICK_ALLOW_PRIVATE_ENDPOINTS=1`. En Docker, utilisez `host.docker.internal` comme hôte d'endpoint.
2. En Docker : définissez `QUICK_PICK_TOKEN` dans votre `.env` ou votre environnement avant `docker compose up -d`, puis ouvrez `http://localhost:8791/#token=<votre-jeton>` (le jeton est conservé pour la session de l'onglet uniquement, jamais dans la chaîne de requête ; ajoutez `&remember=1` pour le persister dans le `localStorage` sur une machine de confiance, ou saisissez-le à l'invite en cas de `401 unauthorized`).
3. Si vous exposiez le serveur sur le réseau local (`QUICK_PICK_HOST=0.0.0.0` hors Docker) : définissez également `QUICK_PICK_TOKEN`, sinon le serveur refusera de démarrer.
4. Aucune action requise pour un usage local par défaut (`127.0.0.1` sans LLM local).
- Correctifs round 3 : adresses de métadonnées cloud toujours bloquées (`100.100.100.200`, `fd00:ec2::254`, même avec `QUICK_PICK_ALLOW_PRIVATE_ENDPOINTS=1`) ; jeton passé par le fragment d'URL et conservé en `sessionStorage` par défaut (`&remember=1` pour le `localStorage`) avec invite en cas de `401` ; le proxy essaie chaque IP validée à tour de rôle ; aide Docker `extra_hosts` pour Ollama hôte et note DNS « fake-IP » (`198.18.0.0/15`).
