## Dokumente & System

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
