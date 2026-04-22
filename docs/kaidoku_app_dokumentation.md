# Kaidoku App Dokumentation

## Zweck dieses Dokuments

Diese Dokumentation beschreibt den Ist-Zustand der lokalen Kaidoku-Codebasis in
`C:\Users\Flo\kaidoku` auf Basis von Version `v0.5`.

Der Fokus liegt auf dem tatsaechlich vorhandenen Verhalten der Anwendung:

- Start und Boot-Sequenz
- zentrale Konfiguration
- sichtbare Oberflaechenbereiche
- Rollen, Rechte und Teams
- Dokument- und Gruppensichtbarkeit
- FileSync in `v0.5`
- Persistenz und Betrieb

Diese Fassung ersetzt aeltere Beschreibungen, die noch von `v0.3` oder `v0.4`
ausgingen und zentrale Neuerungen aus `v0.5` noch nicht abbildeten.

## Kurzfassung

Kaidoku ist eine lokal betreibbare, deutsch konfigurierte RAG-Anwendung auf
Basis von Kotaemon und KTEM mit Gradio-Frontend.

Der aktuelle Stand `v0.5` kombiniert:

- Login-basierte Benutzerverwaltung
- Chat mit mehreren Reasoning-Pipelines
- Dokumentenindizierung fuer klassische Dateisammlungen und GraphRAG-Sammlungen
- Ressourcenverwaltung fuer LLMs, Embeddings, Rerankings und MCP-Server
- Rollenmodell mit `admin`, `key_user` und `user`
- teambezogene Zugriffssteuerung fuer Benutzer, Dokumente und Dateigruppen
- globale Teams und Standardteams
- lokalen FileSync fuer serverseitige Ordner

## Versionsbezug

Der hier dokumentierte Stand entspricht dem Git-Tag `v0.5`.

Der zugehoerige Commit ist:

- `ee4a5f9` - `Bump app version to 0.5`

Praegende Aenderungen zwischen `v0.4` und `v0.5` sind laut lokaler Git-Historie:

- lokaler Ordner-FileSync wurde eingefuehrt
- Docker-Konfiguration und README wurden dafuer angepasst
- FileSync-UI wurde auf Deutsch umgestellt
- Chat-Selektor und Gruppenverhalten fuer FileSync wurden korrigiert
- Team-Sichtbarkeit und Default-Verhalten in der Dokumentauswahl wurden angepasst
- `delete_file` wurde in der Index-Pipeline fuer Loeschfaelle nutzbar gemacht
- FileSync prueft Indexierungsergebnis und Inhalt vor dem Veroeffentlichen
- DOCX- und PPTX-Reader wurden fuer stabilere lokale Verarbeitung ueberschrieben

## Repository-Struktur

Wichtige Einstiegspunkte im Wurzelverzeichnis:

- `app.py`: Standard-Startpunkt der Anwendung
- `flowsettings.py`: zentrale Laufzeitkonfiguration
- `README.md`: Installations- und Docker-Hinweise
- `Dockerfile`: Container-Build
- `sso_app.py` und `sso_app_demo.py`: alternative SSO-Einstiege
- `libs/ktem/ktem/main.py`: Hauptaufbau der Gradio-App
- `libs/ktem/ktem/app.py`: Basis-App, Event-System, Settings-State, Index-Initialisierung
- `libs/ktem/ktem/authz.py`: Rollen-, Team- und Berechtigungslogik
- `libs/ktem/ktem/pages/`: UI-Seiten fuer Chat, Ressourcen, Einstellungen, Hilfe, Login
- `libs/ktem/ktem/pages/help.py`: Aufbau des Hilfe-Reiters, Rollenblock und
  admin-sichtbarer Versionsverlauf
- `libs/ktem/ktem/index/file/ui.py`: Datei- und Gruppenverwaltung inkl. Teamzuordnung
- `libs/ktem/ktem/filesync.py`: lokaler FileSync-Dienst
- `libs/ktem/ktem/db/`: Datenmodelle und Schema-Erweiterungen

## Start und Boot-Sequenz

Der normale Startpfad ist `app.py`.

Beim Start passiert aktuell:

1. `KH_APP_DATA_DIR` und `GRADIO_TEMP_DIR` werden vorbereitet.
2. Falls `GRADIO_TEMP_DIR` nicht gesetzt ist, wird `ktem_app_data/gradio_tmp`
   verwendet.
