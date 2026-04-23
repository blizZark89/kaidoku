# Anleitung: Allgemeiner Ueberblick

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
- Mehrere Reasoning-Ansaetze stehen zur Verfuegung, z. B. einfache QA oder Agentenlogik

#### 1.1 Dateisammlung

<table>
  <tr>
    <td valign="top" width="42%">
      <img src="images/1.1 Dateisammlung.PNG" alt="1.1 Dateisammlung" />
    </td>
    <td valign="top">

- **"Alle durchsuchen"**
  - durchsucht automatisch **alle verfuegbaren Dokumente** im aktuellen Suchbereich
  - keine manuelle Auswahl von Dateien oder Gruppen noetig

- **"In Dateien suchen"**
  - durchsucht **nur die explizit ausgewaehlten einzelnen Dokumente**
  - geeignet fuer gezielte Abfragen in bestimmten Dateien

- **"In Dateigruppen suchen"**
  - durchsucht **alle Dokumente innerhalb der ausgewaehlten Gruppen**
  - sinnvoll fuer strukturierte, thematische Suchen

- **Teamfilter ("Teams")**
  - "Alle Teams" -> Suche ueber **alle fuer dich sichtbaren Inhalte**
  - einzelnes Team -> Suche **nur innerhalb dieses Teams**

    </td>
  </tr>
</table>

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
- Reranking fuer bessere Trefferreihenfolge
- verschiedene Embedding-Modelle

---

### 5. Reasoning und KI-Pipelines

Mehrere Verarbeitungsstrategien sind integriert:

- klassische Frage-Antwort
- zerlegte Fragen (Decomposition)
- agenten-basierte Ansaetze, z. B. ReAct oder ReWOO

Dadurch koennen:
- komplexe Fragen beantwortet werden
- mehrstufige Probleme geloest werden

---

### 6. Ressourcenverwaltung

Die App kann verschiedene KI-Komponenten verwalten:

- LLMs, z. B. OpenAI, Ollama, Gemini, Claude
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

- Ueberwacht definierte Ordner und sorgt dafuer, dass alle Dateien automatisch aktuell im System sind

Wie Dateiunterschiede erkannt werden:
- Jede Datei wird beim Einlesen analysiert und mit einem Hashwert versehen
- Bei jedem weiteren Scan wird dieser Hash erneut berechnet
- Vergleich der Hashwerte: Gleich -> Datei ist unveraendert -> keine Aktion
- Vergleich der Hashwerte: Unterschiedlich -> Inhalt hat sich geaendert -> Datei wird neu importiert und aktualisiert
- Dadurch werden echte Inhaltsaenderungen erkannt, nicht nur z. B. ein geaendertes Aenderungsdatum

Was passiert bei Aenderungen konkret:
- Geaenderte Dateien werden neu indexiert, damit Such- und Chatfunktionen den aktuellen Stand nutzen
- Alte Versionen werden ersetzt oder intern aktualisiert, je nach Systemlogik
- Zugehoerige Metadaten wie `source_ids` bleiben konsistent oder werden aktualisiert

Weitere Faelle:
- Neue Datei: wird erkannt, importiert und einer Gruppe zugeordnet
- Geloeschte Datei: wird auch im System entfernt
- Defekte Datei: wird erkannt und gemeldet, kein Import

Zusaetzliche Logik im Hintergrund:
- FileSync merkt sich den zuletzt bekannten Hash pro Datei
- FileSync merkt sich, ob eine Datei bereits importiert wurde
- FileSync merkt sich die Zuordnung Ordner -> Dateigruppe
- Dadurch werden unnoetige Neuimporte vermieden und nur echte Aenderungen verarbeitet

Kurz gesagt:
- FileSync erkennt praezise Inhaltsaenderungen auf Byte-Ebene
- Aktualisiert wird nur das, was sich wirklich geaendert hat

---

### 8. Benutzeroberflaeche

Die App bietet mehrere Hauptbereiche:

- **Chat** -> Arbeiten mit KI
- **Dateien** -> Dokumente und Gruppen verwalten
- **Ressourcen** -> Modelle und Systeme konfigurieren
- **Einstellungen** -> App- und Benutzerkonfiguration
- **Hilfe** -> Unterstuetzung, Rollenhinweise und Admin-Informationen

---

### 9. Teams und Sichtbarkeit (konzeptionell)

- Inhalte koennen bestimmten Gruppen zugeordnet werden
- Sichtbarkeit von Dokumenten wird darueber gesteuert
- globale Inhalte sind fuer alle sichtbar

Zusaetzlich:
- Standardkontext kann fuer Suchen genutzt werden

---

### 10. Speicherung und Betrieb

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
- robuste Dokumentverarbeitung, auch fuer Office-Dateien

---

## Kurz gesagt

Kaidoku ist eine lokale Wissensplattform mit KI-Unterstuetzung:

- Dokumente hochladen oder automatisch synchronisieren
- Inhalte durchsuchen
- Fragen stellen
- fundierte Antworten aus eigenen Daten erhalten

-> Ziel: internes Wissen effizient nutzbar machen
