FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/opt/hf-cache

# upgrade pulls the latest Debian security fixes into the base image's
# packages; rebuild regularly (see "Updating" in DEPLOY.md) to keep getting them.
RUN apt-get update \
 && apt-get upgrade -y \
 && apt-get install -y --no-install-recommends ffmpeg curl \
 && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 10001 app
WORKDIR /app

# CPU-only PyTorch: the default build bundles CUDA (several GB) and the server has no GPU.
ARG TORCH_VERSION=2.13.0
RUN pip install --index-url https://download.pytorch.org/whl/cpu "torch==${TORCH_VERSION}"

COPY requirements-prod.txt .
RUN pip install -r requirements-prod.txt

# Bake the embedding and reranker models into the image, so the container
# starts without downloading anything and runs with the Hub offline.
ARG RERANK_MODEL=cross-encoder/ms-marco-MiniLM-L6-v2
RUN python -c "from sentence_transformers import SentenceTransformer, CrossEncoder; \
SentenceTransformer('all-MiniLM-L6-v2'); CrossEncoder('${RERANK_MODEL}')" \
 && chown -R app:app /opt/hf-cache

# The code stays owned by root, so the app user can read but not change it;
# only /app/data is writable.
COPY . .
RUN mkdir -p /app/data && chown app:app /app/data

USER app

ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_CLIENT_SHOW_ERROR_DETAILS=none \
    STREAMLIT_CLIENT_TOOLBAR_MODE=viewer \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    HF_HUB_OFFLINE=1 \
    ANONYMIZED_TELEMETRY=False \
    AUTH_MODE=oidc \
    ENABLE_WHISPER=false \
    DATA_DIR=/app/data

EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fsS http://localhost:8501/_stcore/health || exit 1

# server.py runs app.py behind the upload gate (core/upload_gate.py).
CMD ["streamlit", "run", "server.py"]
