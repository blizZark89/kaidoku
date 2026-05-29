# Anleitung: Allgemeiner Überblick

## Was ist Kaidoku?

Kaidoku ist eine lokal betreibbare RAG-Anwendung (Retrieval-Augmented Generation).
Sie kombiniert:

- Chat mit KI-Modellen
- Dokumentensuche und -analyse
- Wissensaufbereitung aus eigenen Dateien
- Verwaltung von Inhalten und Datenquellen

Die Anwendung läuft lokal und kann ohne Cloud-Abhängigkeit betrieben werden.

---

## Zentrale Funktionen

### 1. Chat mit Dokumentbezug

- Nutzer können normale Chats mit KI führen
- Antworten können auf eigenen Dokumenten basieren
- Mehrere Reasoning-Ansätze stehen zur Verfügung, z. B. einfache QA oder Agentenlogik

#### 1.1 Dateisammlung

<table>
  <tr>
    <td valign="top" width="42%">
      <img src="images/1.1 Dateisammlung.PNG" alt="1.1 Dateisammlung" />
    </td>
    <td valign="top">

- **"Alle durchsuchen"**
  - durchsucht automatisch **alle verfügbaren Dokumente** im aktuellen Suchbereich
  - keine manuelle Auswahl von Dateien oder Gruppen nötig

- **"In Dateien suchen"**
  - durchsucht **nur die explizit ausgewählten einzelnen Dokumente**
  - geeignet für gezielte Abfragen in bestimmten Dateien

- **"In Dateigruppen suchen"**
  - durchsucht **alle Dokumente innerhalb der ausgewählten Gruppen**
  - sinnvoll für strukturierte, thematische Suchen

- **Teamfilter ("Teams")**
  - "Alle Teams" -> Suche über **alle für dich sichtbaren Inhalte**
  - einzelnes Team -> Suche **nur innerhalb dieses Teams**

    </td>
  </tr>
</table>

Typischer Ablauf:
1. Chat starten
2. Dokumente oder Gruppen auswählen
3. Frage stellen
4. System sucht relevante Inhalte
5. KI generiert eine Antwort auf Basis dieser Inhalte

---

### 2. Textsprache

<table>
  <tr>
    <td valign="top" width="42%">
      <img src="images/2. Textsprache.PNG" alt="2. Textsprache" />
    </td>
    <td valign="top">

- **Sprache**
  - Über das Dropdown **Sprache** kann die Ausgabesprache verändert werden
  - Geschrieben werden kann in jeder Sprache
  - Nach der Eingabe wird die Antwort in der ausgewählten Sprache ausgegeben

    </td>
  </tr>
</table>

---

### 3. Benutzer

Sichtbar für: Admin + Key User (Key User sieht nur eingeschränkte Ansicht)

Dieser Tab hat drei Untertabs:

**3.1 Benutzerliste**

<table>
  <tr>
    <td valign="top" width="42%">
      <img src="images/3.1 Benutzerliste.PNG" alt="3.1 Benutzerliste" />
    </td>
    <td valign="top">

- Tabelle mit Spalten: id, username, role, team, standardteam, can_read, can_upload
  - Sortierbar nach jeder Spalte (Dropdown "Sortieren nach" + aufsteigend/absteigend)
- Beim Klick auf einen Benutzer öffnet sich der Bearbeitungsbereich:
  - Benutzername — editierbar (3-32 Zeichen, nur Buchstaben/Zahlen/Unterstriche)
  - Passwort ändern + Passwort bestätigen (beide Passwort-Felder, nur ausfüllen wenn geändert werden soll)
  - Rolle — Dropdown, je nach Berechtigung des eingeloggten Users:
    - Wenn du Admin bist: du siehst alle 3 Rollen -> admin, key_user, user
    - Wenn du Key User bist: du siehst nur user
    - Ein normaler User sieht nur sich selbst und kann das Standardteam ändern
  - Teams — Mehrfachauswahl (Dropdown)
    - Admin sieht ALLE Teams
    - Key User sieht nur die Teams, die er selbst managt (seine eigenen Teams ohne globale Teams)
  - Standardteam — Dropdown (einfach)
    - Admin: alle Teams wählbar
    - Key User: eigene Teams + globale Teams
  - Leserechte (Checkbox) — für Rolle "user" manuell setzbar; Admin/Key User haben automatisch true
  - Upload-Rechte (Checkbox) — für Rolle "user" manuell setzbar; Admin/Key User haben automatisch true
  - Buttons: Speichern | Löschen (mit Bestätigungsdialog "Löschen bestätigen" / "Abbrechen") | Schließen

    </td>
  </tr>
