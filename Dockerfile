# ==========================================
# STAGE 1: Lite Version (Basis)
# ==========================================
FROM python:3.10-slim AS lite

# System-Abhängigkeiten installieren
RUN apt-get update -qqy && \
    apt-get install -y --no-install-recommends \
        ssh \
        git \
        gcc \
        g++ \
        poppler-utils \
        libpoppler-dev \
        unzip \
        zstd \
        curl \
        cargo \
        && \
    apt-get autoremove && apt-get clean && rm -rf /var/lib/apt/lists/*

# Setup-Argumente
ARG TARGETPLATFORM
ARG TARGETARCH

# Umgebungsvariablen setzen
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=UTF-8
ENV TARGETARCH=${TARGETARCH}

WORKDIR /app

# PDF.js herunterladen
COPY scripts/download_pdfjs.sh /app/scripts/download_pdfjs.sh
RUN chmod +x /app/scripts/download_pdfjs.sh
ENV PDFJS_PREBUILT_DIR="/app/libs/ktem/ktem/assets/prebuilt/pdfjs-dist"
RUN bash scripts/download_pdfjs.sh $PDFJS_PREBUILT_DIR

# Installiere uv für schnelles Paketmanagement
RUN pip install --no-cache-dir "uv"

# Projektdateien kopieren
COPY . /app
COPY launch.sh /app/launch.sh
COPY .env.example /app/.env

# Python-Abhängigkeiten installieren
RUN --mount=type=ssh  \
    --mount=type=cache,target=/root/.cache/uv  \
    uv sync --frozen --no-cache \
    && uv pip install --python .venv "pdfservices-sdk@git+https://github.com/niallcm/pdfservices-python-sdk.git@bump-and-unfreeze-requirements"

RUN --mount=type=ssh  \
    --mount=type=cache,target=/root/.cache/uv  \
    if [ "$TARGETARCH" = "amd64" ]; then uv pip install --python .venv "graphrag<=0.3.6" future; fi

ENTRYPOINT ["sh", "/app/launch.sh"]

# ==========================================
# STAGE 2: Full Version (Kaidoku Standard)
# ==========================================
FROM lite AS full

# Zusätzliche Tools für OCR, Dokumentenkonvertierung und Medien
RUN apt-get update -qqy && \
    apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-jpn \
        libsm6 \
        libxext6 \
        libreoffice \
        ffmpeg \
        libmagic-dev \
        && \
    apt-get autoremove && apt-get clean && rm -rf /var/lib/apt/lists/*

# PyTorch installieren (CPU-Version, um Platz zu sparen)
RUN --mount=type=ssh  \
    --mount=type=cache,target=/root/.cache/uv  \
    uv pip install --python .venv torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu

# Zusätzliche KI-Bibliotheken (Advanced Features)
RUN --mount=type=ssh  \
    --mount=type=cache,target=/root/.cache/uv  \
    uv pip install --python .venv "libs/kotaemon[adv]" \
    && uv pip install --python .venv unstructured[all-docs]

# LightRAG und Ollama-Client (nur Python-Library, nicht der Server!)
ENV USE_LIGHTRAG=true
RUN --mount=type=ssh  \
    --mount=type=cache,target=/root/.cache/uv  \
    uv pip install --python .venv aioboto3 nano-vectordb ollama xxhash "lightrag-hku<=1.3.0"

# Docling für Dokumenten-Parsing
RUN --mount=type=ssh  \
    --mount=type=cache,target=/root/.cache/uv  \
    uv pip install --python .venv "docling<=2.5.2"

# Initialisierung von LlamaIndex (lädt Basis-NLTK Daten)
RUN /app/.venv/bin/python -c "from llama_index.core.readers.base import BaseReader"

# Startskript ausführen
ENTRYPOINT ["sh", "/app/launch.sh"]
