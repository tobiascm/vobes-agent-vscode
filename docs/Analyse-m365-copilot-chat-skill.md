# M365 Copilot Chat Skill — Analyse und Erkenntnisse

> **Datum:** 2026-03-29
> **Autor:** Agent-gestuetzte Analyse (Claude Code)
> **Zweck:** Technische Dokumentation fuer Besprechung mit Experten — API-Status, Token-Problematik, UI-Fallback

---

## 1. Zusammenfassung

| Weg | Status | Details |
|-----|--------|---------|
| **Graph Beta API** (`/beta/copilot/conversations`) | **403 Forbidden** | Fehlende Scopes im delegierten Token |
| **Browser-UI via Playwright** | **Funktioniert** | Prompt eingeben, Enter, Antwort auslesen |
| **Token-Transfer (CLI)** | **Unzuverlaessig** | JWT wird bei Transfer durch Agent-Context korrumpiert |

---

## 2. Graph Beta API — Conversations Endpoint

### 2.1 Getesteter Ablauf

```
POST https://graph.microsoft.com/beta/copilot/conversations
Authorization: Bearer <NAA-Token>
Content-Type: application/json
Body: {}
```

### 2.2 Fehlermeldung (403)

```json
{
  "error": {
    "code": "unauthorized",
    "message": " Required scopes = [Sites.Read.All, Mail.Read, People.Read.All, OnlineMeetingTranscript.Read.All, Chat.Read, ChannelMessage.Read.All, ExternalItem.Read.All].",
    "innerError": {
      "date": "2026-03-29T21:12:15",
      "request-id": "1aa1eea5-ad75-4a8a-811c-4e8908ed5950",
      "client-request-id": "1aa1eea5-ad75-4a8a-811c-4e8908ed5950"
    }
  }
}
```

### 2.3 Vorhandene Scopes im NAA-Token

Der Token wird ueber **Nested App Authentication (NAA)** aus der M365 Copilot Web-App bezogen. Die App-ID ist `c0ab8ce9-e9a0-42e7-b064-33d422df41f1` (M365ChatClient).

**Vorhandene Scopes (aus JWT `scp` Claim):**

```
AppCatalog.Read.All
Calendars.Read
Channel.ReadBasic.All
Chat.ReadBasic
ChatMessage.Send
email
Files.ReadWrite.All
FileStorageContainer.Selected
Group.Read.All
InformationProtectionPolicy.Read
MailboxSettings.Read
openid
Organization.Read.All
People.Read
profile
Sites.ReadWrite.All
Team.ReadBasic.All
User.Read
User.Read.All
User.ReadBasic.All
```

### 2.4 Fehlende Scopes (von der API gefordert)

| Scope | Im Token? | Benoetigt fuer |
|-------|-----------|----------------|
| `Sites.Read.All` | Nein (`Sites.ReadWrite.All` vorhanden — sollte genuegen) | Copilot-Grounding auf SharePoint |
| `Mail.Read` | **Nein** | Copilot-Zugriff auf E-Mails |
| `People.Read.All` | **Nein** (`People.Read` vorhanden, `.All` fehlt) | Personensuche |
| `OnlineMeetingTranscript.Read.All` | **Nein** | Meeting-Transkripte |
| `Chat.Read` | **Nein** (`Chat.ReadBasic` vorhanden) | Teams-Chat-Inhalte |
| `ChannelMessage.Read.All` | **Nein** | Teams-Kanal-Nachrichten |
| `ExternalItem.Read.All` | **Nein** | External Connectors / Graph Connectors |

**Kernproblem:** Die App-Registration `c0ab8ce9-e9a0-42e7-b064-33d422df41f1` (M365ChatClient — Microsofts eigene First-Party-App) hat die fuer die Conversations API benoetigten Scopes **nicht im consent**. Vermutlich sind diese Scopes nur ueber eine eigene App-Registration mit Admin-Consent erreichbar.

### 2.5 Einordnung

Die `/beta/copilot/conversations` API ist eine **Beta-API** von Microsoft. Stand Maerz 2026:

- Die API existiert und ist dokumentiert
- Sie erfordert einen spezifischen Satz von Scopes, der ueber den normalen M365ChatClient-NAA-Token hinausgeht
- Es ist unklar, ob diese Scopes ueber Admin-Consent fuer die M365ChatClient-App freigegeben werden koennen, oder ob eine **eigene App-Registration** noetig ist
- Microsoft empfiehlt fuer Copilot-Interaktionen offiziell noch den Plugin/Agent-Weg (Declarative Agents, API Plugins)

