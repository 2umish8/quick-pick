FROM python:3.12-alpine

WORKDIR /app

# Copie du code source
COPY . /app

# Configuration d'écoute conteneur (0.0.0.0 indispensable pour Docker)
ENV QUICK_PICK_HOST=0.0.0.0
ENV QUICK_PICK_PORT=8791
ENV QUICK_PICK_DATA_DIR=/app/data/decks
# Private classifier endpoints blocked by default (0). Opt in for Ollama/local
# LLM with QUICK_PICK_ALLOW_PRIVATE_ENDPOINTS=1 (e.g. endpoint host.docker.internal).
ENV QUICK_PICK_ALLOW_PRIVATE_ENDPOINTS=0
# No token hardcoded here: pass QUICK_PICK_TOKEN at runtime (required with 0.0.0.0).

EXPOSE 8791

# Persistance des decks de décision
VOLUME ["/app/data/decks"]

CMD ["python3", "server.py"]