3. `ktem.main.App` wird instanziiert.
4. `app.make()` baut die komplette Gradio-Oberflaeche.
5. `demo.queue().launch(...)` startet die Anwendung im Browser.

Waehrend des App-Aufbaus werden ausserdem:

- alle konfigurierten Reasoning-Pipelines registriert
- alle Indizes initialisiert
- der globale Settings-State aufgebaut
- der User-State vorbereitet
- der FileSync-Worker gestartet

## Zentrale Konfiguration in `flowsettings.py`

Der lokale Stand setzt unter anderem:

- `KH_APP_VERSION = "0.5"`
- `KH_APP_NAME = "kaidoku"`
- `KH_LOCALE = "de"`
- `KH_ENABLE_FIRST_SETUP = True`
- `KH_FEATURE_USER_MANAGEMENT = True`
- `KH_SSO_ENABLED = False`
- `KH_ENABLE_ALEMBIC = False`
- SQLite als Anwendungsdatenbank
- LanceDB als Docstore
- Chroma als Vectorstore

Wichtige App-Datenverzeichnisse unter `ktem_app_data`:

- `user_data`
- `markdown_cache_dir`
- `chunks_cache_dir`
- `zip_cache_dir`
- `zip_cache_dir_in`
- `huggingface`
- `filesync`

Aktuell konfigurierte bzw. vorbereitete Modellfamilien:

- OpenAI
- Azure OpenAI
- Ollama
- Google Gemini
- Claude
- Groq
- Cohere
- Mistral
- Voyage AI

Wichtige Default-Beispiele:

- Chat-Modell OpenAI: `gpt-4o-mini`
- Embeddings OpenAI: `text-embedding-3-large`
- Gemini: `gemini-1.5-flash`
- lokales Ollama-Modell ueber `LOCAL_MODEL`, falls gesetzt

Konfigurierte Reasoning-Pipelines:

- `FullQAPipeline`
- `FullDecomposeQAPipeline`
- `ReactAgentPipeline`
- `RewooAgentPipeline`

## Hauptnavigation und Sichtbarkeit

Die Haupttabs werden in `libs/ktem/ktem/main.py` aufgebaut.

Moegliche Hauptbereiche:

- `Willkommen`
- `Chat`
- `Dateien`
- `Ressourcen`
- `Einstellungen`
- `Hilfe`
- optional `First Setup`

Sichtbarkeitslogik bei aktivierter Benutzerverwaltung:

- ohne Login ist nur `Willkommen` sichtbar
- nach erfolgreichem Login wird auf `Chat` gewechselt
- `Ressourcen` ist nur fuer `admin` und `key_user` sichtbar
- `Einstellungen` und `Hilfe` sind nach Login sichtbar
- Datei-Tabs werden nach Login sichtbar
- GraphRAG-Sammlungen sind nur sichtbar, wenn
  `application.show_graphrag_collections` aktiv ist oder der Benutzer Admin ist

Wenn nur ein Index existiert, wird dieser direkt als eigener Tab gerendert.
Bei mehreren Indizes erscheint ein Obertab `Dateien` mit Untertabs je Sammlung.

## Hilfe-Reiter

Die Hilfeoberflaeche wird in `libs/ktem/ktem/pages/help.py` aufgebaut.

Aktuelle aufklappbare Bereiche:

- `Über Kaidoku`
- `Anleitung`
- `Rollen`
- optional `Eigenen Space erstellen` im Demo-Modus
- `Versionsverlauf`

Inhalt und Sichtbarkeit:

- `Anleitung` zeigt immer die allgemeine Dokumentation
- angemeldete `user` sehen dort zusaetzlich die User-Anleitung
- angemeldete `key_user` sehen dort zusaetzlich User- und Key-User-Anleitung
- angemeldete `admin` sehen dort die allgemeine Anleitung sowie User-, Key-User-
  und Admin-Anleitung
- `Rollen` zeigt gesammelt die drei Rollendokumente fuer `user`, `key_user` und
  `admin`
- `Versionsverlauf` ist nur fuer `admin` sichtbar
- der Versionsverlauf enthaelt keinen lokal gerenderten Changelog mehr, sondern
  verweist auf die GitHub-Releases unter
  `https://github.com/blizZark89/kaidoku/releases`

