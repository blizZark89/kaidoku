# Anleitung: Rolle User

## Überblick
Als `user` nutzt du die Plattform für deine tägliche Arbeit, ohne Verwaltungsaufgaben.

## Was ist Kaidoku?

Kaidoku ist eine lokal betreibbare RAG-Anwendung (Retrieval-Augmented Generation).
Sie kombiniert:

- Chat mit KI-Modellen
- Dokumentensuche und -analyse
- Wissensaufbereitung aus eigenen Dateien
- Verwaltung von Inhalten und Datenquellen

Die Anwendung laeuft lokal und kann ohne Cloud-Abhaengigkeit betrieben werden.

---

## Zentrale Funktionen

### 1. Chat mit Dokumentbezug

- Nutzer koennen normale Chats mit KI fuehren
- Antworten koennen auf eigenen Dokumenten basieren
- Mehrere Reasoning-Ansaetze stehen zur Verfuegung (z. B. einfache QA, Agentenlogik)

Typischer Ablauf:
1. Chat starten
2. Dokumente oder Gruppen auswaehlen
3. Frage stellen
4. System sucht relevante Inhalte
5. KI generiert eine Antwort auf Basis dieser Inhalte

---

### 2. Dokumentenverwaltung

- Dateien koennen hochgeladen und indexiert werden
- Inhalte werden durchsuchbar gemacht
- Unterstuetzung fuer viele Formate:
  - PDF, DOCX, PPTX
  - Excel, CSV
  - Bilder
  - Markdown, Text, HTML
  - ZIP-Dateien

Nach dem Upload:
- Dokumente werden analysiert
- Inhalte werden in Suchindizes ueberfuehrt
- Dokumente stehen fuer den Chat zur Verfuegung

---

### 3. Dateigruppen

- Dokumente koennen in Gruppen organisiert werden
- Gruppen erleichtern die strukturierte Suche
- Gruppen koennen automatisch oder manuell gepflegt werden

Im Chat kann gezielt gesucht werden:
- in einzelnen Dateien
- in Gruppen
- oder global

---

### 4. Intelligente Suche (RAG)

- Inhalte werden in Vektor-Datenbanken gespeichert
- Relevante Textstellen werden automatisch gefunden
- Kombination aus:
  - Retrieval (Suche)
  - Generierung (LLM-Antwort)

Zusaetzlich moeglich:
- Reranking (bessere Trefferreihenfolge)
- verschiedene Embedding-Modelle

---

### 5. Reasoning & KI-Pipelines

Mehrere Verarbeitungsstrategien sind integriert:

- klassische Frage-Antwort
- zerlegte Fragen (Decomposition)
- Agenten-basierte Ansaetze (z. B. ReAct, ReWOO)

Dadurch koennen:
- komplexe Fragen beantwortet werden
- mehrstufige Probleme geloest werden

---

### 6. Ressourcenverwaltung

Die App kann verschiedene KI-Komponenten verwalten:

- LLMs (z. B. OpenAI, Ollama, Gemini, Claude)
- Embedding-Modelle
- Reranking-Modelle
- MCP-Server
- Index-Sammlungen

Das erlaubt flexible Anpassung an:
- lokale Modelle
- externe APIs
- unterschiedliche Anwendungsfaelle

---

### 7. FileSync (automatischer Import)

- Ueberwacht einen lokalen Ordner
- Importiert neue oder geaenderte Dateien automatisch
- Entfernt geloeschte Dateien auch aus dem System

Funktionen:
- regelmaessiges Scannen
- automatische Zuordnung
- automatische Gruppenbildung
- Fehlererkennung bei defekten Dateien

Ziel:
-> Dokumente ohne manuelles Hochladen aktuell halten

---

### 8. Benutzeroberflaeche

Die App bietet mehrere Hauptbereiche:

- **Chat** -> Arbeiten mit KI
- **Dateien** -> Dokumente und Gruppen verwalten
- **Ressourcen** -> Modelle und Systeme konfigurieren
- **Einstellungen** -> App- und Benutzerkonfiguration
- **Hilfe** -> Unterstuetzung

---

### 9. Teams & Sichtbarkeit (konzeptionell)

- Inhalte koennen bestimmten Gruppen zugeordnet werden
- Sichtbarkeit von Dokumenten wird darueber gesteuert
- globale Inhalte sind fuer alle sichtbar

Zusaetzlich:
- Standardkontext kann fuer Suchen genutzt werden

---

### 10. Speicherung & Betrieb

- lokale Datenhaltung (SQLite)
- Vektor-Datenbanken (Chroma)
- Dokumentenspeicher (LanceDB)

Alle Daten liegen im lokalen App-Verzeichnis:
- keine zwingende externe Abhaengigkeit

---

## Technische Highlights

- vollstaendig lokal betreibbar
- Docker-faehig
- deutsche Oberflaeche
- modular erweiterbar
- unterstuetzt viele KI-Anbieter
- robuste Dokumentverarbeitung (auch Office-Dateien)

---

## Kurz gesagt

Kaidoku ist eine lokale Wissensplattform mit KI-Unterstuetzung:

- Dokumente hochladen oder automatisch synchronisieren
- Inhalte durchsuchen
- Fragen stellen
- fundierte Antworten aus eigenen Daten erhalten

-> Ziel: internes Wissen effizient nutzbar machen

## Was du typischerweise tust

### Arbeiten mit der Anwendung
- Führe Chats
- Nutze vorhandene Dokumente
- Suche in Dateien und Dateigruppen

### Dokumente nutzen
- Greife auf Inhalte deines Teams zu
- Verwende dein Standardteam als Filter im Chat

### Optional: Dokumente hochladen
- Nur möglich, wenn dir Upload-Rechte gegeben wurden

### Eigene Einstellungen
- Ändere dein Passwort
- Wähle dein Standardteam

## Was du NICHT tun kannst
- Keine Benutzer verwalten
- Keine Teams verwalten
- Keine Systemeinstellungen ändern
- Kein FileSync

## Wichtige Hinweise
- Du musst mindestens einem Team angehören
- Ohne Upload-Recht kannst du nur lesen

## Best Practice
- Nutze dein Standardteam sinnvoll
- Lade nur relevante Dokumente hoch
- Halte deine Inhalte übersichtlich
