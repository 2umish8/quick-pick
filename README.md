# Quick-Pick

**Your AI agent asks you 20 questions at once as a stack of cards. You swipe through them, and the agent picks up your decisions.** No more wall of text in your LLM chat.

[Version française](README.fr.md)

<!-- TODO GIF: 10 s, swipe mobile -> clavier -> deck_cli summary -->
![Quick-Pick demo: swipe on mobile, keyboard on desktop, then deck_cli summary](docs/demo.gif)

## Why

When you work with coding agents and assistants (Claude, Cursor, Hermes, OpenCode, Aider…), they often need many small decisions from you: keep or drop this dependency, approve or rework this rule, now or later for this ticket. In a chat, that turns into a long message with 20 multiple-choice questions, and answering it is slow and error-prone.

Quick-Pick turns those questions into a deck of cards. The agent creates the deck, sends you a link, you decide one card at a time (swipe on mobile, keys on desktop), and the agent reads back a summary of your decisions and comments. It also works on its own for backlogs, code reviews, ideas or audits, with optional AI suggestions (bring your own key).

## Highlights

- **Zero dependencies**: 100% Python standard library (`server.py`). No `pip install`, no bundler, starts instantly.
- **Mobile-first, keyboard on desktop**: smooth physical swipe on phones (`passive: false`), arrow keys and dedicated keys (`a` / `d` / `w`) on desktop.
- **Built-in BYOK**: works with any OpenAI-compatible API (OpenAI `gpt-4o-mini`, local Ollama `llama3.2`, Groq, OpenRouter) and custom scoring webhooks.
- **Plain JSON storage**: decks are readable JSON files that scripts and AI agents can edit (`deck_cli.py`).
- **Calm by design**: no anxiety-inducing counters while you sort, decision history available at any time, a note field per card, and full undo (`Ctrl+Z`).

Note: the interface strings are currently in French.

## Quickstart

### Option A: local (zero dependencies)

```bash
git clone https://github.com/2umish8/quick-pick.git
cd quick-pick
python3 server.py
```

Open **`http://localhost:8791`** in your browser.

### Option B: Docker Compose (recommended for self-hosting)

```bash
docker compose up -d
```

The service runs on port `8791` and persists data in `./data/decks`.

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
| `QUICK_PICK_DATA_DIR` | `./data/decks` | Folder where deck JSON files are stored |
| `QUICK_PICK_ALLOW_PRIVATE_ENDPOINTS` | `1` | Let the AI proxy call local/private endpoints (e.g. Ollama on `127.0.0.1:11434`) |

## AI suggestions and BYOK (bring your own key)

Quick-Pick does not require any paid or proprietary model. Click the **⚙️** icon in the header to configure suggestions:

1. **OpenAI / Ollama / Groq protocol**:
   - **Base URL**: `https://api.openai.com/v1`, `http://localhost:11434/v1`, or `https://api.groq.com/openai/v1`
   - **Model**: `gpt-4o-mini`, `llama3.2`, `mistral`, etc.
   - **API key**: your private key. It is saved in plain text in your browser's `localStorage` and is not stored by the server. It is, however, sent to your Quick-Pick server with each test and suggestion request, and the server forwards it as an `Authorization: Bearer` header to the endpoint you configured. Only enter it on a Quick-Pick instance you control.
2. **Custom webhook / API**:
   - Enter the URL of your own scoring endpoint. It receives the payload `{ id, title, description, bullets, candidate_actions }`.

## Using Quick-Pick with AI agents

Quick-Pick solves the **"wall of text"** problem in LLM chats (Hermes, Claude, Cursor, OpenCode, Aider). Instead of asking 20 multiple-choice questions in one message, an agent prepares a deck of cards, gives the link to the human, then reads back the decisions:

1. **The agent creates the deck**:
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
3. **The agent reads the decisions back**:
   ```bash
   python3 deck_cli.py summary pr-review --format md
   ```
   The agent gets the decisions and comments and resumes its work asynchronously, without blocking the conversation.
4. **Agent skill**: [`skills/quick-pick/SKILL.md`](skills/quick-pick/SKILL.md) can be dropped into your agent environment (`~/.agents/skills/quick-pick/`).

## Command line (`deck_cli.py`)

Scripts and AI agents can drive decks from the command line:

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

# 7. Test the connection to an external classifier
python3 deck_cli.py classifier --endpoint http://localhost:11434/v1
```

## Deck format (`data/decks/<id>.json`)

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

## Security and production deployment

Quick-Pick is designed for a single user or an internal team:

- There is no built-in authentication. To expose it on the internet, put it behind a reverse proxy with authentication (Caddy with Basic Auth, Traefik, Authelia, Cloudflare Access) or on a private network such as Tailscale.
- Anyone who can reach the server can also use its AI proxy (`/api/classifier/*`). With `QUICK_PICK_ALLOW_PRIVATE_ENDPOINTS=1` (the default), that includes local and private addresses; set it to `0` if you don't need a local model.
- Security headers are set by default (`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`).
- The AI proxy blocks cloud metadata services (AWS/GCP) and link-local addresses, and request bodies are limited to 2 MB.

## Tests

```bash
python3 -m unittest discover tests
```

## License

Released under the **MIT** license. Free to use, modify and self-host.

Quick-Pick by [Mowtif](https://mowtif.com)
