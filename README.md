## Installation

> If you are not a developer and just want to use the app, please check out our easy-to-follow [User Guide](https://cinnamon.github.io/kotaemon/). Download the `.zip` file from the [latest release](https://github.com/Cinnamon/kotaemon/releases/latest) to get all the newest features and bug fixes.

### System requirements

1. [Python](https://www.python.org/downloads/) >= 3.10
2. [Docker](https://www.docker.com/): optional, if you [install with Docker](#with-docker-recommended)
3. [Unstructured](https://docs.unstructured.io/open-source/installation/full-installation#full-installation) if you want to process files other than `.pdf`, `.html`, `.mhtml`, and `.xlsx` documents. Installation steps differ depending on your operating system. Please visit the link and follow the specific instructions provided there.

### With Docker (recommended)

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
      # Falls es im Repo ein spezielles Dockerfile für "Full" gibt, hier den Pfad angeben:
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
      # für FileSync Links Host-Pfad - Rechts Container-Pfad
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