## Rollen- und Rechtemodell

Die zentrale Logik liegt in `libs/ktem/ktem/authz.py`.

Unterstuetzte Rollen:

- `admin`
- `key_user`
- `user`

Wichtige Rechtefunktionen:

- `has_read_access(actor)`
- `has_upload_access(actor)`
- `can_manage_user(session, actor, target)`
- `can_create_role(session, actor, role, team_id)`
- `allowed_user_ids_for_scope(session, actor)`
- `default_team_choices(session, actor)`
- `normalize_default_team_id(...)`

Grundregeln:

- `admin` hat Vollzugriff
- `key_user` hat immer Lese- und Upload-Rechte
- `user` hat Leserechte und optional Upload-Rechte
- nur `admin` darf alle Rollen anlegen oder aendern
- `key_user` darf nur `user` im eigenen verwaltbaren Teamkontext anlegen,
  aendern oder loeschen
- normale `user` koennen keine anderen Benutzer verwalten

### Admin

Ein `admin` darf und kann aktuell:

- alle Tabs und alle Ressourcenbereiche sehen
- LLMs, Embeddings, Rerankings, MCP-Server und Index-Sammlungen verwalten
- Benutzer aller Rollen anlegen, bearbeiten und loeschen
- Teams erstellen, loeschen und als global markieren
- Dokumente allen vorhandenen Teams zuordnen
- Dateigruppen teambezogen verwalten
- alle sichtbaren und administrativen Einstellungen veraendern
- FileSync konfigurieren und manuell ausfuehren
- GraphRAG-Sammlungen immer sehen

Besonderheiten:

- `admin` ist keiner festen Teammenge zugeordnet
- fuer `admin` sind `can_read` und `can_upload` effektiv immer `True`
- vorhandene Altinstallationen mit altem `admin`-Flag werden beim Zugriff
  automatisch auf das aktuelle RBAC-Modell abgeglichen

### Key User

Ein `key_user` ist ein fachlicher Team-Verwalter mit eingeschraenkten
Administrationsrechten.

Ein `key_user` darf und kann aktuell:

- `Chat`, `Dateien`, `Einstellungen`, `Hilfe` und `Ressourcen` sehen
- im Ressourcenbereich den Benutzer-Tab sehen
- `user` im eigenen verwaltbaren Teamkontext anlegen, bearbeiten und loeschen
- Teamzuordnungen fuer diese `user` innerhalb des eigenen Teamkontexts setzen
- Dokumente in den eigenen Teams hochladen und diesen Teams zuordnen
- sichtbare Dokumente und Dateigruppen im Teamkontext nutzen
- das eigene Standardteam pflegen
- das eigene Passwort aendern

Ein `key_user` darf aktuell nicht:

- `admin` oder weitere `key_user` anlegen
- Teams erstellen, loeschen oder global markieren
- LLM-, Embedding-, Reranking-, MCP- oder Index-Administration verwenden
- FileSync konfigurieren

Wichtig:

- ein `key_user` muss mindestens einem Team zugeordnet sein
- globale Teams zaehlen bei der Benutzerverwaltung nicht als verwaltbarer
  Teamkontext; verwaltet werden nur die eigenen nicht-globalen Teams

### User

Ein `user` ist auf die normale Anwendung beschraenkt.

Ein `user` darf und kann aktuell:

- sich anmelden und die Anwendung nutzen
- Chats fuehren
- sichtbare Dokumente und Dateigruppen im erlaubten Teamkontext durchsuchen
- das eigene Passwort aendern
- das eigene Standardteam sehen und im Chat indirekt als Default-Filter nutzen
- optional Dokumente hochladen, wenn `can_upload` fuer den Benutzer gesetzt ist

Ein `user` darf aktuell nicht:

- andere Benutzer verwalten
- Ressourcen-Administration nutzen
- Teams verwalten
- FileSync konfigurieren
- globale Systemeinstellungen aendern

Wichtig:

- ein `user` muss mindestens einem Team zugeordnet sein
- ohne Upload-Recht bleibt der Zugriff auf vorhandene Dokumente lesend

## Teams, globale Teams und Standardteam