</table>

Rollen-Detail:

| Rolle | Berechtigungen |
|---|---|
| admin | Vollzugriff auf alle Ressourcen-Tabs, kann alle Rollen vergeben, sieht alle Benutzer, kein Team-Zwang |
| key_user | Sieht nur den Benutzer-Tab, darf nur user-Rolle anlegen/bearbeiten (innerhalb seiner Teams), kann keine Admins/Key User managen. Automatisch Lese- und Upload-Rechte. |
| user | Basis-Rolle, sieht keine Ressourcen-Tabs. Lese-/Upload-Rechte sind einzeln konfigurierbar. Default: Lesen=ja, Upload=nein. |

Einschränkungen beim Bearbeiten:
- Ein User kann sich nicht selbst löschen
- Ein User (nicht Admin) darf für sich selbst nur das Standardteam ändern
- Ein Key User darf nur User in seinen eigenen Teams bearbeiten/löschen
- Admin darf keine Team-Zuordnung haben (wird zurückgewiesen)
- Key User und User müssen mindestens einem Team zugeordnet sein

**3.2 Benutzer anlegen**

- Benutzername (Textfeld)
- Passwort + Passwort bestätigen (beide versteckt)
- Rolle — Dropdown (angepasst an Berechtigung des Erstellers)
  - Admin: user, key_user, admin
  - Key User: nur user
- Teams — Mehrfachauswahl
- Standardteam — Dropdown
- Leserechte (Checkbox, default: true)
- Upload-Rechte (Checkbox, default: false)
- Regeln-Übersicht (zwei Markdown-Blöcke):
  - Benutzername-Regeln: 3-32 Zeichen, keine Groß-/Kleinschreibung, nur Buchstaben/Zahlen/Unterstriche
  - Passwort-Regeln: mind. 8 Zeichen, 1 Großbuchstabe, 1 Kleinbuchstabe, 1 Ziffer, 1 Sonderzeichen
- "Benutzer anlegen" Button

**3.3 Teams**

<table>
  <tr>
    <td valign="top" width="42%">
      <img src="images/3.3 Teams.PNG" alt="3.3 Teams" />
    </td>
    <td valign="top">

Es gibt zwei Ebenen, auf denen Teams zugeordnet werden können:

**(A) Dateiebene**

- Jede hochgeladene Datei kann einem oder mehreren Teams zugeordnet werden.
- Diese Zuordnung wird beim Upload oder in der Dateiverwaltung gesetzt.
- Wird bei der Suche nach einzelnen Dateien berücksichtigt.

**(B) Gruppenebene**

- Jede Dateigruppe kann einem oder mehreren Teams zugeordnet werden.
- Diese Zuordnung wird in der Dateiverwaltung unter "Dateisammlung" gesetzt.
- Wird bei der Suche nach Dateigruppen berücksichtigt.

Wichtig: Die beiden Ebenen sind unabhängig voneinander. Eine Dateigruppe kann Team A zugeordnet sein, während die enthaltenen Dateien selbst keinem Team zugeordnet sind (oder einem anderen).

Sichtbarkeit – Wer sieht was?

Die Sichtbarkeit wird bei jedem Zugriff berechnet. Es gibt folgende Regeln:

- **Admins** -> Sehen alle Dateien und Gruppen, unabhängig von Team-Zuordnung.
- **Globale Teams** -> Dateien/Gruppen, die einem als "global sichtbar" markierten Team zugeordnet sind, werden für alle Nutzer angezeigt.
- **Ohne Team-Zuordnung** -> Dateien/Gruppen ohne Team-Zuordnung sind nur für den Nutzer sichtbar, der sie hochgeladen/erstellt hat.
- **Mit Team-Zuordnung** -> Dateien/Gruppen mit Team-Zuordnung sind nur für Mitglieder dieser Teams sichtbar.

Team-Filter auf der Chat-Seite

Das "Team"-Dropdown auf der Chat-Seite dient dem Filtern der Suchergebnisse.

- "Alle Teams" (kein Filter) -> Admin sieht alles, normaler Nutzer nur Inhalte aus eigenen Teams.
- Konkretes Team -> Es werden nur Dateien/Gruppen angezeigt, die diesem Team zugeordnet sind.

Wichtige Unterscheidung je nach Such-Modus:

- **"In Datei(en) suchen"** -> Der Filter wird auf Dateiebene angewendet. Nur Dateien des gewählten Teams erscheinen in der Dropdown-Liste.
- **"In Dateigruppe(n) suchen"** -> Der Filter wird auf Gruppenebene angewendet. Nur Gruppen des gewählten Teams erscheinen. Alle Dateien innerhalb dieser Gruppen stehen dann zur Verfügung, auch wenn die einzelnen Dateien keinem Team zugeordnet sind.

    </td>
  </tr>
</table>

---

### 4. Dokumentenverwaltung

<table>
  <tr>
    <td valign="top" width="42%">
      <img src="images/4. Dokumentenverwaltung.PNG" alt="4. Dokumentenverwaltung" />
    </td>
    <td valign="top">

**4.1 Dateien hochladen**
- einzelne oder mehrere Dateien gleichzeitig hochladen
- unterstützte Formate:
  - PDF, DOCX, PPTX
  - Excel, CSV
  - Bilder
  - Markdown, Text, HTML
  - ZIP-Dateien

**4.2 Indexierung**
- Dokumente werden automatisch analysiert
- Inhalte werden in Suchindizes überführt
- Status wird in der Datei-Liste angezeigt -> z. B. "fertig" oder "in Bearbeitung"
- Bereits indexierte Dateien stehen sofort im Chat zur Verfügung

**4.3 Quellen statt Dateien**
- jede indexierte Datei erscheint als **Quelle** in der Uebersicht
- selbst wenn die Originaldatei gelöscht wird, bleibt die Quelle erhalten
- erst das **Loeschen der Quelle** entfernt den Inhalt endgültig aus dem System

**4.4 Team-Zuordnung beim Upload**
- Dateien können direkt einem oder mehreren Teams zugewiesen werden
- ohne Zuordnung bleibt die Datei nur für den Ersteller sichtbar
- spätere Änderungen sind in der Dateiverwaltung möglich

    </td>
  </tr>
</table>

---

### 5. Dateigruppen

- Dokumente können in Gruppen organisiert werden
- Gruppen erleichtern die strukturierte Suche im Chat
- Gruppen können automatisch oder manuell gepflegt werden
- jede Gruppe kann eigenen Teams zugeordnet werden -> unabhängig von den Dateien darin

Im Chat kann gezielt gesucht werden:
- in einzelnen Dateien
- in Gruppen
- oder global

---

### 6. Intelligente Suche (RAG)

- Inhalte werden in Vektor-Datenbanken gespeichert
- Relevante Textstellen werden automatisch gefunden
- Kombination aus:
  - Retrieval (Suche)
  - Generierung (LLM-Antwort)

Zusätzlich möglich:
- Reranking für bessere Trefferreihenfolge
- verschiedene Embedding-Modelle

---

### 7. Reasoning und KI-Pipelines

Mehrere Verarbeitungsstrategien sind integriert:

- klassische Frage-Antwort
- zerlegte Fragen (Decomposition)
- agenten-basierte Ansätze, z. B. ReAct oder ReWOO

