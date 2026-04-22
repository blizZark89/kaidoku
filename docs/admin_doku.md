# Anleitung: Rolle Admin

## Überblick
Als `admin` hast du vollständige Kontrolle über das gesamte System. Du bist für die Einrichtung, Verwaltung und den Betrieb verantwortlich.

## Was du typischerweise tust

### Benutzer verwalten
- Lege neue Benutzer an (`user`, `key_user`, `admin`)
- Bearbeite oder lösche bestehende Benutzer
- Weise Teams zu oder ändere Rollen

### Teams verwalten
- Erstelle neue Teams
- Lösche Teams (nur wenn sie nicht verwendet werden)
- Markiere Teams als global (für systemweite Sichtbarkeit)

### Inhalte und Ressourcen steuern
- Ordne Dokumente Teams zu
- Verwalte Dateigruppen
- Stelle sicher, dass Inhalte korrekt sichtbar sind

### System konfigurieren
- Verwalte LLMs, Embeddings, Reranking und Indizes
- Konfiguriere MCP-Server
- Passe Systemeinstellungen an

### FileSync nutzen
- Richte FileSync ein
- Starte Synchronisationen manuell

## Wichtige Hinweise
- Du bist keinem festen Team zugeordnet
- Du hast immer Lese- und Uploadrechte
- Änderungen wirken sich oft systemweit aus → vorsichtig vorgehen

## Best Practice
- Vergib `admin`-Rechte nur sehr sparsam
- Nutze `key_user` für Teamverwaltung
- Halte Teams und Berechtigungen übersichtlich