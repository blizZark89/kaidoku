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

## Schnellstart – Erste Schritte

1. **Anmelden** — mit deinem Benutzernamen und Passwort
2. **Team wählen** — oben rechts im Chat dein Standardteam einstellen
3. **Datei hochladen** — im Tab "Dateien" deine erste PDF/Datei hochladen
4. **Frage stellen** — im Tab "Chat" eine Frage zur Datei eingeben
5. **Antwort lesen** — die KI antwortet mit Quellenangaben und Seitenzahlen

Tipp: Nach dem Upload kurz warten bis die Datei als "fertig" markiert ist — dann ist sie durchsuchbar.

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

**Wann nutze ich welchen Modus?**

| Modus | Geeignet für |
|-------|-------------|
| Alle durchsuchen | Schnelle Suche, ich weiß nicht wo die Info steht |
| In Dateien suchen | Ich kenne die genaue Datei (z.B. Handbuch.pdf) |
| In Dateigruppen suchen | Thematische Suche (z.B. alle Q3-Berichte) |

Typischer Ablauf:
1. Chat starten
2. Dokumente oder Gruppen auswählen
3. Frage stellen
4. System sucht relevante Inhalte
5. KI generiert eine Antwort auf Basis dieser Inhalte

---

### 1.2 Mindmap

Nach jeder Antwort erscheint ein **Mindmap**-Button. Ein Klick darauf erstellt eine visuelle Wissenslandkarte aus der Antwort:

- Zeigt die wichtigsten Konzepte und Zusammenhänge als Baumdiagramm
- Hilft komplexe Themen schnell zu überblicken
- Ideal für Präsentationen oder zum Teilen mit Kollegen
- Jeder Knoten kann ein- und ausgeklappt werden

---

### 1.3 Tipps für gute Fragen

Schlecht: "Was steht in dem Dokument?"
Gut: "Fasse die Sicherheitsvorschriften aus Kapitel 3 zusammen."

Schlecht: "Erklär mir das."
Gut: "Was sind die drei wichtigsten Änderungen in Version 2.0 gegenüber Version 1.0?"

**Goldene Regeln:**
- Sei so konkret wie möglich
- Nenne das Dokument/die Dateigruppe beim Namen
- Stelle EINE Frage auf einmal
- "Fasse zusammen", "Vergleiche", "Liste auf" sind gute Einstiege
- Je präziser die Frage, desto besser die Antwort

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

- Tabelle mit Spalten: username, role, team, standardteam, can_read, can_upload, storage_mb, id
  - Sortierbar nach jeder Spalte (Dropdown "Sortieren nach" + aufsteigend/absteigend)
- Beim Klick auf einen Benutzer öffnet sich der Bearbeitungsbereich:
  - Benutzername — editierbar (3-32 Zeichen, nur Buchstaben/Zahlen/Unterstriche)
  - Passwort ändern + Passwort bestätigen (nur ausfüllen wenn geändert werden soll)
  - Rolle — Dropdown, je nach Berechtigung des eingeloggten Users:
    - Admin: sieht alle 3 Rollen -> admin, key_user, user
    - Key User: sieht nur user
    - User: sieht nur sich selbst und kann das Standardteam ändern
  - Teams — Mehrfachauswahl (Dropdown)
    - Admin sieht ALLE Teams
    - Key User sieht nur die Teams, die er selbst erstellt hat
  - Standardteam — Dropdown (einfach)
    - Admin: alle Teams wählbar
    - Key User: eigene Teams + globale Teams
  - Leserechte (Checkbox)
  - Upload-Rechte (Checkbox)
  - Buttons: Speichern | Löschen (mit Bestätigungsdialog) | Schließen

    </td>
  </tr>
</table>

Rollen-Detail:

| Rolle | Berechtigungen |
|---|---|
| admin | Vollzugriff auf alle Ressourcen-Tabs, kann alle Rollen vergeben, sieht alle Benutzer |
| key_user | Erstellt und verwaltet eigene Teams und Benutzer (nur user), sieht nur eigene Teams |
| user | Basis-Rolle, sieht keine Ressourcen-Tabs, Lese-/Upload-Rechte konfigurierbar |

Einschränkungen beim Bearbeiten:
- Ein User kann sich nicht selbst löschen
- Ein User (nicht Admin) darf für sich selbst nur das Standardteam ändern
- Ein Key User darf nur User in seinen eigenen Teams bearbeiten/löschen
- Admin darf keine Team-Zuordnung haben
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
- Regeln-Übersicht:
  - Benutzername: 3-32 Zeichen, keine Groß-/Kleinschreibung, nur Buchstaben/Zahlen/Unterstriche
  - Passwort: mind. 8 Zeichen, 1 Großbuchstabe, 1 Kleinbuchstabe, 1 Ziffer, 1 Sonderzeichen
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
- Jede hochgeladene Datei kann einem oder mehreren Teams zugeordnet werden

