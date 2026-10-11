# Base image pinned by digest (multi-arch manifest list of python:3.12-alpine).
# To refresh: docker pull python:3.12-alpine && docker image inspect --format '{{index .RepoDigests 0}}' python:3.12-alpine
FROM python:3.12-alpine@sha256:1b668429b3511ab407d8e00648891631b0b1a4d7e15e3ca70f38ab5b91ad4ab4

# Unprivileged runtime user. Fixed UID 10001 so bind-mounted volumes stay usable
# (see README for the docker compose override).
RUN adduser -D -u 10001 -h /home/quickpick quickpick

WORKDIR /app

COPY --chown=quickpick:quickpick . /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Container listen address (0.0.0.0 is required inside Docker).
ENV QUICK_PICK_HOST=0.0.0.0
ENV QUICK_PICK_PORT=8791
ENV QUICK_PICK_DATA_DIR=/app/data/decks
# Private classifier endpoints blocked by default (0). Opt in for Ollama/local
# LLM with QUICK_PICK_ALLOW_PRIVATE_ENDPOINTS=1 (e.g. endpoint host.docker.internal).
ENV QUICK_PICK_ALLOW_PRIVATE_ENDPOINTS=0
# No token hardcoded here: pass QUICK_PICK_TOKEN at runtime (required with 0.0.0.0).

# data/ is not in the image, so create the writable mount point up front.
RUN mkdir -p "$QUICK_PICK_DATA_DIR" && chown quickpick:quickpick "$QUICK_PICK_DATA_DIR"

USER quickpick

EXPOSE 8791

# Deck persistence (never versioned, see .gitignore).
VOLUME ["/app/data/decks"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python3 -c "import os,urllib.request as u;u.urlopen(u.Request('http://127.0.0.1:' + os.environ.get('QUICK_PICK_PORT', '8791') + '/api/health', headers={'X-Quick-Pick-Token': os.environ.get('QUICK_PICK_TOKEN', '')}), timeout=4)"

CMD ["python3", "server.py"]
