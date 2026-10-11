# Quick-Pick

**Your AI agent asks you 20 questions at once as a stack of cards. You swipe through them, and the agent picks up your decisions.** No more wall of text in your LLM chat.

[Version française](README.fr.md)

<!-- TODO GIF (docs/demo.gif, not in the repo yet): 10 s, mobile swipe -> keyboard -> deck_cli summary -->

## Why

When you work with coding agents and assistants (Claude, Cursor, Hermes, OpenCode, Aider…), they often need many small decisions from you: keep or drop this dependency, approve or rework this rule, now or later for this ticket. In a chat, that turns into a long message with 20 multiple-choice questions, and answering it is slow and error-prone.

Quick-Pick turns those questions into a deck of cards. The agent creates the deck, sends you a link, you decide one card at a time (swipe on mobile, keys on desktop), and the agent reads back a summary of your decisions and comments. It also works on its own for backlogs, code reviews, ideas or audits: create a deck from the home screen by pasting a list, with optional AI suggestions (bring your own key).

## Highlights

- **Zero dependencies**: 100% Python standard library (`server.py`). No `pip install` required, no bundler, starts instantly.
- **Mobile-first, keyboard on desktop**: smooth physical swipe on phones (`passive: false`), arrow keys and dedicated keys (`a` / `d` / `w`) on desktop.
- **Create decks anywhere**: paste a list in the web UI (one line = one card), call `POST /api/decks`, or use `deck_cli.py`.
- **Built-in BYOK**: works with any OpenAI-compatible API (OpenAI `gpt-4o-mini`, local Ollama `llama3.2`, Groq, OpenRouter) and custom scoring webhooks. The key stays in your browser session by default.
- **Secure defaults**: optional API token (required as soon as the server listens beyond localhost), strict Content Security Policy, AI proxy that refuses private addresses and never follows redirects.
- **Plain JSON storage**: decks are readable JSON files that scripts and AI agents can edit.
- **Calm by design**: no anxiety-inducing counters while you sort, decision history available at any time, a note field per card, and full undo (`Ctrl+Z`).

Note: the interface strings are currently in French.

## Quickstart

### Option A: local (zero dependencies)

```bash
git clone https://github.com/2umish8/quick-pick.git
cd quick-pick
python3 server.py
```

Open **`http://localhost:8791`** in your browser. On `127.0.0.1` (the default) no token is needed.

### Option B: pip (from GitHub)

Quick-Pick is not on PyPI yet; install it straight from the repository:

```bash
pip install git+https://github.com/2umish8/quick-pick.git
quick-pick              # web server on http://localhost:8791
quick-pick-cli list     # deck management CLI
```

The install ships the front end (`public/`) and the example decks (`examples/`). `python3 server.py` keeps working from a clone.

### Option C: Docker Compose (recommended for self-hosting)

Inside the container the server listens on `0.0.0.0`, so an API token is required. Compose refuses to start without `QUICK_PICK_TOKEN`:

```bash
# Pick a random token (or put QUICK_PICK_TOKEN=... in a .env file next to docker-compose.yml)
export QUICK_PICK_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
docker compose up -d
```

The port is published on the host loopback only (`127.0.0.1:8791`), and decks persist in `./data/decks`. Then open **`http://localhost:8791/#token=<your-token>`**: the token is read from the URL fragment (never the query string), removed from the address bar, kept for the tab session only, and attached to every API call. On a trusted machine, add `&remember=1` (`#token=<token>&remember=1`) to keep it in `localStorage`. You can also type it at the prompt shown after a `401 unauthorized`.

The image is pinned by digest (`python:3.12-alpine`), runs as an unprivileged user (`quickpick`, UID 10001) and has a `HEALTHCHECK` on `/api/health`. Compose runs the container with your host UID (1000 by default) so the mounted `./data/decks` stays writable:

```bash
# If your Linux UID is not 1000:
export QUICK_PICK_UID=$(id -u) QUICK_PICK_GID=$(id -g)
docker compose up -d
```

Quick check: `docker compose ps` should show `(healthy)`, and `curl -H "X-Quick-Pick-Token: $QUICK_PICK_TOKEN" http://localhost:8791/api/health` should answer `{"ok": true, ...}`.

## Create a deck from the web UI

No terminal needed: on the home screen, click **Créer un deck** ("Create a deck"), give it a title, pick a decision template (`triage`, `binary` or `priority`) and paste your items, **one line per card**. The deck is created and sorting starts right away. From the summary screen, **Copier en Markdown** ("Copy as Markdown") exports your decisions with their labels.

The same thing over the API (handy for agents):