---

## 3. Token-Transfer-Problem (betrifft alle M365 Skills)

### 3.1 Problem

Der JWT-Token (~3400 Zeichen) wird beim Transfer durch die Claude Code Tool-Chain **still korrumpiert**:

```
Browser NAA → Playwright Tool Result → Claude Context → Bash CLI Argument
                                                          ↑
                                                    Korruption hier
```

### 3.2 Reproduktion

**Schritt 1:** Token via NAA holen (funktioniert)

```javascript
// via mcp_playwright_browser_evaluate
async () => {
  const nas = window.nestedAppAuthService;
  if (!nas) return { error: 'NAA not ready' };
  const result = await nas.handleRequest({
    method: 'GetToken',
    requestId: 'test-' + Date.now(),
    tokenParams: {
      clientId: 'c0ab8ce9-e9a0-42e7-b064-33d422df41f1',
      resource: 'https://graph.microsoft.com',
      scope: 'https://graph.microsoft.com/.default'
    }
  }, new URL(window.location.href));
  if (!result.success || !result.token?.access_token) {
    return { error: 'Token failed' };
  }
  return { success: true, token: result.token.access_token };
}
```

**Ergebnis:** `{ success: true, token: "eyJ0eXAi..." }` — Token ist gueltig (3440 Zeichen).

**Schritt 2:** Token cachen (schlaegt fehl)

```bash
python .agents/skills/skill-m365-copilot-file-search/copilot_file_search.py cache-token "eyJ0eXAi..."
```

**Ergebnis:** Script meldet "Token cached (expires in 70m 30s)" — sieht erfolgreich aus.

**Schritt 3:** Token verwenden (Korruption sichtbar)

```bash
python scripts/m365_file_reader.py read "Dateiname.xlsx"
# → Exit 2: TOKEN_EXPIRED
```

**Schritt 4:** Direkte Pruefung gegen Graph API:

```python
r = requests.get('https://graph.microsoft.com/v1.0/me',
                 headers={'Authorization': 'Bearer ' + token})
# → 401: {"error":{"code":"InvalidAuthenticationToken","message":"Signature is invalid."}}
```

**Der Token hat die korrekte Laenge und das korrekte Format, aber die Signatur ist ungueltig.** Einzelne Zeichen wurden waehrend des Transfers veraendert.

### 3.3 Beweis: Gleicher Token funktioniert direkt im Browser

Wird der Token im Browser gehalten und der API-Call direkt per `fetch()` im selben `browser_evaluate` gemacht, funktioniert er einwandfrei:

```javascript
// via mcp_playwright_browser_evaluate — Token + API-Call in einem Schritt
async () => {
  const nas = window.nestedAppAuthService;
  if (!nas) return { error: 'NAA not ready' };
  const result = await nas.handleRequest({
    method: 'GetToken',
    requestId: 'fr-' + Date.now(),
    tokenParams: {
      clientId: 'c0ab8ce9-e9a0-42e7-b064-33d422df41f1',
      resource: 'https://graph.microsoft.com',
      scope: 'https://graph.microsoft.com/.default'
    }
  }, new URL(window.location.href));
  if (!result.success || !result.token?.access_token) {
    return { error: 'Token failed' };
  }
  const token = result.token.access_token;

  // Direkt im Browser die Graph API aufrufen — funktioniert!
  const searchBody = {
    requests: [{
      entityTypes: ['driveItem'],
      query: { queryString: 'EKEK1_Verschiebung und Teilung WU_2025.xlsx' },
      from: 0,
      size: 3
    }]
  };
  const r = await fetch('https://graph.microsoft.com/v1.0/search/query', {
    method: 'POST',
    headers: {
      'Authorization': 'Bearer ' + token,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(searchBody)
  });

  const data = await r.json();
  // → Status 200, 3 Treffer zurueckgegeben
  return { status: r.status, data: data };
}
```

**Ergebnis:** Status 200, korrekte Suchergebnisse. Der Token ist gueltig — er wird nur beim Transfer durch den Agent-Context korrumpiert.

### 3.4 Getestete Workarounds (alle gescheitert)

| Versuch | Ergebnis |
|---------|----------|
| `cache-token TOKEN` als CLI-Argument | Signatur ungueltig |
| Token direkt in JSON-Cache-Datei schreiben (Python) | Signatur ungueltig — gleiche Korruption |
| Token ueber Claudes `Write`-Tool in Datei schreiben | Nicht zuverlaessig — selber Transferweg |
| `browser_run_code` mit `require('fs')` | `ReferenceError: require is not defined` |
| `browser_run_code` mit `import('fs')` | `ERR_VM_DYNAMIC_IMPORT_CALLBACK_MISSING` |
| CDP Session oeffnen | `Protocol error: Not allowed` |
| Browser-Download via Blob URL | Download-Event feuert nicht |

