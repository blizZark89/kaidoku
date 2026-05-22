# Kaidoku - Zusammenfassung für Administratoren/Installierer

## Was ist Kaidoku?

Kaidoku ist eine lokal betreibbare RAG-Anwendung (Retrieval-Augmented Generation). Sie kombiniert Chat mit KI-Modellen, Dokumentensuche, Wissensaufbereitung aus eigenen Dateien und Verwaltung von Inhalten und Datenquellen. Die Anwendung läuft ohne Cloud-Abhängigkeit und eignet sich für den Betrieb in geschlossenen Umgebungen.

---

## Architektur und Kernkomponenten

### Retrieval-Augmented Generation (RAG)
- Inhalte werden in Vektor-Datenbanken gespeichert.
- Relevante Textstellen werden automatisch gefunden.
- Kombination aus Retrieval (Suche) und Generierung (LLM-Antwort).
- Optional: Reranking für bessere Trefferreihenfolge und verschiedene Embedding-Modelle.

### Reasoning und KI-Pipelines
- Klassische Frage-Antwort.
- Zerlegte Fragen (Decomposition).
- Agenten-basierte Ansätze wie ReAct oder ReWOO.
- Ermöglicht die Beantwortung komplexer Fragen und Lösung mehrstufiger Probleme.

---

## Technische Infrastruktur

### Lokale Datenhaltung
- **SQLite** –_relationale Datenbank für Metadaten und Konfiguration.
- **Chroma** –Vektor-Datenbank für semantische Suche.
- **LanceDB** –Dokumentenspeicher.

Alle Daten liegen im lokalen App-Verzeichnis. Es besteht keine zwingende externe Abhängigkeit.

### Unterstützte Dokumentformate
- PDF, DOCX, PPTX
- Excel, CSV
- Bilder
- Markdown, Text, HTML
- ZIP-Dateien

Nach dem Upload werden Dokumente analysiert und in Suchindizes überführt. Der Status wird in der Datei-Liste angezeigt.

---

## Ressourcenverwaltung

Die App verwaltet verschiedene KI-Komponenten:

- **LLMs** – z. B. OpenAI, Ollama, Gemini, Claude.
- **Embedding-Modelle** –für die Umwandlung von Text in Vektoren.
- **Reranking-Modelle** –für die Optimierung der Suchergebnisse.
- **MCP-Server** –für erweiterte Funktionalitäten.
- **Index-Sammlungen** –für die Organisation der Vektor-Daten.

Das erlaubt flexible Anpassung an lokale Modelle, externe APIs und unterschiedliche Anwendungsfälle.

---

## FileSync (Automatischer Import)

FileSync überwacht definierte Ordner und hält alle Dateien automatisch aktuell im System.

**Erkennung von Änderungen:**
- Jede Datei wird beim Einlesen mit einem Hashwert versehen.
- Bei jedem Scan wird der Hash erneut berechnet.
- Gleicher Hash -> keine Aktion.
- Unterschiedlicher Hash -> Datei wird neu importiert und aktualisiert.

**Konkrete Auswirkungen:**
- Geänderte Dateien werden neu indexiert.
- Alte Versionen werden ersetzt oder aktualisiert.
- Neue Dateien werden erkannt, importiert und einer Gruppe zugeordnet.
- Gelöschte Dateien werden auch im System entfernt.
- Defekte Dateien werden erkannt und gemeldet.

**Hintergrundlogik:**
- FileSync merkt sich den zuletzt bekannten Hash pro Datei.
- FileSync merkt sich, ob eine Datei bereits importiert wurde.
- FileSync merkt sich die Zuordnung Ordner -> Dateigruppe.
- Dadurch werden nur echte Inhaltsänderungen verarbeitet.

---

## Teams und Sichtbarkeit (Admin-Perspektive)

Zwei unabhängige Ebenen existieren:

- **Dateiebene** –Einzeldokumente können Teams zugeordnet werden.
- **Gruppenebene** –Dateigruppen können separate Team-Zuordnungen erhalten.

**Sichtbarkeitsregeln:**
- Admins sehen alle Inhalte.
- Globale Teams sind für alle Nutzer sichtbar.
- Inhalte ohne Team-Zuordnung sind nur für den Ersteller sichtbar.
- Inhalte mit Team-Zuordnung sind nur für Mitglieder dieser Teams sichtbar.

Im Chat wird der Team-Filter je nach Such-Modus auf Datei- oder Gruppenebene angewendet.

---

## Betrieb

- Vollständig lokal betreibbar.
- Docker-fähig.
- Deutsche Oberfläche verfügbar.
- Modular erweiterbar.
- Unterstützt viele KI-Anbieter.
- Robuste Dokumentverarbeitung, auch für Office-Dateien.

---

## Kurz gesagt

Kaidoku ist eine lokale Wissensplattform mit KI-Unterstützung:

1. Dokumente hochladen oder automatisch synchronisieren.
2. Inhalte indizieren und durchsuchen.
3. Flexible KI-Pipelines und Modelle konfigurieren.
4. Benutzern gezielten Zugriff auf Wissen über Teams ermöglichen.

-> Ziel: Internes Wissen effizient und sicher nutzbar machen.
