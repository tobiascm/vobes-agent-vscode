---
name: skill-m365-copilot-chat
description: "M365 Copilot Chat ueber Playwright DOM-Interaktion. Kein Token-Transfer, kein Python-HTTP-Client. Nutze diesen Skill wenn der User eine Copilot-Frage stellen und die Antwort zurueckbekommen moechte. Trigger: frage copilot, m365 copilot chat, prompt an copilot senden, bizchat fragen, copilot follow-up."
---

# Skill: M365 Copilot Chat (Playwright DOM-Interaktion)

Stellt eine Frage an **Microsoft 365 Copilot Chat** ueber die Copilot-Web-UI
via Playwright MCP. Kein Token-Transfer, kein Python-HTTP-Client.

> **Hintergrund:** Die M365-Copilot-Web-App sendet Chat-Nachrichten intern
> ueber Teams Trouter WebSocket — es gibt keinen einfachen REST-Endpoint
> fuer `fetch()`. Deshalb laeuft der gesamte Workflow ueber semantische
> DOM-Selektoren, die stabil und zuverlaessig sind.

## Wann verwenden?

- Der User moechte eine **Frage an M365 Copilot** stellen
- Der User moechte ein **Follow-up** in derselben Copilot-Konversation
- Der User moechte **M365-grounded** Antworten (Chats, Mails, Dateien)
- Keywords: `Copilot fragen`, `M365 Copilot`, `BizChat`, `Prompt an Copilot`

## Wann NICHT verwenden?

| Aufgabe | Stattdessen verwenden |
|---------|-----------------------|
| Dateien in SharePoint/OneDrive suchen | `$skill-copilot-search` |
| Dateiinhalt direkt lesen | `$skill-m365-file-reader` |
| Confluence/Jira lesen | `mcp-atlassian` oder `local_rag` |
| Generische Webseiteninteraktion | `$skill-browse-intranet` |

## Voraussetzungen

1. **Playwright MCP Server** muss verfuegbar sein
2. **M365-Sitzung** muss im Browser aktiv sein (User eingeloggt)
3. User braucht **M365 Copilot Lizenz**

## Architektur

- **Kein Token-Cache, kein `--token`, kein Graph-HTTP-Call**
- **Kein Python-Script noetig** — der gesamte Workflow laeuft ueber Playwright MCP Tools
- Semantische Selektoren (`getByRole('textbox', { name: '...' })`) — keine fragilen CSS/XPath

## Workflow

### 1. M365 Copilot oeffnen

```
mcp_playwright_browser_navigate → https://m365.cloud.microsoft/chat
```

Danach `mcp_playwright_browser_snapshot` pruefen:
- Textbox `"Nachricht an Copilot senden"` sichtbar → Session aktiv, weiter
- Login-Seite → User bitten sich einzuloggen, danach erneut pruefen

### 2. (Optional) Neuen Chat starten

Falls ein frischer Chat gewuenscht ist, den Button "Neuer Chat" klicken:

```
mcp_playwright_browser_click → ref des "Neuer Chat"-Buttons
```

### 3. Prompt senden

```
mcp_playwright_browser_type
  ref:     <ref der Textbox "Nachricht an Copilot senden">
  text:    "<USER_PROMPT>"
  submit:  true
```

### 4. Auf Abschluss warten

Waehrend Copilot generiert, zeigt die UI den Button **"Generieren beenden"** an.
Sobald die Antwort fertig ist, verschwindet er:

```
mcp_playwright_browser_wait_for → textGone: "Generieren beenden"
```

### 5. Antwort aus Snapshot lesen

```
mcp_playwright_browser_snapshot
```

Die Antwort steht im letzten `article "Copilot said: ..."` Node.
Relevante Inhalte befinden sich in den `paragraph`, `strong`, `list`, `listitem` Kinder-Nodes.

Beispiel-Snapshot-Struktur:
```yaml
article "Copilot said: Hallo Welt ...":
  paragraph: Hallo Welt
  paragraph:
    strong: "TL;DR:"
    text: Alles gut.
```

Den Text aller `paragraph`/`generic`-Kinder des letzten `article "Copilot said: ..."` extrahieren.

### 6. Follow-up (optional)

Fuer Follow-ups einfach Schritt 3–5 wiederholen — die Conversation bleibt offen.
Die conversation_id ist in der Page URL sichtbar:
`https://m365.cloud.microsoft/chat/conversation/<ID>`

## Fehlerbehandlung

| Problem | Erkennung | Loesung |
|---------|-----------|---------|
| Nicht eingeloggt | Snapshot zeigt Login-Seite statt Textbox | User bitten sich einzuloggen |
| Copilot-Lizenz fehlt | Fehlermeldung in der UI | User informieren |
| Timeout beim Warten | `wait_for` laeuft in Timeout | Snapshot pruefen, ggf. erneut senden |
| Leere Antwort | `article "Copilot said:"` ohne Text-Kinder | Snapshot pruefen, Prompt ggf. wiederholen |

## Selektoren-Referenz

| Element | Selektor |
|---------|----------|
| Eingabefeld | `textbox "Nachricht an Copilot senden"` |
| Generierung laeuft | Text `"Generieren beenden"` sichtbar |
| Generierung fertig | Text `"Generieren beenden"` verschwunden |
| Antwort | Letzter `article "Copilot said: ..."` |
| Neuer Chat | `button "Neuer Chat"` |
| Conversation ID | Aus Page URL `/chat/conversation/<ID>` |
- **Kein `--token` CLI-Argument**
- **Kein Graph-Chat-HTTP-Call in Python**
- **Kein DOM-Geklicke fuer Senden/Lesen**
- Der Browser ist **Auth- und Request-Proxy**
- Python ist nur **Config-/Payload-/Render-Helper**

## Einmalige Einrichtung: Backend-Endpoint hinterlegen

Der tatsaechliche Backend-Endpoint der M365-Copilot-Web-App muss einmalig ermittelt werden
(z. B. ueber `mcp_playwright_browser_network_requests` waehrend eines manuellen Test-Chats)
und lokal gespeichert werden:

```bash
python scripts/m365_copilot_chat.py set-endpoint "https://<<<COPILOT-WEB-BACKEND>>>"