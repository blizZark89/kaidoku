# Kaidoku und der EU AI Act – Kurzanleitung für Betreiber

## 1. Einordnung der Anwendung

Kaidoku ist eine lokal betreibbare RAG-Anwendung (Retrieval-Augmented Generation). Sie nutzt externe oder lokale KI-Modelle, um auf Basis hochgeladener Dokumente Antworten zu generieren.

Aus Sicht des EU AI Acts ist Kaidoku in der Regel **kein Hochrisiko-System** nach Anhang III, solange sie nicht in sensiblen Bereichen wie Recht, Gesundheit oder öffentlicher Sicherheit eingesetzt wird. Sie fällt jedoch unter die Regelungen für **allgemeine KI-Modelle** bzw. **KI-Systeme**, wenn sie kommerziell genutzt wird.

---

## 2. Transparenzpflichten (Art. 52 AI Act)

Nutzer müssen wissen, dass sie mit einer KI interagieren.

**Was konkret zu tun ist:**
- Deutlicher Hinweis im Chat, dass Antworten von einem KI-Modell stammen.
- Hinweis, dass Antworten auf hochgeladenen Dokumenten basieren können.
- Kein Etikettieren von KI-generierten Inhalten als menschlich erstellt.

**Umsetzung in Kaidoku:**
- Dies kann im System-Prompt oder in der Begrüßungsnachricht des Chats erfolgen.
- Im Bereich "Hilfe" oder "Einstellungen" sollte ein kurzer Satz stehen: "Diese Anwendung verwendet KI-Modelle. Antworten können fehlerhaft sein."

---

## 3. Menschliche Aufsicht (Art. 14 AI Act)

Eine KI-Anwendung darf keine Entscheidungen allein treffen, die rechtliche oder erhebliche persönliche Auswirkungen haben.

**Was konkret zu tun ist:**
- Kaidoku sollte als **Unterstützungswerkzeug** positioniert werden, nicht als alleinige Entscheidungsinstanz.
- Wichtige Ausgaben sollten von Menschen geprüft werden.
- Admins können über Team-Zuordnungen steuern, wer Zugriff auf welche Informationen hat.

**Empfohlene Formulierung für Nutzer:**
"Die KI liefert Vorschläge und Informationen aus Ihren Dokumenten. Bitte prüfen Sie wichtige Inhalte vor Weitergabe oder Entscheidungen."

---

## 4. Datenqualität und Dokumentenintegrität (Art. 10 AI Act)

Die Qualität der KI-Antworten hängt direkt von den hochgeladenen Dokumenten ab.

**Was konkret zu tun ist:**
- Nur verlässliche und aktuelle Dokumente hochladen.
- Regelmäßige Prüfung der Dateigruppen auf veraltete Inhalte.
- Nutzung von FileSync, um sicherzustellen, dass Änderungen am Dateisystem automatisch übernommen werden.
- Gelöschte Quellen entfernen, damit keine Antworten auf Basis nicht mehr vorhandener Dokumente erzeugt werden.

---

## 5. Datenschutz und DSGVO

Da Kaidoku interne Dokumente verarbeitet, greifen DSGVO-Regelungen.

**Was konkret zu tun ist:**
- Keine personenbezogenen Daten ohne Rechtsgrundlage hochladen.
- Team-Zuordnungen nutzen, um Zugriffsrechte zu beschränken.
- Bei Nutzung externer APIs (OpenAI, Claude, Gemini) prüfen, ob Dokumente das Haus verlassen.
- Bei lokaler Nutzung (Ollama, lokale Modelle) bleiben alle Daten im eigenen Netzwerk.

**Empfehlung:**
Für vertrauliche Unternehmensdaten ausschließlich lokale Modelle oder On-Premise-APIs verwenden.

---

## 6. Urheberrecht und Training (Art. 53 AI Act)

KI-Modelle können auf urheberrechtlich geschützten Material trainiert sein.

**Was konkret zu tun ist:**
- Kaidoku verwendet externe Modelle (z. B. OpenAI, Anthropic). Diese Anbieter müssen selbst die AI-Act-konformen Trainingsdaten sicherstellen.
- Für die eigene Haftung gilt: Hochgeladene Dokumente müssen entweder eigene Werke oder rechtmäßig erworbene Inhalte sein.
- Keine urheberrechtlich geschützten Dokumente ohne Erlaubnis indexieren.

---

## 7. Risikomanagement und Dokumentation (Art. 9 AI Act)

Betreiber müssen Risiken im Umgang mit KI dokumentieren.

**Was konkret zu tun ist:**
- Ein einfaches Risikoregister führen:
  - "KI gibt falsche Antworten" -> Abhilfe: Hinweis auf Prüfungspflicht durch Menschen.
  - "Unautorisierter Zugriff auf Dokumente" -> Abhilfe: Team-Zuordnungen und Rechteverwaltung prüfen.
  - "Daten verlassen das Unternehmen" -> Abhilfe: Lokale Modelle verwenden oder API-Datenverarbeitung prüfen.

