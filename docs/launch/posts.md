# Quick-Pick : brouillons de lancement (MOW-190)

Brouillons uniquement, rien n'est publié. Aucun chiffre d'usage : n'en ajoutez pas tant qu'on n'en a pas de réels.
Pré-requis avant toute publication : GIF `docs/demo.gif` en place (et décommenter la ligne TODO des README). README anglais et MOW-188 (mode direct navigateur, jeton d'API) sont livrés en v2.1.0 : les brouillons ci-dessous en tiennent compte.

---

## (a) Show HN

### Titres (< 80 caractères)

1. `Show HN: Quick-Pick – swipe cards so your AI agent can ask 20 questions at once` (79)
2. `Show HN: Quick-Pick – answer your coding agent's questions by swiping cards` (75)
3. `Show HN: Quick-Pick – a zero-dependency card stack for fast yes/no/later triage` (79)

Recommandé : 1 (l'angle agent est le plus distinctif). Lien : https://github.com/2umish8/quick-pick

### Premier commentaire (Mischael)

> Hi HN, I'm Mischael. I build most of my projects with several AI agents running in parallel (coding agents, plus a few assistants for planning and audits). The bottleneck kept being me: every agent would end its turn with a long message containing 15–20 questions ("keep or drop this dependency?", "approve this rule?", "now or later?"), and I'd answer them in a messy reply that the agent then had to parse.
>
> Quick-Pick is my fix for that. The agent writes the questions as a JSON deck (or pipes them into `deck_cli.py`), sends me a link, and I go through them one card at a time: swipe on my phone, or arrow keys / a-d-w on desktop, with an optional note per card. When I'm done, the agent runs `deck_cli.py summary <deck> --format md` and gets my decisions and comments back. There's a SKILL.md so agents that support skills know how to use it.
>
> It also works without agents, for backlog triage, code review items or audits.
>
> Stack: Python standard library only (`python3 server.py`, no pip install), vanilla JS front end, decks stored as plain JSON files, Docker Compose if you prefer. Optional AI suggestions per card with your own key, through any OpenAI-compatible API (OpenAI, Groq, OpenRouter, local Ollama) or a custom webhook. MIT licensed.
>
> Caveats: it's meant for a single user or a small internal team; auth is a single shared API token (required as soon as it listens beyond localhost), so for internet exposure put it behind a reverse proxy or Tailscale. The UI strings are in French for now.
>
> What I'd like feedback on:
> - If you use coding agents: is "agent asks, human swipes, agent reads back" a workflow you'd actually use, or do you handle this differently?
> - The deck format and CLI: anything missing for your agent setup?
> - The BYOK design: by default the key goes through your own Quick-Pick server, with an opt-in direct browser mode for CORS-enabled providers. Which would you use?


---

## (b) Reddit

**Lire les règles d'autopromo de chaque subreddit avant de poster** (ratio 9:1, jours dédiés, flair obligatoire, interdiction des liens en premier post, etc.). Poster depuis le compte de Mischael, répondre aux commentaires soi-même, ne pas cross-poster le même jour.

### r/selfhosted (angle zéro dépendance / Docker / Ollama)

**Titre :** Quick-Pick: a tiny self-hosted card stack for triaging decisions (Python stdlib only, Docker Compose, optional Ollama)

**Corps :**

> I made a small self-hosted tool to sort through lists of decisions one card at a time: backlog items, code review points, ideas, audit findings. Swipe on mobile, keyboard on desktop, with a note field and undo.
>
> Why it might fit here:
> - Zero dependencies: `python3 server.py` with the standard library only, no pip install, no build step.
> - Or `docker compose up -d` (with `QUICK_PICK_TOKEN` set), port 8791 on localhost, decks persisted as plain JSON in `./data/decks`.
> - Optional AI suggestions per card using your own endpoint: a local Ollama works (`http://localhost:11434/v1`), as do OpenAI-compatible APIs or a custom webhook.
> - A CLI (`deck_cli.py`) to create decks and pull a Markdown/JSON summary, so scripts or AI agents can feed it.
>
> Honest limitations: auth is a single shared API token (Docker requires it and publishes on 127.0.0.1 only), so for remote access it's meant to sit behind your reverse proxy / Authelia / Tailscale; single user or small team; UI in French for now.
>
> MIT, repo: https://github.com/2umish8/quick-pick
>
> Feedback on the Docker setup and what you'd want before running it on your homelab is welcome.

### r/LocalLLaMA (angle BYOK / Ollama local)

**Titre :** I built a swipe-card UI so local agents can ask me batches of questions; suggestions can run on Ollama

**Corps :**

> When I work with agents, I end up answering long lists of small questions in chat. Quick-Pick turns those into a deck of cards: the agent creates the deck from JSON, I swipe through it (or use the keyboard), and the agent reads my decisions back with `deck_cli.py summary`.
>
> The local-model part: each card can show a suggested action from any OpenAI-compatible endpoint. I use it with Ollama (`http://localhost:11434/v1`, e.g. `llama3.2` or `mistral`; local endpoints are opt-in with `QUICK_PICK_ALLOW_PRIVATE_ENDPOINTS=1`); OpenAI, Groq and OpenRouter work too, or a custom webhook. The model gets the card's title, description, bullets and the candidate actions, and returns `{action, confidence, reasoning}`. Nothing is required: without a model it's just a fast manual triage UI.
>
> Runs on Python's standard library only (or Docker Compose), decks are plain JSON, MIT.
>
> https://github.com/2umish8/quick-pick
>
> Curious which small local models people find reliable for this kind of single-label classification with strict JSON output.

### r/ClaudeAI ou r/ChatGPTCoding (angle skill agent)

**Titre :** Stop answering your coding agent's 20 questions in one wall of text: I made a swipe-card skill for it

**Corps :**

> My agents (Claude, Cursor and others) often finish a task with a long list of questions: keep or remove this, approve this change, now or later. Answering in chat is slow and easy to get wrong.
>
> Quick-Pick is a small open-source tool for that loop:
> 1. The agent pipes the questions as JSON into `deck_cli.py create`.
> 2. It sends me a link like `http://localhost:8791/#pr-review`.
> 3. I swipe through the cards on my phone or use the keyboard, adding a note when needed.
> 4. The agent runs `deck_cli.py summary pr-review --format md` and continues with my decisions.
>
> The repo ships a `skills/quick-pick/SKILL.md` you can drop into your agent's skills folder so it knows when and how to use it. Zero dependencies (Python stdlib), Docker Compose optional, MIT.
>
> https://github.com/2umish8/quick-pick
>
> I'd love to hear how others handle batches of decisions from agents, and whether the skill file works well with your setup.

Note : vérifier les règles du sub choisi (r/ClaudeAI exige souvent un flair et des posts liés à Claude ; r/ChatGPTCoding tolère mieux les outils multi-agents).

---

## (c) X (fil de 3 posts)

**1/3** (avec `docs/demo.gif`)
> My AI agents kept ending their turn with 20 questions in one wall of text.
>
> So I built Quick-Pick: the agent turns them into a stack of cards, I swipe through them, it reads my decisions back.
>
> Open source, MIT 👇
> [GIF]

**2/3**
> How it works:
> • agent pipes JSON into `deck_cli.py create`
> • sends me a link
> • I swipe on mobile or use the keyboard, with notes
> • agent runs `deck_cli.py summary` and keeps going
>
> Ships with a SKILL.md for agents that support skills.

**3/3**
> Zero dependencies: `python3 server.py`, or Docker Compose.
> Optional per-card suggestions with your own key: OpenAI, Groq, OpenRouter or local Ollama.
>
> Feedback welcome: https://github.com/2umish8/quick-pick

---

## (d) LinkedIn (français, build in public)

> Je construis la plupart de mes projets avec plusieurs agents IA en parallèle. Et le goulot d'étranglement, c'était moi.
>
> Chaque agent finissait son tour par un long message : 15, 20 questions. « On garde cette dépendance ? », « Je valide cette règle ? », « Maintenant ou plus tard ? ». Je répondais dans un pavé de texte, l'agent devait le relire et l'interpréter. Lent pour moi, fragile pour lui.
>
> Alors j'ai construit Quick-Pick, et je viens de le publier en open source.
>
> Le principe :
> → l'agent transforme ses questions en pile de cartes
> → il m'envoie un lien
> → je tranche une carte à la fois, en swipant sur mon téléphone ou au clavier, avec une note si besoin
> → l'agent récupère la synthèse de mes décisions et reprend son travail
>
> Côté technique, j'ai voulu quelque chose de très simple à faire tourner : uniquement la bibliothèque standard Python, aucune dépendance, ou Docker Compose. Les suggestions IA sont optionnelles, avec votre propre clé (OpenAI, Groq, OpenRouter) ou un modèle local via Ollama. Licence MIT.
>
> Ça sert aussi sans agent : trier un backlog, une relecture de code, une liste d'idées.
>
> C'est encore jeune (l'interface est en français pour l'instant, et l'authentification se limite à un jeton d'API partagé). Si vous travaillez avec des agents de code, je suis preneur de vos retours : est-ce que ce mode « l'agent demande, l'humain swipe » vous parle ?
>
> Le repo : https://github.com/2umish8/quick-pick
>
> #BuildInPublic #OpenSource #IA