Dadurch können:
- komplexe Fragen beantwortet werden
- mehrstufige Probleme gelöst werden

---

### 8. Ressourcenverwaltung

Die App kann verschiedene KI-Komponenten verwalten:

- LLMs, z. B. OpenAI, Ollama, Gemini, Claude
- Embedding-Modelle
- Reranking-Modelle
- MCP-Server
- Index-Sammlungen

Das erlaubt flexible Anpassung an:
- lokale Modelle
- externe APIs
- unterschiedliche Anwendungsfälle

---

### 9. FileSync (automatischer Import)

<table>
  <tr>
    <td valign="top" width="42%">
      <img src="images/9. FileSync.PNG" alt="9. FileSync" />
    </td>
    <td valign="top">

- Überwacht definierte Ordner und sorgt dafür, dass alle Dateien automatisch aktuell im System sind

Wie Dateiunterschiede erkannt werden:
- Jede Datei wird beim Einlesen analysiert und mit einem Hashwert versehen
- Bei jedem weiteren Scan wird dieser Hash erneut berechnet
- Vergleich der Hashwerte: Gleich -> Datei ist unverändert -> keine Aktion
- Vergleich der Hashwerte: Unterschiedlich -> Inhalt hat sich geändert -> Datei wird neu importiert und aktualisiert
- Dadurch werden echte Inhaltsänderungen erkannt, nicht nur z. B. ein geändertes Änderungsdatum

Was passiert bei Änderungen konkret:
- Geänderte Dateien werden neu indexiert, damit Such- und Chatfunktionen den aktuellen Stand nutzen
- Alte Versionen werden ersetzt oder intern aktualisiert, je nach Systemlogik
- Zugehörige Metadaten wie `source_ids` bleiben konsistent oder werden aktualisiert

Weitere Fälle:
- Neue Datei: wird erkannt, importiert und einer Gruppe zugeordnet
- Gelöschte Datei: wird auch im System entfernt
- Defekte Datei: wird erkannt und gemeldet, kein Import

Zusätzliche Logik im Hintergrund:
- FileSync merkt sich den zuletzt bekannten Hash pro Datei
- FileSync merkt sich, ob eine Datei bereits importiert wurde
- FileSync merkt sich die Zuordnung Ordner -> Dateigruppe
- Dadurch werden unnötige Neuimporte vermieden und nur echte Änderungen verarbeitet

Kurz gesagt:
- FileSync erkennt präzise Inhaltsänderungen auf Byte-Ebene
- Aktualisiert wird nur das, was sich wirklich geändert hat

    </td>
  </tr>
</table>

---

### 10. Benutzeroberfläche

Die App bietet mehrere Hauptbereiche:

- **Chat** -> Arbeiten mit KI
- **Dateien** -> Dokumente und Gruppen verwalten
- **Ressourcen** -> Modelle und Systeme konfigurieren
- **Einstellungen** -> App- und Benutzerkonfiguration
- **Hilfe** -> Unterstützung, Rollenhinweise und Admin-Informationen

---

### 11. Speicherung und Betrieb

- lokale Datenhaltung (SQLite)
- Vektor-Datenbanken (Chroma)
- Dokumentenspeicher (LanceDB)

Alle Daten liegen im lokalen App-Verzeichnis:
- keine zwingende externe Abhängigkeit

---

## Technische Highlights

- vollständig lokal betreibbar
- Docker-fähig
- deutsche Oberfläche
- modular erweiterbar
- unterstützt viele KI-Anbieter
- robuste Dokumentverarbeitung, auch für Office-Dateien

---

## Kurz gesagt

Kaidoku ist eine lokale Wissensplattform mit KI-Unterstützung:

- Dokumente hochladen oder automatisch synchronisieren
- Inhalte durchsuchen
- Fragen stellen
- fundierte Antworten aus eigenen Daten erhalten

-> Ziel: internes Wissen effizient nutzbar machen