### 3.5 Loesung: "Browser-as-API-Proxy"

Token nie durch den Agent-Context transferieren. Stattdessen Token + API-Call in einem einzigen `browser_evaluate` ausfuehren. Der Token bleibt vollstaendig im Browser-Kontext.

---

## 4. Browser-UI-Weg (Playwright) — funktionierender Copilot Chat

### 4.1 Getesteter Ablauf

**Schritt 1:** M365 Copilot Chat oeffnen

```javascript
// mcp_playwright_browser_navigate
url: "https://m365.cloud.microsoft/chat"
```

**Schritt 2:** Prompt eingeben

```javascript
// mcp_playwright_browser_type
element: "Copilot chat message input"
ref: "e325"  // textbox "Nachricht an Copilot senden"
text: "Test"
```

Playwright-Code der ausgefuehrt wird:

```javascript
await page.getByRole('textbox', { name: 'Nachricht an Copilot senden' }).fill('Test');
```

**Schritt 3:** Absenden

```javascript
// mcp_playwright_browser_press_key
key: "Enter"
```

**Schritt 4:** Auf Antwort warten

```javascript
// mcp_playwright_browser_wait_for
text: "Copilot said:"
timeout: 30000
```

Playwright-Code:

```javascript
await page.getByText("Copilot said:").first().waitFor({ state: 'visible' });
```

**Schritt 5:** Antwort aus Snapshot lesen

Nach dem Warten enthaelt der Page-Snapshot die vollstaendige Copilot-Antwort als strukturierten Text im `article`-Element:

```yaml
article "Copilot said: ✅ Test erfolgreich – ich bin einsatzbereit...":
  - generic:
    - heading "Copilot said:"
    - img "Copilot's Logo"
    - generic: Copilot
  - generic:
    - paragraph: "✅ **Test erfolgreich – ich bin einsatzbereit.**"
    - paragraph: "Ich habe testweise in deinen **Chats, E-Mails und Dateien** ..."
    - list:
      - listitem: "✅ Copilot antwortet"
      - listitem: "✅ Enterprise-Suche funktioniert"
      - listitem: "✅ Deutsch als Sprache gesetzt ist"
      - listitem: "✅ Struktur + TL;DR eingehalten werden"
    - paragraph: "→ **alles ok ✅**"
    - separator
    - paragraph: "**TL;DR:** Testnachricht angekommen ✅ ..."
```

### 4.2 Copilot-Antwort (vollstaendig)

> **Test erfolgreich – ich bin einsatzbereit.**
>
> Ich habe testweise in deinen Chats, E-Mails und Dateien nach dem Begriff „Test" gesucht. Dabei gibt es zwar Treffer (z. B. eine Test von dir selbst sowie mehrere Test-Dateien), aber keine aktuelle Aufgabe oder Anfrage, die sich konkret aus deinem letzten „Test"-Post ableiten laesst.
>
> Wenn du pruefen wolltest, ob:
> - Copilot antwortet
> - Enterprise-Suche funktioniert
> - Deutsch als Sprache gesetzt ist
> - Struktur + TL;DR eingehalten werden
>
> → alles ok
>
> **TL;DR:** Testnachricht angekommen. Copilot funktioniert, Suche lief, bereit fuer die naechste Aufgabe.

### 4.3 Conversation-URL

Nach dem Chat wechselt die URL zu:

```
https://m365.cloud.microsoft/chat/conversation/273ddf22-136c-476d-bf08-7735c7a183dd
```

Die Conversation-ID kann fuer Follow-up-Nachrichten verwendet werden.

---

## 5. Vergleich der Wege

| Kriterium | Graph Beta API | Browser-UI (Playwright) |
|-----------|---------------|------------------------|
| **Funktioniert** | Nein (403) | Ja |
| **Authentifizierung** | NAA-Token (fehlende Scopes) | Browser-Session (SSO) |
| **Latenz** | ~2-5s (wenn es gaenge) | ~10-20s (UI-Rendering + Generierung) |
| **Strukturierte Ausgabe** | JSON | Page Snapshot (semi-strukturiert) |
| **Follow-up moeglich** | Ja (conversation-id) | Ja (gleiche Seite) |
| **Attachments/Dateien** | Ueber API-Body | Ueber UI-Button "Inhalt hinzufuegen" |
| **Abhaengigkeiten** | Token mit korrekten Scopes | Playwright MCP + aktive M365-Session |
| **Zuverlaessigkeit** | Hoch (wenn Scopes vorhanden) | Mittel (UI kann sich aendern) |

