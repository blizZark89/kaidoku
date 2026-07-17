# Lokale Installation von Kaidoku (v0.6.6)

Diese Anleitung beschreibt die Einrichtung einer lokalen Kaidoku-Entwicklungsumgebung
ohne Authentik/SSO. Für den Produktivbetrieb mit Authentik siehe
[Authentik-Installation](authentik_installation.md).

---

## Voraussetzungen

- **Python 3.10+**
- **Git**
- **uv** (Python-Paketmanager) — [Installation](https://docs.astral.sh/uv/getting-started/installation/)
- **Plattenplatz**: ca. 10 GB frei (`.venv` wird ~8.5 GB)
- Optional: **Docker** (nur für Server-Deployment)

---

## 1. Repository klonen

```bash
git clone git@github.com:blizZark89/kaidoku.git
cd kaidoku
```

---

## 2. .env-Datei erstellen

```bash
cp .env.example .env
```

Mindestens diese Werte anpassen:

```ini
# OpenAI API-Key (erforderlich für Chat + Embeddings)
OPENAI_API_KEY=sk-...

# Optional: Andere Provider
# COHERE_API_KEY=...
# VOYAGE_API_KEY=...
```

---

## 3. Abhängigkeiten installieren

```bash
uv sync
```

> Dies lädt große ML-Pakete (torch ~850 MB, nvidia-cudnn ~670 MB) und dauert
> 5–15 Minuten. Die fertige `.venv` ist ca. 8.5 GB groß.

---

## 4. App starten

```bash
source .venv/bin/activate
python app.py
```

Die App öffnet sich automatisch im Browser unter `http://127.0.0.1:7860`.

---

## 5. Ersteinrichtung

Beim ersten Start:

1. Standard-Login: **admin** / **admin**
2. Im Tab **Einstellungen** das Admin-Passwort ändern
3. Unter **Ressourcen > LLMs** den API-Key und das Modell konfigurieren
4. Unter **Ressourcen > Embeddings** das Embedding-Modell konfigurieren

---

## 6. Optional: Lokales Modell via Ollama

```bash
# Ollama installieren (https://ollama.com)
ollama pull qwen2.5:7b
ollama pull nomic-embed-text

# In .env eintragen:
# LOCAL_MODEL=qwen2.5:7b
# LOCAL_MODEL_EMBEDDINGS=nomic-embed-text
```

---

## Verzeichnisstruktur nach der Installation

```
kaidoku/
├── .venv/              # Python-Umgebung (8.5 GB)
├── ktem_app_data/      # Datenverzeichnis (wird bei Start erstellt)
│   ├── user_data/      # SQLite-DB, Dateien, Indizes
│   └── huggingface/    # HF-Modelle
├── app.py              # Einstiegspunkt
├── flowsettings.py     # Konfiguration
└── .env                # API-Keys & Einstellungen
```

---

## Häufige Probleme

| Problem | Lösung |
|---|---|
| `ModuleNotFoundError: No module named 'theflow'` | `uv sync` ausführen (nicht `pip install`) |
| App startet nicht, Port belegt | `lsof -i :7860` — ggf. alten Prozess killen |
| Zu wenig Plattenplatz | `rm -rf .venv` löscht die Umgebung (~8.5 GB frei) |
| `uv sync` dauert ewig | Normal — lädt große ML-Pakete. Hintergrundprozess empfehlenswert |
