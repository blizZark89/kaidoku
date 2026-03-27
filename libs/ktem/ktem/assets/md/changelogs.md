# Changelogs

## v0.3

##### Änderungen
- Rollen- und Berechtigungssystem eingeführt (Admin, Key User, User)
- Team-basierte Zugriffskontrolle implementiert
- Berechtigungen für Lesen und Datei-Upload ergänzt
- Validierungen für rollenbasierte Aktionen hinzugefügt

##### Admin
- Vollzugriff auf das System
- Kann Benutzer erstellen, bearbeiten und löschen
- Kann Teams erstellen und verwalten
- Kann Benutzer Teams zuordnen

##### Key User
- Kann nur durch Admin erstellt werden
- Ist genau einem Team zugeordnet
- Kann Benutzer für das eigene Team erstellen
- Kann Leserechte und Upload-Rechte vergeben

##### User
- Ist einem Team zugeordnet
- Hat Zugriff nur auf teambezogene Daten
- Kann Dateien lesen
- Kann optional Dateien hochladen (bei entsprechender Berechtigung)

##### Hinweise
- Bestehende Upload-Logik unverändert
- Es wurden ausschließlich Berechtigungsprüfungen ergänzt


## v0.2

### Änderungen
- Team-basierte Dokumentensichtbarkeit eingeführt
- Dokumente standardmäßig privat (Owner-only)
- Mehrfach-Team-Zuordnung für Dokumente
- Neue Suchoption „In Teams suchen“

### Funktionen
- Teamverwaltung im Frontend (ohne Backend-Änderungen)  
- Teams erstellen, umbenennen und löschen (lokal gespeichert)  
- Mehrfachzuordnung von Teams zu Benutzern  
- Neue Spalte „Teams“ in der Benutzerliste (Anzeige als Badges)  
- Neuer Tab „Teams verwalten“  


## v0.1

### Änderungen
- Sprache auf Deutsch umgestellt  
- GraphRAG und LightRAG ausblendbar  
- Minimap standardmäßig deaktiviert  

### Layout
- Chat 40 % / Info 60 %  

### Ausgeblendet
- Hilfe, GraphRAG, LightRAG, Feedback, Schnellupload  


## v0.0.1

### Chat
- Chatbot mit Pipeline-, ReWOO- und ReAct-Agenten  
- Konversationsverwaltung  

### Dateien
- Upload und Nutzung als Kontext  

### Benutzer
- Erstellung, Login/Logout, Passwort ändern  

### Einstellungen & Info
- Allgemeine + Pipeline-Einstellungen  
- Anzeige von Cinnamon AI / Kotaemon Infos  