```bash
curl -X POST http://localhost:8791/api/decks \
  -H 'Content-Type: application/json' \
  -d '{
        "title": "Q4 backlog triage",
        "template": "triage",
        "items": ["Move the database to Postgres", "Remove the legacy module"]
      }'
# When QUICK_PICK_TOKEN is set, add: -H "Authorization: Bearer $QUICK_PICK_TOKEN"
```

| Field | Required | Validation |
|---|---|---|
| `title` | yes | non-empty, 120 characters max |
| `items` | yes | array of non-empty lines, 500 characters per card, 200 cards max |
| `template` | no (`triage`) | `triage`, `binary` or `priority` |
| `id` | no | slug generated from the title; otherwise `^[a-zA-Z0-9_-]{1,128}$` |

Responses: `201` with the deck state, `400` on invalid input, `409` if the requested id already exists (a deck is **never** overwritten). For a description, a category or custom actions, use `deck_cli.py create`.

## Keyboard shortcuts

| Key | Action |
|---|---|
| `d` / `→` | Action on the right (e.g. keep / approve) |
| `a` / `←` | Action on the left (e.g. drop / reject) |
| `w` / `↑` | Action on top (e.g. review / later) |
| `x` / `Esc` | Skip the card |
| `c` | Focus the note field |
| `Ctrl+Z` / `Cmd+Z` | Undo |