Das Teammodell ist in `libs/ktem/ktem/db/base_models.py`,
`libs/ktem/ktem/db/models.py`, `libs/ktem/ktem/authz.py` und
`libs/ktem/ktem/pages/resources/user.py` umgesetzt.

Aktueller Stand in `v0.5`:

- Benutzer koennen mehreren Teams zugeordnet sein
- Teams koennen `global` sein
- Benutzer koennen ein `default_team_id` besitzen

### Teams

Allgemeine Regeln:

- nur `admin` darf Teams erstellen und loeschen
- nur `admin` darf den Global-Status eines Teams aendern
- ein Team darf nicht geloescht werden, solange es einem Benutzer zugeordnet ist
  oder als Standardteam verwendet wird

### Globale Teams

Globale Teams erweitern die Sichtbarkeit:

- Dokumente oder Gruppen mit globalem Team sind teamuebergreifend sichtbar
- Nicht-Admins koennen globale Teams als Standardteam verwenden
- globale Teams erscheinen in der Teamauswahl fuer passende Benutzer

### Standardteam

Das Standardteam ist neu relevant fuer `v0.5`:

- es wird pro Benutzer in `UserAccess.default_team_id` gespeichert
- es muss fuer die Rolle und Teammenge gueltig sein
- im Chat-Dateiselektor wird es als bevorzugter Teamfilter gesetzt, wenn moeglich
- normale Benutzer duerfen bei sich selbst nur das Standardteam aendern, nicht
  Rolle oder Teamrechte

## Benutzerverwaltung

Die Benutzerverwaltung sitzt in `libs/ktem/ktem/pages/resources/user.py`.

Die UI enthaelt:

- `Benutzerliste`
- `Benutzer anlegen`
- `Teams`

Aktuelle Validierungen:

- Benutzername: 3 bis 32 Zeichen, nur Buchstaben, Zahlen, Unterstriche
- Passwort: mindestens 8 Zeichen, Grossbuchstabe, Kleinbuchstabe, Ziffer,
  Sonderzeichen
- Passwoerter werden per SHA-256 gehasht gespeichert

Wichtige Regeln:

- Bootstrap-Admin aus `flowsettings.py` wird beim Start sichergestellt
- `admin` darf `user`, `key_user` und `admin` anlegen
- `key_user` darf nur `user` anlegen
- `admin` darf keinem Team fest zugeordnet sein
- `key_user` und `user` muessen mindestens einem Team zugeordnet sein
- fuer `admin` und `key_user` werden `can_read` und `can_upload` intern immer
  auf `True` normalisiert
- Benutzerlisten sind rollenspezifisch gefiltert:
  Admin sieht alle, Key User sieht relevante Team-Benutzer plus sich selbst,
  User sieht nur sich selbst

## Chat-Seite

Die Chat-Oberflaeche liegt in `libs/ktem/ktem/pages/chat/__init__.py`.

Sie kombiniert:

- Konversationsliste
- eigentlichen Chatbereich
- sitzungsbezogene Reasoning-Einstellungen
- Referenz- und Zusatzansichten

Der fachliche Ablauf:

1. Benutzer waehlt oder erstellt eine Unterhaltung.
2. Benutzer waehlt Dateien oder Dateigruppen.
3. Optional wirkt ein Teamfilter auf die Dateiauswahl.
4. Retrieval sucht passende Inhalte in den zulaessigen Quellen.
5. Eine Reasoning-Pipeline erzeugt die Antwort.
6. Unterhaltung und Antwort werden gespeichert.

Im aktuellen Stand sind unter anderem vorhanden:

- Folgefragen
- Reasoning-Auswahl
- Sprachwahl
- PDF-Viewer-Anbindung
- Mindmap- und Informationspanel
- lokalisierte Gesprächstitel
- robustere Reset-Logik fuer den Chat-Zustand

## Dateien, Upload und Sichtbarkeit

Die Datei- und Gruppenlogik sitzt hauptsaechlich in
`libs/ktem/ktem/index/file/ui.py`.

### Upload

Aktuelles Verhalten:

- Upload ist bei aktivierter Benutzerverwaltung nur mit `has_upload_access`
  erlaubt
- `admin` darf Dokumente allen Teams zuordnen
- Nicht-Admins duerfen Dokumente nur den eigenen Teams zuordnen
- beim Upload kann fuer Dokumente eine Teammenge gespeichert werden
- fuer einzelne Dokumente koennen die Teams spaeter bearbeitet werden

