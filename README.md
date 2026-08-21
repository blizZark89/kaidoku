## Installation

### Systemvoraussetzungen

1. [Python](https://www.python.org/downloads/) >= 3.10
2. [Docker](https://www.docker.com/): optional, falls du [mit Docker installieren](#mit-docker-empfohlen) moechtest
3. [Unstructured](https://docs.unstructured.io/open-source/installation/full-installation#full-installation) wenn du Dateien verarbeiten moechtest, die nicht `.pdf`, `.html`, `.mhtml` oder `.xlsx` sind. Die Installation unterscheidet sich je nach Betriebssystem. Bitte folge dem Link und den dortigen Anweisungen.

### PDF-Viewer

Um den integrierten `PDF_JS viewer` zu aktivieren, lade [PDF_JS_DIST](https://github.com/mozilla/pdf.js/releases/download/v4.0.379/pdfjs-4.0.379-dist.zip) herunter und entpacke ihn nach `libs/ktem/ktem/assets/prebuilt`

<img src="https://raw.githubusercontent.com/Cinnamon/kotaemon/main/docs/images/pdf-viewer-setup.png" alt="pdf-setup" width="250">

### Docling (fuer .pptx, .docx, .xlsx Unterstuetzung)

Fuer die Verarbeitung von Office-Dateien (.pptx, .docx, .xlsx) wird `docling` benoetigt.

**Docker (empfohlen):** Im Dockerfile ist docling im `full`-Target enthalten (nicht im `lite`-Target). Stelle sicher, dass du den `full`-Build verwendest.

**Lokale Installation:**
```shell
deactivate 2>/dev/null || true
apt update
apt install -y curl ca-certificates build-essential
cd ~/kaidoku
rm -rf .venv
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv python install 3.12
uv venv --python 3.12 .venv
source .venv/bin/activate
python -V
python -m pip install --upgrade "pip<26" setuptools wheel
python -m pip install "docling==2.5.2"
deactivate
```

### Mit Docker (empfohlen)

```shell
git clone https://github.com/blizzark89/kaidoku.git
cd kaidoku
```

```shell
nano docker-compose.yaml

services:
  kaidoku:
    build:
      context: .
      # Falls im Repo ein spezielles Dockerfile fuer "Full" existiert, hier den Pfad angeben:
      dockerfile: Dockerfile 
    container_name: kaidoku
    restart: unless-stopped
    environment:
      - TZ=Europe/Berlin
      - GRADIO_SERVER_NAME=0.0.0.0
      - GRADIO_SERVER_PORT=7860
      - GRADIO_ALLOW_CORS=true
      - GRADIO_SAMESITE="none"
      - KH_LOCALE=de
      - KH_FEATURE_USER_MANAGEMENT=True
    volumes:
      - ./kaidoku_app_data:/app/ktem_app_data
      # fuer FileSync: Links Host-Pfad, Rechts Container-Pfad
      - /app/sync-data:/app/sync-data
    ports:
      - "7860:7860"
```

```shell
docker compose up -d --build
docker ps
```


## Update:
```shell
cd ~/kaidoku
docker compose down
docker builder prune -a -f
docker buildx prune -a -f
docker image prune -a -f
docker system prune -a -f
df -h
docker system df
git pull origin main
docker compose build
docker compose up -d
docker ps
```
