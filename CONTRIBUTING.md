# Contributing to Quick-Pick

Thanks for taking the time. Quick-Pick is a small, self-hosted, standard-library-only tool:
contributions are welcome when they stay reviewable and maintainable.

Before opening a pull request, read [`MAINTAINERS.md`](MAINTAINERS.md): it defines the
non-negotiable rules (data separation, backwards compatibility, no direct pushes to `main`).

## Scope of a contribution

- **One pull request = one topic.** Bug fix, feature, documentation or packaging. Mixing topics
  makes the review (and the merge) slower for everyone.
- **The maintainer decides the roadmap.** Issues and pull requests carry no commitment on timing.
- Keep the runtime free of third-party dependencies: standard library only on the server, vanilla
  ES modules in `public/`. A dependency needs a strong reason stated in the pull request.

## Development setup

```bash
git clone https://github.com/2umish8/quick-pick.git
cd quick-pick
python3 server.py          # http://localhost:8791
```

Install the lint tooling in a virtual environment (the application itself needs nothing):

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"    # ruff
```

## Checks to run before pushing

```bash
PYTHONPATH=. python3 -m unittest discover -s tests   # server + CLI tests
ruff check .                                          # lint (config lives in pyproject.toml)
for file in public/*.js; do node --check "$file"; done  # front-end syntax
```

The same three checks run in CI on every pull request (Python 3.11 and 3.12).

## Style

- Python: standard library only, dense handlers are fine (`if cond: return value`).
  The enabled ruff rules are `E4`, `E7`, `E9`, `F` minus `E401`/`E701`, see `pyproject.toml`.
- JavaScript: vanilla ES modules, no bundler, no framework.
- Code and comments in English.
- Commits follow `fix(scope):`, `feat(scope):`, `chore(scope):` and reference the ticket when there is one.
- Any behaviour change comes with a test in `tests/`.

## Data and secrets

- `data/` holds **your** decks and is never committed (it is git-ignored and seeded from
  `examples/decks/` on the first run).
- Never commit a `.env` file, an API key, personal data or a real deck taken from your instance.
  Private classifier endpoints belong in your browser storage or in `QUICK_PICK_*` environment variables.
- Security reports do not go through the public issue tracker: see [`SECURITY.md`](SECURITY.md).