### Dokument-Sichtbarkeit

Die Sichtbarkeit orientiert sich in `v0.5` an:

- Rolle des Benutzers
- Teamzuordnung des Dokuments
- globalen Teams
- Legacy-Faellen ohne Teamzuordnung
- Benutzer-Scope des Uploaders

Regeln:

- `admin` sieht alle Dokumente
- Dokumente mit globalem Team sind fuer berechtigte Benutzer teamuebergreifend
  sichtbar
- Dokumente mit normaler Teamzuordnung sind nur fuer Benutzer mit
  Teamueberschneidung sichtbar
- Legacy-Dokumente ohne Teamzuordnung bleiben ueber den erlaubten Benutzer-Scope
  sichtbar

### Dateigruppen

Dateigruppen koennen ebenfalls Teaminformationen tragen.

Wichtige Punkte:

- Gruppen koennen auf sichtbare Dokumente beschraenkt werden
- Gruppen mit globalem Team sind teamuebergreifend sichtbar
- nicht sichtbare Dateien werden aus Gruppen fuer die jeweilige Sicht gefiltert
- FileSync erzeugt und pflegt Gruppen automatisch

### Dateiselektor im Chat

Der Chat-Dateiselektor kennt in `v0.5`:

- Modus `Alle durchsuchen`
- Modus `In Datei(en) suchen`
- Modus `In Dateigruppe(n) suchen`
- Teamfilter

Wichtig fuer `v0.5`:

- Teamfilter wird bei Benutzerverwaltung automatisch angeboten
- wenn ein gueltiges Standardteam existiert, wird es als Default gesetzt
- ohne Teamfilter werden fuer normale Benutzer primaer global sichtbare Inhalte
  angeboten; ueber den Teamfilter laesst sich gezielt auf Teams eingrenzen

## Ressourcen-Bereich

Der Ressourcen-Tab liegt in `libs/ktem/ktem/pages/resources/__init__.py`.

Moegliche Untertabs:

- `Index-Sammlungen`
- `LLMs`
- `Embeddings`
- `Rerankings`
- `MCP-Server`
- `Benutzer`

Sichtbarkeitsregeln:

- die ersten fuenf Tabs sind nur fuer `admin` sichtbar
- `Benutzer` ist fuer `admin` und `key_user` sichtbar

Damit trennt `v0.5` fachliche Benutzerverwaltung klar von technischer
Systemadministration.

## Einstellungen

Die Einstellungsseite liegt in `libs/ktem/ktem/pages/settings.py`.

Bereiche:

- `Benutzereinstellungen`
- allgemeine Anwendungseinstellungen
- Index-/Retrieval-Einstellungen
- Reasoning-Einstellungen
- `FileSync`

Sichtbarkeit bei aktivierter Benutzerverwaltung:

- `Benutzereinstellungen` sind fuer angemeldete Benutzer sichtbar
- allgemeine, Retrieval- und Reasoning-Einstellungen sind nur fuer `admin`
  sichtbar
- `FileSync` ist nur fuer `admin` sichtbar

Benutzereinstellungen umfassen:

- aktueller Benutzername
- Passwortaenderung
- Abmelden

## FileSync in v0.5

Der lokale FileSync-Dienst ist eine der praegenden Neuerungen von `v0.5`.

Die Implementierung sitzt in `libs/ktem/ktem/filesync.py`, die UI im
`FileSync`-Tab der Einstellungen.

### Zweck

FileSync ueberwacht einen lokalen absoluten Serverordner und importiert passende
Dateien automatisch in die vorhandenen Dateisammlungen.

### Konfiguration

Konfigurierbare Werte:

- lokaler Ordnerpfad
- Scan-Intervall in Minuten
- Dateityp-Filter
- Zuordnung erkannter Unterordner zu erlaubten Teams
- ausfuehrender Sync-Benutzer

### Rechte

FileSync ist ausschliesslich fuer Administratoren vorgesehen:

- nur `admin` darf konfigurieren
- nur `admin` darf einen manuellen Lauf starten
- der Sync benoetigt einen Admin mit Upload-Rechten als technischen Benutzer

### Verhalten