**(B) Gruppenebene**
- Jede Dateigruppe kann einem oder mehreren Teams zugeordnet werden

Wichtig: Die beiden Ebenen sind unabhängig voneinander.

Sichtbarkeit – Wer sieht was?

| Regel | Sichtbar für |
|-------|-------------|
| **Admins** | Alle Dateien und Gruppen |
| **Globale Teams** | Alle Nutzer (systemweit sichtbar) |
| **Ohne Team-Zuordnung** | Nur der Ersteller |
| **Mit Team-Zuordnung** | Nur Mitglieder dieser Teams |

Team-Filter auf der Chat-Seite:
- "Alle Teams" -> Admin sieht alles, Nutzer nur eigene Teams
- Konkretes Team -> Nur Dateien/Gruppen des gewählten Teams

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
- unterstützte Formate: PDF, DOCX, PPTX, Excel, CSV, Bilder, Markdown, Text, HTML, ZIP

**4.2 Indexierung**
- Dokumente werden automatisch analysiert
- Status wird in der Datei-Liste angezeigt (z. B. "fertig" oder "in Bearbeitung")

**4.3 Quellen vs. Dateien**

Wichtiger Unterschied:
- **Datei** = die Originaldatei die du hochgeladen hast (z.B. Handbuch.pdf)
- **Quelle** = der indexierte Inhalt, der im Chat durchsucht wird

Was bedeutet das praktisch?
- Löschst du die Datei, bleibt die Quelle erhalten → Inhalte sind weiterhin suchbar
- Löschst du die Quelle, ist der Inhalt endgültig weg
- Zum vollständigen Entfernen: erst Quelle löschen, dann Datei löschen

**4.4 Team-Zuordnung beim Upload**
- Dateien können direkt einem oder mehreren Teams zugewiesen werden
- ohne Zuordnung bleibt die Datei nur für den Ersteller sichtbar

    </td>
  </tr>
</table>

---

### 5. Dateigruppen

- Dokumente können in Gruppen organisiert werden
- Gruppen erleichtern die strukturierte Suche im Chat
- Jede Gruppe kann eigenen Teams zugeordnet werden (unabhängig von den enthaltenen Dateien)

---

### 6. Team-Konzept

**Was ist ein Team?**
Ein Team ist eine Gruppe von Benutzern, die gemeinsame Dokumente sehen und bearbeiten. Teams steuern, wer welche Dateien und Dateigruppen sehen kann.

**Was bedeutet "globales Team"?**
Ein globales Team ist für ALLE Benutzer sichtbar — unabhängig von ihrer Team-Zugehörigkeit. Nur Admins können Teams als global markieren. Ideal für unternehmensweite Dokumente wie Organigramme oder allgemeine Richtlinien.

**Standardteam vs. Team-Filter**
- **Standardteam** (in den Einstellungen): Wird automatisch vorausgewählt wenn du einen neuen Benutzer anlegst oder eine Datei hochlädst. Ist dein "Heimat-Team".
- **Team-Filter** (im Chat): Schränkt die Suche temporär auf ein bestimmtes Team ein. Ändert nichts an deinen Einstellungen.

**Sichtbarkeits-Matrix**

|  | Admin | Key-User (eigenes Team) | Key-User (fremdes Team) | User (Mitglied) | User (nicht Mitglied) |
|--|-------|------------------------|------------------------|----------------|----------------------|
| Dateien ohne Team | ✅ | ❌ | ❌ | ❌ | ❌ |
| Dateien im Team | ✅ | ✅ | ❌ | ✅ | ❌ |
| Dateien in globalem Team | ✅ | ✅ | ✅ | ✅ | ✅ |
| Teams in Liste sehen | Alle | Nur eigene | Keine | Nur eigene | Keine |

---

### 7. Speicherverbrauch

In der Benutzerliste (nur Admin sichtbar) zeigt die Spalte **MB** wie viel Speicherplatz jeder Benutzer durch seine hochgeladenen Dateien belegt.

- Die Anzeige ist ein Richtwert
- Gelöschte Quellen werden nicht mehr mitgezählt
- Bei vollem Speicher: Alte Quellen löschen oder Admin kontaktieren

---

### 8. Intelligente Suche (RAG)

- Inhalte werden in Vektor-Datenbanken gespeichert
- Relevante Textstellen werden automatisch gefunden
- Kombination aus: Retrieval (Suche) + Generierung (LLM-Antwort)
- Reranking für bessere Trefferreihenfolge möglich

---

### 9. Reasoning und KI-Pipelines

Mehrere Verarbeitungsstrategien sind integriert:
- klassische Frage-Antwort
- zerlegte Fragen (Decomposition)
- agenten-basierte Ansätze (ReAct, ReWOO)

---

### 10. Ressourcenverwaltung