Exact actions depend on the deck (see [deck format](#deck-format-datadecksidjson)).

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `QUICK_PICK_HOST` | `127.0.0.1` (`0.0.0.0` in Docker) | Server listen address |
| `QUICK_PICK_PORT` | `8791` | HTTP port |
| `QUICK_PICK_DATA_DIR` | `./data/decks` | Folder where deck JSON files are stored (not versioned, seeded from `examples/decks/` on first run) |
| `QUICK_PICK_TOKEN` | *(empty)* | API token (`Authorization: Bearer <token>` or `X-Quick-Pick-Token: <token>`). Required when the server listens on a non-loopback address: without it the server refuses to start |
| `QUICK_PICK_ALLOWED_HOSTS` | *(empty)* | Extra host names accepted in the `Host` header, comma-separated (`localhost`, `127.0.0.1` and `::1` are always accepted) |
| `QUICK_PICK_ALLOW_PRIVATE_ENDPOINTS` | `0` | Let the AI proxy call private/local endpoints (e.g. Ollama on `127.0.0.1:11434`). Set to `1` to use a local LLM (see [AI suggestions](#ai-suggestions-and-byok-bring-your-own-key)). Cloud metadata addresses stay blocked |
| `QUICK_PICK_CLASSIFIER_ALLOWED_HOSTS` | *(empty)* | Optional comma-separated allowlist of host names the AI proxy may call (e.g. `api.openai.com`). When set, any other host is refused |
| `QUICK_PICK_CSP_CONNECT_SRC` | *(empty)* | Extra origins allowed by the CSP `connect-src` for the direct browser mode, space-separated (e.g. `http://localhost:11434`) |
| `QUICK_PICK_API_KEY` | *(empty)* | API key used by `deck_cli.py classifier` when `--api-key-stdin` is not given |

> **Note:** when an `Origin` header is present, it must match the request `Host` exactly (same host and port). Behind a reverse proxy, forward the original `Host` header and add the public name to `QUICK_PICK_ALLOWED_HOSTS`.

## AI suggestions and BYOK (bring your own key)

Quick-Pick does not require any paid or proprietary model. Click the **⚙️** icon in the header to configure suggestions:

1. **OpenAI / Ollama / Groq protocol**:
   - **Base URL**: `https://api.openai.com/v1`, `http://localhost:11434/v1`, or `https://api.groq.com/openai/v1`
   - **Model**: `gpt-4o-mini`, `llama3.2`, `mistral`, etc.
   - **API key**: your private key (see where it is stored below).
2. **Custom webhook / API**:
   - Enter the URL of your own scoring endpoint. It receives the payload `{ id, title, description, bullets, candidate_actions }`.

> **Local LLM (Ollama):** private and local endpoints are blocked by default. To use Ollama or another local model, start the server with `QUICK_PICK_ALLOW_PRIVATE_ENDPOINTS=1`. In Docker, the container cannot reach the host's `127.0.0.1`: use `host.docker.internal` as the endpoint host (e.g. `http://host.docker.internal:11434/v1`) together with `QUICK_PICK_ALLOW_PRIVATE_ENDPOINTS=1`. On Linux, uncomment the `extra_hosts` block in `docker-compose.yml` so `host.docker.internal` resolves through `host-gateway`. To narrow the proxy further, set `QUICK_PICK_CLASSIFIER_ALLOWED_HOSTS` (e.g. `QUICK_PICK_CLASSIFIER_ALLOWED_HOSTS=api.openai.com`).

### Where your API key lives

The server **never** writes the key to disk, and Quick-Pick never sends it to any third party other than the provider you configured. Two storage options, chosen in the settings:

| Choice | Storage | Lifetime |
|---|---|---|
| Default | browser `sessionStorage` | Cleared when the tab is closed |
| "Mémoriser la clé sur cet appareil" (remember on this device) | browser `localStorage` | Persists until you click **Oublier la clé** (forget the key) |

A key saved in `localStorage` by an earlier version keeps working as is: it is shown as remembered in the settings, with the button to forget it. No existing setting is silently overwritten.

### Two ways to call the provider

| Mode | When | Where the key goes |
|---|---|---|
| **Through the server** (default) | Always available | It **goes through your Quick-Pick server**, which forwards it as `Authorization: Bearer` |
| **Direct from the browser** | Settings option, OpenAI-compatible APIs only | It stays in the browser; the server never sees it |

> ⚠️ **Proxy mode (default):** the key reaches the provider *through* the Quick-Pick server. On a shared instance, whoever runs the server could see it in logs or process memory. Use direct mode, or your own instance, if that is not acceptable.

> ⚠️ **Direct mode:** only for OpenAI-compatible APIs that **allow CORS** from the app's origin (OpenAI, Groq and OpenRouter do; Ollama and vLLM depend on their configuration). By default the CSP `connect-src` only allows those known providers: for a self-hosted provider, add its origin to `QUICK_PICK_CSP_CONNECT_SRC` and restart the server. Custom webhooks have no CORS contract and always go through the server.

## Using Quick-Pick with AI agents

Quick-Pick solves the **"wall of text"** problem in LLM chats (Hermes, Claude, Cursor, OpenCode, Aider). Instead of asking 20 multiple-choice questions in one message, an agent prepares a deck of cards, gives the link to the human, then reads back the decisions:

1. **The agent creates the deck** (with the CLI below, or with `POST /api/decks`):
   ```bash
   # The agent can pipe JSON straight into the CLI
   cat << 'EOF' | python3 deck_cli.py create --id "pr-review" --title "Review PR #42" --items-file -
   [
     {
       "id": "item-1",
       "title": "Remove legacy dependency XYZ",
       "bullets": ["Unmaintained for 2 years", "Replaceable with 10 lines of native code"]
     }
   ]
   EOF
   ```
2. **The agent notifies the human**:
   > *"I've prepared 5 decisions at http://localhost:8791/#pr-review. Swipe through them when you have 30 seconds."*

   If the instance uses a token, the link can carry it in the fragment: `http://localhost:8791/#pr-review&token=<token>`.
3. **The agent reads the decisions back**:
   ```bash
   python3 deck_cli.py summary pr-review --format md
   ```
   The agent gets the decisions and comments and resumes its work asynchronously, without blocking the conversation.
4. **Agent skill**: [`skills/quick-pick/SKILL.md`](skills/quick-pick/SKILL.md) can be dropped into your agent environment (`~/.agents/skills/quick-pick/`).

## Command line (`deck_cli.py`)

Scripts and AI agents can drive decks from the command line (`quick-pick-cli` is the same tool when installed with pip):

```bash
# 1. Create a deck from a JSON items file
python3 deck_cli.py create \
  --id "sprint-42" \
  --title "Sprint 42 triage" \
  --category "PRODUCT" \
  --template "triage" \
  --items-file items.json

# Built-in templates: triage (3 ways), binary (yes/no), priority (now/later/ignore)
# Custom actions: use --actions-file actions.json
# Optional: --description, --guidelines (decision criteria shown to the human)

# 2. List decks
python3 deck_cli.py list

# 3. Show current state (progress)
python3 deck_cli.py status sprint-42

# 4. Get the decision summary (Markdown or JSON, default JSON)
python3 deck_cli.py summary sprint-42 --format md

# 5. Reset a deck
python3 deck_cli.py reset sprint-42

# 6. Delete a deck
python3 deck_cli.py delete sprint-42

# 7. Test an external classifier (never pass the key as an argument)
echo "$MY_KEY" | python3 deck_cli.py classifier --endpoint https://api.openai.com/v1 --api-key-stdin
QUICK_PICK_API_KEY="$MY_KEY" python3 deck_cli.py classifier --endpoint https://api.openai.com/v1
```

> `--api-key` is still accepted for compatibility but prints a warning: the key would be visible in `ps` and in your shell history. Prefer `--api-key-stdin` or `QUICK_PICK_API_KEY`.

## Deck format (`data/decks/<id>.json`)

The `data/` folder is **not** versioned: it holds your decks. On first run, if it contains no deck yet, the example decks from `examples/decks/` are copied into it. An existing deck is never overwritten or deleted (neither at startup nor during an upgrade). To get an example back, delete that file from `data/decks/` and restart the server.

Each deck is a self-contained JSON document:

```json
{
  "id": "my-decision",
  "title": "Topic title",
  "description": "Context",
  "category": "AUDIT",
  "default_actions": [
    { "id": "approve", "label": "Keep", "direction": "east", "key": "d", "color": "success" },
    { "id": "reject", "label": "Drop", "direction": "west", "key": "a", "color": "danger" },
    { "id": "review", "label": "Rework", "direction": "north", "key": "w", "color": "warning" }
  ],
  "items": [
    {
      "id": "item-1",
      "title": "Item name",
      "badges": [{ "label": "URGENT", "variant": "warning" }],
      "bullets": ["Key point 1", "Key point 2"],
      "description": "Optional details",
      "status": "pending",
      "chosen_action": null,
      "comment": null,
      "decided_at": null
    }
  ]
}
```

> **Read-time validation:** every deck is checked when loaded: `items` must be a JSON array and each item needs a non-empty `id` and `title`. A non-conforming deck returns an explicit `404` error; the file is never rewritten or fixed automatically.

## Security and production deployment

Quick-Pick is designed for a single user or an internal team:

- **API token:** when the server listens on a non-loopback address (`QUICK_PICK_HOST=0.0.0.0`, Docker), `QUICK_PICK_TOKEN` is required at startup and every `/api/*` call must present it. The token never travels in the query string: pass it in the URL fragment (`http://localhost:8791/#token=<token>`, kept for the tab session; add `&remember=1` to keep it in `localStorage` on a trusted machine) or type it at the prompt.
- **Request checks:** the server validates the `Host` header, requires `Content-Type: application/json` on POST requests and checks the `Origin` header.
- **AI proxy hardening:** private and local addresses are refused by default, cloud metadata addresses (AWS/GCP/Alibaba) are always refused, each endpoint is resolved once and the connection is pinned to the validated addresses (DNS rebinding), redirects are never followed, and `QUICK_PICK_CLASSIFIER_ALLOWED_HOSTS` can restrict targets to an allowlist. Request bodies are limited to 2 MB.
- **Browser hardening:** security headers on every response (`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`), a strict `Content-Security-Policy` with no inline script or style (`script-src 'self'`, `style-src 'self'`, `frame-ancestors 'none'`; `connect-src` allows `'self'`, the known providers and whatever you add via `QUICK_PICK_CSP_CONNECT_SRC`), and a `Permissions-Policy` that turns off camera, microphone, geolocation, etc.
- **Internet exposure:** the token is a single shared secret, not user accounts. To expose Quick-Pick on the internet, put it behind a reverse proxy with authentication (Caddy with Basic Auth, Traefik, Authelia, Cloudflare Access) or on a private network such as Tailscale.
- **"Fake-IP" DNS:** on networks using fake-IP DNS (`198.18.0.0/15`, e.g. some VPN/proxy/sandbox modes such as Clash/Surge/TUN), public API host names resolve to non-global addresses and are refused by default. Workaround: disable fake-IP for those domains / use a real DNS, or (knowingly) combine `QUICK_PICK_ALLOW_PRIVATE_ENDPOINTS=1` with `QUICK_PICK_CLASSIFIER_ALLOWED_HOSTS=api.openai.com` to restrict targets.

Security issues: see [SECURITY.md](SECURITY.md).

## Upgrading

Release notes and upgrade steps for each version are in [CHANGELOG.md](CHANGELOG.md) (in French) and on the [releases page](https://github.com/2umish8/quick-pick/releases). Coming from 2.0.0, read the 2.0.1 security notes first: Docker now requires `QUICK_PICK_TOKEN`, and a local LLM needs `QUICK_PICK_ALLOW_PRIVATE_ENDPOINTS=1`.

## Tests

```bash
PYTHONPATH=. python3 -m unittest discover -s tests
ruff check .                      # optional: pip install -e ".[dev]"
node --test tests/js/*.test.mjs   # front end (classifier, XSS, timeout, mobile & a11y)
```

The same checks run in CI on every pull request. The front-end checks (`tests/js/*.test.mjs`, no dependency, no DOM) also run from the unittest suite when `node` is installed, and are skipped otherwise. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Released under the **MIT** license, © 2026 Mischael Radabanoro. Free to use, modify and self-host. See [LICENSE](LICENSE).

Quick-Pick by [Mowtif](https://mowtif.com)