- Änderungen an Konfiguration oder Modellen protokollieren.

---

## 8. Zusammenfassung der Pflichten für Kaidoku-Betreiber

| Pflicht | Status | Umsetzung |
|---------|--------|-----------|
| Transparenz gegenüber Nutzern | Erforderlich | Hinweistext im Chat / Hilfe-Bereich |
| Menschliche Aufsicht | Erforderlich | Klare Kommunikation, dass KI nur unterstützt |
| Datenqualität sicherstellen | Erforderlich | Regelmäßige Pflege der Dateigruppen |
| Datenschutz (DSGVO) | Erforderlich | Team-Zuordnung, lokale Modelle bevorzugen |
| Risikomanagement | Empfohlen | Einfaches Register, regelmäßige Prüfung |
| Urheberrecht beachten | Erforderlich | Nur eigene/lizenzierte Dokumente hochladen |

---

## 9. Konfiguration der Webapp für AI-Act-Konformität

Der AI Act verlangt bestimmte Einstellungen und Anpassungen an der Webapp selbst. Kaidoku (basiert auf Kotaemon/Gradio) lässt sich ohne Änderungen am Quellcode betreiben, **sofern die Konfiguration korrekt gesetzt ist**.

**Was muss an der Webapp konfiguriert/geprüft werden:**

1. **System-Prompt und Willkommensnachricht**
   - In den Chat-Einstellungen einen Hinweis aktivieren: "Diese Anwendung nutzt KI. Antworten können fehlerhaft sein und ersetzen keine fachliche Prüfung durch Menschen."
   - Dies kann über die Datei `flowsettings.py` oder die UI-Einstellungen geschehen.

2. **Nutzermanagement aktivieren**
   - `KH_FEATURE_USER_MANAGEMENT` sollte auf `true` gesetzt sein.
   - So wird sichergestellt, dass nur autorisierte Nutzer auf die hochgeladenen Dokumente zugreifen können.
   - Standard-Admin-Zugang (`admin/admin`) nach der Ersteinrichtung ändern.

3. **Datenverarbeitung dokumentieren**
   - In den Einstellungen muss klar sein, ob Daten lokal bleiben (Ollama, lokale LLMs) oder über externe APIs (OpenAI, Anthropic, Gemini) verarbeitet werden.
   - Bei externen APIs: Nutzer in den Hilfeseiten darauf hinweisen, dass Dokumente den eigenen Server verlassen können.

4. **Keine Quellcode-Änderungen nötig**
   - Kaidoku lässt sich **ohne Änderungen am Quellcode** AI-Act-konform betreiben.
   - Es sind keine neuen Features, UI-Elemente oder Backend-Anpassungen erforderlich.
   - Einzige Voraussetzung: Die Konfiguration (System-Prompt, Nutzermanagement, Datenverarbeitung) muss korrekt gesetzt sein.

5. **Empfohlene Prüfpunkte vor dem produktiven Betrieb**

   | Prüfpunkt | Empfehlung |
   |-----------|-------------|
   | Nutzerregistrierung | Nur mit Admin-Freigabe oder LDAP/SSO |
   | Chat-Hinweise | System-Prompt mit KI-Hinweis versehen |
   | Dateigruppen-Zugriff | Pro Team/Nutzer einschränken |
   | Modell-Auswahl | Nur vertrauenswürdige Endpunkte zulassen |
   | API-Keys | Über Umgebungsvariablen, nicht in der UI |

**Fazit:** Wer Kaidoku produktiv betreibt, muss keine Entwicklerarbeit leisten – die AI-Act-Konformität wird durch korrekte **Konfiguration und organisatorische Maßnahmen** erreicht. Der Aufwand liegt in der Dokumentation und den internen Prozessen, nicht im Code.

---

## 10. Praktischer Hinweis

Der AI Act ist eine sich entwickelnde Regulierung. Für Unternehmen, die Kaidoku produktiv einsetzen, empfiehlt sich eine kurze interne Richtlinie:

1. **Einsatzzweck definieren** – Für welche Aufgaben wird Kaidoku genutzt?
2. **Nutzer schulen** – Hinweis auf KI-Natur, Fehleranfälligkeit und Prüfungspflicht.
3. **Dokumente kuratieren** – Regelmäßige Überprüfung der Dateigruppen.
4. **Datenfluss kontrollieren** – Lokale Modelle bei sensiblen Daten bevorzugen.
5. **Dokumentation aktualisieren** – Änderungen an Modellen oder Konfiguration festhalten.

---

-> Ziel: Sicherer und rechtskonformer Betrieb von Kaidoku im Unternehmen.