Die App kann verschiedene KI-Komponenten verwalten:
- LLMs (OpenAI, Ollama, Gemini, Claude)
- Embedding-Modelle
- Reranking-Modelle
- MCP-Server
- Index-Sammlungen

---

### 11. FileSync (automatischer Import)

<table>
  <tr>
    <td valign="top" width="42%">
      <img src="images/9. FileSync.PNG" alt="9. FileSync" />
    </td>
    <td valign="top">

- Überwacht definierte Ordner und sorgt dafür, dass alle Dateien automatisch aktuell im System sind

So funktionierts:
- Jede Datei bekommt einen Hashwert
- Bei jedem Scan wird der Hash neu berechnet
- Gleicher Hash = Datei unverändert → keine Aktion
- Anderer Hash = Inhalt geändert → Datei wird neu importiert

Was passiert konkret:
- Neue Datei → wird erkannt, importiert und einer Gruppe zugeordnet
- Geänderte Datei → wird neu indexiert
- Gelöschte Datei → wird aus dem System entfernt
- Defekte Datei → wird erkannt und gemeldet

    </td>
  </tr>
</table>

---

### 12. Benutzeroberfläche

Die App bietet mehrere Hauptbereiche:

- **Chat** → Arbeiten mit KI
- **Dateien** → Dokumente und Gruppen verwalten
- **Ressourcen** → Modelle und Systeme konfigurieren
- **Einstellungen** → App- und Benutzerkonfiguration
- **Hilfe** → Anleitungen, Rollenhinweise und Support

---

### 13. Speicherung und Betrieb

- lokale Datenhaltung (SQLite)
- Vektor-Datenbanken (Chroma)
- Dokumentenspeicher (LanceDB)

Keine externe Cloud-Abhängigkeit.

---

## Häufige Fehlermeldungen

| Meldung | Bedeutung | Lösung |
|---------|-----------|--------|
| **Keine Treffer gefunden** | Keine relevanten Textstellen in den Dateien | Andere Suchbegriffe probieren, Suchmodus prüfen, warten bis Datei indiziert ist |
| **Datei zu groß (max. X MB)** | Die Datei überschreitet das Upload-Limit | Datei verkleinern oder Admin bitten Limit zu erhöhen |
| **Maximale Anzahl an Dateien erreicht** | Das Datei-Kontingent ist voll | Nicht benötigte Dateien/Quellen löschen |
| **Ungültige URL** | Die eingegebene URL ist falsch formatiert | URL muss mit http:// oder https:// beginnen |
| **Denke nach …** (bleibt lange) | Die KI verarbeitet deine Anfrage | Normal bei großen Dokumenten. Wenn >30 Sekunden: F5 drücken |
| **Keine Antwort gefunden** | Die KI konnte keine sinnvolle Antwort generieren | Frage präziser formulieren |
| **Du darfst diesen Benutzer nicht anlegen** | Fehlende Berechtigung oder Team-Konflikt | Prüfen ob du Key-User bist und mind. ein Team hast |

---

## Häufige Fragen (FAQ)

**F: Warum sehe ich bestimmte Dateien nicht?**
A: Prüfe: 1) Bist du im richtigen Team? 2) Ist die Datei einem Team zugeordnet? 3) Bist du Mitglied dieses Teams? Dateien ohne Team-Zuordnung sind nur für den Ersteller sichtbar.

**F: Warum dauert die erste Suche so lange?**
A: Beim ersten Zugriff wird das KI-Modell geladen. Die zweite Suche ist deutlich schneller.

**F: Kann ich eine Datei löschen ohne die Suchtreffer zu verlieren?**
A: Ja! Datei und Quelle sind getrennt. Lösche nur die Datei — die Quelle bleibt erhalten. Lösche die Quelle nur, wenn du den Inhalt endgültig entfernen willst.

**F: Ich habe mein Passwort vergessen — was nun?**
A: Dein Admin kann ein neues Passwort für dich setzen (Benutzereinstellungen).

**F: Wie lade ich mehrere Dateien auf einmal hoch?**
A: Im Datei-Upload-Dialog mehrere Dateien auswählen (Strg+Klick oder Shift+Klick) und gemeinsam hochladen.

**F: Änderungen werden nicht angezeigt — was tun?**
A: Browser-Cache leeren mit Strg+F5. Nach Docker-Updates kann der alte Cache stören.

---

## Bekannte Probleme & Workarounds

| Problem | Lösung |
|---------|--------|
| Nach einem Update funktioniert etwas nicht | Strg+F5 drücken (Browser-Cache leeren) |
| Bilder im Hilfe-Reiter laden nicht | Strg+F5 drücken |
| Klick auf Bild vergrößert es nicht | Seite neu laden (F5), dann Strg+F5 |
| Chat bleibt bei "Denke nach …" hängen | Seite neu laden (F5) und Frage erneut stellen |

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

Ziel: internes Wissen effizient nutzbar machen.