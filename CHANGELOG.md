# CHANGELOG Quick-Pick

## Unreleased — sécurité

### Changements notables
- Le proxy du classifieur refuse désormais par défaut les endpoints privés et locaux (`QUICK_PICK_ALLOW_PRIVATE_ENDPOINTS` vaut `0`). Les redirections HTTP ne sont plus suivies et chaque endpoint est résolu une seule fois avant connexion.
- Nouveau jeton d'API optionnel `QUICK_PICK_TOKEN` : obligatoire lorsque le serveur écoute sur une adresse non locale (dont Docker). Chaque requête `/api/*` doit alors présenter le jeton (`Authorization: Bearer <jeton>` ou `X-Quick-Pick-Token: <jeton>`). Les pages statiques restent accessibles sans jeton.
- Le serveur contrôle l'en-tête `Host` (avec `QUICK_PICK_ALLOWED_HOSTS` pour les hôtes supplémentaires), exige `Content-Type: application/json` sur les requêtes POST et contrôle l'en-tête `Origin`.
- Nouveau filtre optionnel `QUICK_PICK_CLASSIFIER_ALLOWED_HOSTS` pour restreindre les hôtes joignables par le proxy.
- En Docker, le port publié est désormais `127.0.0.1:8791:8791` et le conteneur exige `QUICK_PICK_TOKEN`.

### Mise à niveau
1. Si vous utilisiez un LLM local (Ollama) : redémarrez avec `QUICK_PICK_ALLOW_PRIVATE_ENDPOINTS=1`. En Docker, utilisez `host.docker.internal` comme hôte d'endpoint.
2. En Docker : définissez `QUICK_PICK_TOKEN` dans votre `.env` ou votre environnement avant `docker compose up -d`, puis ouvrez `http://localhost:8791/?token=<votre-jeton>` (le jeton est enregistré dans le navigateur).
3. Si vous exposiez le serveur sur le réseau local (`QUICK_PICK_HOST=0.0.0.0` hors Docker) : définissez également `QUICK_PICK_TOKEN`, sinon le serveur refusera de démarrer.
4. Aucune action requise pour un usage local par défaut (`127.0.0.1` sans LLM local).