---

## 6. Empfohlene naechste Schritte

### 6.1 Kurzfristig (sofort umsetzbar)

- **Copilot Chat Skill auf Playwright-UI umstellen** — Prompt in Textbox eingeben, Enter, Antwort aus Snapshot lesen
- Das Python-Script `m365_copilot_chat.py` als Fallback behalten fuer den Fall, dass die API-Scopes spaeter freigegeben werden

### 6.2 Mittelfristig (mit IT/Admin klaeren)

Folgende Fragen an den M365-Admin / Azure AD-Admin stellen:

1. **Kann fuer die App `c0ab8ce9-e9a0-42e7-b064-33d422df41f1` (M365ChatClient) ein Admin-Consent fuer die fehlenden Scopes erteilt werden?**
   - Insbesondere: `Mail.Read`, `People.Read.All`, `OnlineMeetingTranscript.Read.All`, `Chat.Read`, `ChannelMessage.Read.All`, `ExternalItem.Read.All`
   - Beachte: Dies ist Microsofts First-Party-App — moeglicherweise ist kein eigener Consent moeglich

2. **Ist eine eigene App-Registration mit den benoetigten Scopes machbar?**
   - Wenn ja: App-Registration im Azure AD erstellen mit den 7 geforderten Scopes
   - Neuen `clientId` in den NAA-Aufruf einsetzen
   - Admin-Consent einholen

3. **Gibt es im VW-Tenant eine Tenant-Policy, die `/beta/copilot/conversations` explizit blockiert?**
   - Manche Tenants deaktivieren Beta-APIs ueber Conditional Access oder API Policies

### 6.3 Langfristig

- Beobachten, ob Microsoft die Conversations API aus Beta in GA (General Availability) ueberfuehrt
- Bei GA koennten sich die Scope-Anforderungen aendern

---

## 7. Technische Referenz

### 7.1 NAA Token-Beschaffung (JavaScript im Browser)

```javascript
async () => {
  const nas = window.nestedAppAuthService;
  if (!nas) return { error: 'NAA not ready — Seite nicht vollstaendig geladen' };

  const result = await nas.handleRequest({
    method: 'GetToken',
    requestId: 'copilot-chat-' + Date.now(),
    tokenParams: {
      clientId: 'c0ab8ce9-e9a0-42e7-b064-33d422df41f1',
      resource: 'https://graph.microsoft.com',
      scope: 'https://graph.microsoft.com/.default'
    }
  }, new URL(window.location.href));

  if (!result.success || !result.token?.access_token) {
    return { error: 'Token request failed', details: result.error };
  }
  return {
    success: true,
    token: result.token.access_token,
    expiresOn: result.token.expires_on
  };
}
```

### 7.2 Conversations API (aktuell 403)

```javascript
// Conversation anlegen
const convResp = await fetch('https://graph.microsoft.com/beta/copilot/conversations', {
  method: 'POST',
  headers: {
    'Authorization': 'Bearer ' + token,
    'Content-Type': 'application/json'
  },
  body: '{}'
});

// Chat-Nachricht senden
const chatResp = await fetch(
  `https://graph.microsoft.com/beta/copilot/conversations/${conversationId}/chat`,
  {
    method: 'POST',
    headers: {
      'Authorization': 'Bearer ' + token,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      message: { text: 'Fasse dieses Dokument zusammen.' }
    })
  }
);
```

### 7.3 Python-Script (aktuell nicht nutzbar wegen 403)

```bash
# Conversation anlegen + Prompt senden
python scripts/m365_copilot_chat.py chat "Test"

# Mit explizitem Token
python scripts/m365_copilot_chat.py chat "Test" --token TOKEN

# Bestehende Conversation fortsetzen
python scripts/m365_copilot_chat.py chat "Follow-up" --conversation-id CONV_ID

# Token-Status pruefen
python scripts/m365_copilot_chat.py check-token
```

### 7.4 Cache-Datei

```
Pfad:   userdata/tmp/.graph_token_cache.json
Format: {"token": "eyJ0eXAi...", "exp": 1774821264}
```

Alle drei M365-Scripts (`copilot_file_search.py`, `m365_file_reader.py`, `m365_copilot_chat.py`) nutzen dieselbe Cache-Datei.