Der Dienst:

- scannt den konfigurierten Ordner regelmaessig
- erkennt neue, geaenderte und geloeschte Dateien
- waehlt anhand der Dateiendung die passende Index-Seite
- uebergibt Teamzuordnungen aus der Ordnerkonfiguration an die Dokumente
- loescht entfernte Dateien auch aus dem Index
- erzeugt bzw. pflegt passende Dateigruppen
- protokolliert Status, letzte Scans und verarbeitete Dateimengen

### Qualitaetssicherung in v0.5

`v0.5` haertet FileSync sichtbar ab:

- Upload-Ergebnisse werden vor dem Veroeffentlichen geprueft
- Dateien ohne durchsuchbaren Inhalt werden erkannt
- fehlgeschlagene Uploads werden gesondert markiert
- Gruppenzuordnung und Chat-Selektor-Verhalten wurden nachgebessert

## Indizes und Dateiformate

Konfigurierte Standard-Sammlung:

- `Dateisammlung`

Je nach GraphRAG-Flags koennen weitere Sammlungen hinzukommen:

- `GraphRAG Sammlung`
- `NanoGraphRAG Sammlung`
- `LightRAG Sammlung`

Unterstuetzte Standard-Dateitypen umfassen aktuell:

- Bilder: `.png`, `.jpeg`, `.jpg`, `.tiff`, `.tif`
- Office und Tabellen: `.xls`, `.xlsx`, `.doc`, `.docx`, `.pptx`, `.csv`
- Web und Text: `.html`, `.mhtml`, `.txt`, `.md`
- Sonstiges: `.pdf`, `.zip`

Spezifisch fuer `v0.5`:

- `.docx` wird ueber `kotaemon.loaders.DocxReader` verarbeitet
- `.pptx` wird ueber `kotaemon.loaders.DoclingReader` verarbeitet

Diese Ueberschreibung soll stabilere lokale Verarbeitung liefern und unnoetige
Abhaengigkeit vom `unstructured`-API-Pfad vermeiden.

## Datenmodell und Persistenz

Die zentralen Tabellen liegen in `libs/ktem/ktem/db/base_models.py` und werden
ueber `libs/ktem/ktem/db/models.py` aktiviert.

Wichtige Tabellen:

- `Conversation`
- `User`
- `Settings`
- `IssueReport`
- `Team`
- `UserAccess`

Fuer `v0.5` relevante Felder:

- `Team`: `id`, `name`, `is_global`
- `UserAccess`: `user_id`, `role`, `team_id`, `default_team_id`,
  `can_read`, `can_upload`

Schema-Verhalten:

- bei deaktiviertem Alembic wird das Schema automatisch erzeugt
- fehlende Spalten `is_global` und `default_team_id` werden beim Start
  nachgezogen
- Legacy-Teammitgliedschaften werden in die neue Zugriffsschicht uebernommen,
  wenn ein Benutzer erstmals gelesen wird

## Betrieb und Deployment

Die README fokussiert den Betrieb ueber Docker.

Dokumentierte Grundvoraussetzungen:

- Python ab `3.10`
- optional Docker
- optional `unstructured` fuer erweiterte Dateiformate ausserhalb der lokal
  stabil abgedeckten Pfade

Die Docker-Beispiele im Repo beruecksichtigen inzwischen:

- deutsche Oberflaeche
- aktivierte Benutzerverwaltung
- persistentes App-Datenverzeichnis
- zusaetzliches Volume fuer `sync-data` im Zusammenhang mit FileSync

## Fazit

Kaidoku `v0.5` ist eine deutsch konfigurierte, lokal betreibbare RAG-Anwendung
mit klar getrennten Rollen, teambezogener Dokumentsteuerung, globalen Teams,
Standardteam-Logik und einer neu hinzugekommenen lokalen FileSync-Funktion.

Fuer den praktischen Betrieb bedeutet das:

- `admin` verwaltet System, Teams, Benutzer und FileSync
- `key_user` verwaltet Benutzer im eigenen Fachkontext und organisiert Inhalte im Team
- `user` nutzt Chat und Dokumente innerhalb der zugewiesenen Teams

Damit beschreibt diese Fassung nicht nur das grobe Produktbild, sondern den
tatsaechlich implementierten Funktionsstand von `v0.5`.
