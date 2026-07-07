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
apt update
apt install -y python3-full python3-venv

cd ~/kaidoku
python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip setuptools wheel
python -m pip install "docling<=2.5.2"
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
git pull origin main
docker compose down
docker compose build
docker compose up -d --build
docker system prune -f
docker ps
```
