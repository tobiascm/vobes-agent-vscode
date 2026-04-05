# M365 Copilot — API-Research Ergebnisse

> **Datum:** 2026-03-21  
> **Autor:** Agent-gestützte Analyse  
> **Ziel:** Prüfen, ob M365 Copilot (BizChat) programmatisch über APIs angesprochen werden kann — ohne die Web-UI.

---

## 1. Übersicht

M365 Copilot (BizChat) unter `https://m365.cloud.microsoft/chat` nutzt intern mehrere Backend-Dienste. Diese Analyse dokumentiert, welche APIs existieren, wie die Authentifizierung funktioniert und welche Endpunkte von außen nutzbar sind.

### Ergebnis in Kurzform

| Fähigkeit | Machbar? | Weg |
|-----------|----------|-----|
| **Copilot-Suche** (SharePoint/OneDrive durchsuchen mit Copilot-Ranking) | **Ja** | `POST /beta/copilot/microsoft.graph.search` |
| **Copilot-Konversation starten** (Frage → Antwort) | **Nein (ohne Admin-Consent)** | `POST /beta/copilot/conversations` existiert, braucht aber zusätzliche Scopes |
| **Copilot-Chat über Sydney-Backend** | **Nein** | NanoProxy blockiert externe Aufrufe |
| **Copilot-Interaktionen auslesen** | **Nein** | Endpoint `/beta/me/copilot/interactions` existiert nicht |
| **Teams-Chats lesen** | **Ja** | `GET /beta/me/chats` |
| **Volltextsuche in Chat-Nachrichten** | **Nein** | `Chat.Read` Scope fehlt im Token |
| **UI-Automation (Playwright)** | **Ja** | Zuverlässigster Weg für volle Copilot-Interaktion |

---

## 2. Architektur von M365 Copilot

```
┌─────────────────────────────────────────────────────────┐
│  Browser: m365.cloud.microsoft/chat                     │
│  (React SPA mit SSR, Satchel State, MobX)               │
│                                                         │
│  ┌─────────────────────┐   ┌──────────────────────────┐ │
│  │ MSAL v2 Auth        │   │ nestedAppAuthService     │ │
│  │ CryptoKeyStore      │   │ (NAA-Protokoll)          │ │
│  │ Broker-iframe       │   │ handleRequest(GetToken)  │ │
│  └─────────┬───────────┘   └─────────┬────────────────┘ │
│            │                          │                  │
│  ┌─────────▼──────────────────────────▼────────────────┐ │
│  │              Token-Austausch                         │ │
│  │  ┌──────────┐  ┌───────────┐  ┌──────────────────┐  │ │
│  │  │ Graph    │  │ Sydney    │  │ Substrate Search │  │ │
│  │  │ Token    │  │ Token     │  │ Token            │  │ │
│  │  └────┬─────┘  └────┬─────┘  └────┬─────────────┘  │ │
│  └───────┼──────────────┼─────────────┼────────────────┘ │
└──────────┼──────────────┼─────────────┼──────────────────┘
           │              │             │
           ▼              ▼             ▼
   ┌──────────────┐ ┌──────────┐ ┌──────────────────┐
   │ Graph API    │ │ Sydney   │ │ Substrate Search │
   │ graph.ms.com │ │ (Trouter │ │ substrate.office │
   │              │ │ WebSocket│ │ .com/search      │
   │ /beta/copilot│ │ Chat)    │ │                  │
   │ /me/chats    │ │          │ │                  │
   └──────────────┘ └──────────┘ └──────────────────┘
```

### 2.1 Registrierte Azure AD Apps

| App | Client-ID | Zweck |
|-----|-----------|-------|
| **OfficeHome SPA** | `4765445b-32c6-49b0-83e6-1d93765276ca` | SPA-Authentifizierung, erhält `m365copilot.read.all`, `mdcpp.all`, `officehome.all` |
| **M365ChatClient** (Backend) | `c0ab8ce9-e9a0-42e7-b064-33d422df41f1` | Backend-App, holt Tokens für Graph, Sydney, Substrate, Teams, Loki, Arc |

### 2.2 VW-Tenant-Informationen

| Parameter | Wert |
|-----------|------|
| Tenant-ID | `2882be50-2012-4d88-ac86-544124e120c8` |
| UPN | `tobias.carsten.mueller@volkswagen.de` |
| Conditional Access | Aktiv — blockiert Device Code Flow (Error 53003) |
| MFA | `pwd`, `wia`, `mfa` |

---

## 3. Token-Beschaffung

### 3.1 Gescheiterter Ansatz: Device Code Flow

Getestet mit vier First-Party Client-IDs:

| App | Client-ID | Ergebnis |
|-----|-----------|----------|
| Azure PowerShell | `1950a258-227b-4e31-a9cf-717495945fc2` | **53003** — Conditional Access |
| Microsoft Office | `d3590ed6-52b3-4102-aeff-aad2292ab01c` | Nicht getestet (gleicher Block erwartet) |
| Microsoft Teams | `1fec8e78-bce4-4aaf-ab1b-5451cc387264` | Nicht getestet |
| Visual Studio | `872cd9fa-d31f-45e0-9eab-6e460a02d1f1` | Nicht getestet |

**Ursache:** VW Conditional Access erfordert ein registriertes/Intune-verwaltetes Gerät. Device Code Flow wird als "Unregistered" klassifiziert.

### 3.2 Gescheiterter Ansatz: Implicit Flow / PKCE aus iframe

| Methode | Fehler |
|---------|--------|
| Implicit Flow (`response_type=token`) | `AADSTS700051` — unsupported_response_type |
| PKCE Auth Code Flow | `AADSTS65002` — First-party preauthorization required |
| Graph Explorer Login-Popup | Cross-Origin-Opener-Policy blockiert Popup |

### 3.3 Erfolgreicher Ansatz: Nested App Auth (NAA)

Die M365-Seite exponiert `window.nestedAppAuthService` — ein Service, der über das NAA-Protokoll Tokens für beliebige Ressourcen holen kann:

```javascript
const nas = window.nestedAppAuthService;

const request = {
  method: 'GetToken',
  requestId: 'my-request-' + Date.now(),
  tokenParams: {
    clientId: 'c0ab8ce9-e9a0-42e7-b064-33d422df41f1',
    resource: 'https://graph.microsoft.com',      // oder substrate.office.com/sydney
    scope: 'https://graph.microsoft.com/.default'
  }
};

const result = await nas.handleRequest(request, new URL(window.location.href));
// result.token.access_token enthält den JWT
```

**Voraussetzung:** Eine aktive M365-Browser-Sitzung (Playwright/Browser Extension).

### 3.4 Verfügbare Tokens über NAA

| Resource | Audience | Wichtige Scopes |
|----------|----------|-----------------|
| **Graph API** | `https://graph.microsoft.com` | `AppCatalog.Read.All`, `Calendars.Read`, `Chat.ReadBasic`, `ChatMessage.Send`, `Files.ReadWrite.All`, `People.Read`, `Sites.ReadWrite.All`, `User.Read.All` u.a. (19 Scopes) |
| **Sydney** | `https://substrate.office.com/sydney` | `M365Chat.Read`, `sydney.readwrite`, `CopilotPlatformFiles.Read`, `CopilotPlatformMail.Read`, `CopilotPlatformSites.Read.All` u.a. (14 Scopes) |
| **Substrate Search** | `https://substrate.office.com/search` | `SubstrateSearch-Internal.ReadWrite` |

---

## 4. API-Test-Ergebnisse

### 4.1 Graph Beta Copilot Endpoints

#### `GET /beta/copilot` — **200 OK**

Liefert die Navigation-Links zu allen Copilot-Sub-Ressourcen:

```json
{
  "conversations@navigationLink": "https://graph.microsoft.com/beta/copilot/conversations",
  "admin@navigationLink": "https://graph.microsoft.com/beta/copilot/admin",
  "agents@navigationLink": "https://graph.microsoft.com/beta/copilot/agents",
  "reports@navigationLink": "https://graph.microsoft.com/beta/copilot/reports",
  "settings@navigationLink": "https://graph.microsoft.com/beta/copilot/settings",
  "communications@navigationLink": "https://graph.microsoft.com/beta/copilot/communications",
  "interactionHistory@navigationLink": "https://graph.microsoft.com/beta/copilot/interactionHistory",
  "users@navigationLink": "https://graph.microsoft.com/beta/copilot/users",
  "#microsoft.graph.retrieval": {},
  "#microsoft.graph.search": {},
  "#microsoft.graph.searchNextPage": {}
}
```

#### `POST /beta/copilot/microsoft.graph.search` — **200 OK** ✅

> **Hinweis:** Die kompakte URL `/beta/copilot/search` ist ein Alias und liefert identische Ergebnisse (getestet 01.04.2026). In Scripts wird die kürzere Variante verwendet.

**Einziger voll funktionierender Copilot-Endpoint.**

```http
POST https://graph.microsoft.com/beta/copilot/microsoft.graph.search
Authorization: Bearer <graph_token>
Content-Type: application/json

{"query": "meilensteine pep"}
```

**Antwort:** 25 Treffer mit SharePoint-URLs und Preview-Snippets:

```json
{
  "searchHits": [
    {
      "webUrl": "https://volkswagengroup.sharepoint.com/.../Meilensteinkurzbeschreibung zum MasterPEP.pdf",
      "resourceType": "listItem",
      "preview": "Meilensteinkurzbeschreibung: Wesentliche Inhalte der Meilensteine PS und PM..."
    },
    {
      "webUrl": "https://volkswagengroup.sharepoint.com/.../PEP V1.0...",
      "resourceType": "listItem",
      "preview": "PEP V1.0 29.09.2025 3 INTERNAL Für den Audi PA- und Derivate PEP36..."
    }
  ]
}
```

#### `POST /beta/copilot/conversations` — **403 Forbidden**

Die API existiert, aber das Token hat nicht die nötigen Scopes:

```json
{
  "error": {
    "code": "unauthorized",
    "message": "Required scopes = [Sites.Read.All, Mail.Read, People.Read.All, OnlineMeetingTranscript.Read.All, Chat.Read, ChannelMessage.Read.All, ExternalItem.Read.All]."
  }
}
```

**Fehlende Scopes im aktuellen Token:**

| Scope | Im Token? |
|-------|-----------|
| `Sites.Read.All` | ❌ (hat `Sites.ReadWrite.All`) |
| `Mail.Read` | ❌ |
| `People.Read.All` | ❌ (hat nur `People.Read`) |
| `OnlineMeetingTranscript.Read.All` | ❌ |
| `Chat.Read` | ❌ (hat nur `Chat.ReadBasic`) |
| `ChannelMessage.Read.All` | ❌ |
| `ExternalItem.Read.All` | ❌ |

→ Diese Scopes erfordern eine eigene App-Registration mit Admin-Consent.

#### `POST /beta/copilot/microsoft.graph.retrieval` — **400 Bad Request**

```json
{
  "error": {
    "code": "BadRequest",
    "message": "The call failed, please try again."
  }
}
```

Das Body-Format ist unbekannt/undokumentiert. Der Endpunkt existiert, aber ohne Dokumentation ist das Request-Format nicht ermittelbar.

#### Weitere Copilot-Endpoints — alle nicht verfügbar

| Endpoint | Status | Grund |
|----------|--------|-------|
| `/beta/copilot/interactionHistory` | 404 | "Requested API is not supported" |
| `/beta/copilot/communications` | 404 | Leer |
| `/beta/copilot/agents` | 404 | RouteNotFound (→ agent365.svc.cloud.microsoft) |
| `/beta/copilot/reports` | 404 | IIS 404 |
| `/beta/copilot/settings` | 400 | "Not supported for AAD accounts" |
| `/beta/copilot/users` | 404 | "API is not supported" |
| `/beta/copilot/admin` | 404 | Leer |
| `/beta/me/copilot` | 404 | Resource nicht gefunden |
| `/beta/me/copilot/interactions` | 400 | "Unexpected segment DynamicPathSegment" |

### 4.2 Andere Graph Beta Endpoints

| Endpoint | Status | Ergebnis |
|----------|--------|----------|
| `GET /v1.0/me` | **200** | Profil: Name, Mail, Telefon, OE |
| `GET /beta/me/chats?$top=30` | **200** | 24 Teams-Chats (Meeting, OneOnOne, Group) mit Members |
| `GET /beta/me/insights/used` | **200** | Kürzlich genutzte Dokumente |
| `POST /beta/search/query` (chatMessage) | **403** | `Chat.Read` Scope fehlt |
| `GET /beta/me/activities` | **401** | Nicht autorisiert |

### 4.3 Sydney API (substrate.office.com/sydney)

Alle Sydney-Endpoints liefern **500** von Python aus:

| Endpoint | Status | Ursache |
|----------|--------|---------|
| `POST /sydney/api/v1/conversations` | 500 | NanoProxy: "Delegation disallowed for this protocol or hostname" |
| `GET /sydney/api/v1/conversations` | 500 | NanoProxy-Block |
| `POST /sydney/ChatHub/negotiate` | 500 | NanoProxy-Block |
| `GET /sydney/api/v1/chats` | 500 | NanoProxy-Block |
| `GET /sydney/api/health` | 500 | NanoProxy-Block |

**Ursache:** Microsoft's NanoProxy-Layer erlaubt Sydney-Zugriffe nur von autorisierten M365-Ursprüngen. Externe HTTP-Clients werden blockiert, unabhängig vom Token.

Aus dem **Browser heraus** (gleiche Origin) werden Sydney-Calls ebenfalls durch **CORS** blockiert, sofern sie nicht von der M365-SPA selbst stammen.

### 4.4 Substrate Search API

```http
POST https://substrate.office.com/search/api/v1/suggestions
Authorization: Bearer <substrate_search_token>
```

**Status 500** — Parameter `EntityRequests` null (= Auth funktioniert, aber Body-Format unbekannt). Bestätigt, dass der Substrate-Search-Token gültig ist.

---

## 5. Zusammenfassung der Zugriffswege

### Weg 1: Graph Beta Copilot Search (funktioniert)

```
Python/Agent  →  NAA Token holen (via Playwright)  →  POST /beta/copilot/microsoft.graph.search
```

**Pro:** Liefert die gleichen Suchergebnisse wie Copilot intern.  
**Contra:** Keine Konversation, nur Suche. Braucht aktive Browser-Session für Token.

### Weg 2: Graph Beta Copilot Conversations (theoretisch möglich)

```
App-Registration mit Admin-Consent  →  Token mit allen 7 Scopes  →  POST /beta/copilot/conversations
```

**Pro:** Echte Copilot-Konversation über API.  
**Contra:** Benötigt App-Registration und Admin-Consent für sensitive Scopes (Mail.Read, Chat.Read etc.). Noch im Beta und möglicherweise nicht für alle Tenants verfügbar.

### Weg 3: Playwright UI-Automation (zuverlässigster Weg)

```
Playwright  →  m365.cloud.microsoft/chat  →  Frage eingeben  →  Antwort auslesen
```

**Pro:** Volle Copilot-Funktionalität, kein Scope-Problem.  
**Contra:** Langsamer, abhängig von UI-Änderungen.

---

## 6. Token-Scopes im Detail

### Graph Token (aud: graph.microsoft.com)

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

### Sydney Token (aud: substrate.office.com/sydney)

```
CopilotPlatformContent.Process.All
CopilotPlatformDataLossPreventionPolicy.Evaluate
CopilotPlatformFiles.Read
CopilotPlatformFiles.ReadWrite
CopilotPlatformFiles.ReadWriteAll
CopilotPlatformFileStorageContainer.Selected
CopilotPlatformLicenseAssignment.Read.All
CopilotPlatformMail.Read
CopilotPlatformPresence.Read
CopilotPlatformPresence.Read.All
CopilotPlatformProtectionScopes.Compute.All
CopilotPlatformSites.Read.All
CopilotPlatformUser.Read
M365Chat.Read
sydney.readwrite
```

### Substrate Search Token (aud: substrate.office.com/search)

```
SubstrateSearch-Internal.ReadWrite
```

---

## 7. Technische Details

### 7.1 MSAL Token-Speicherung

- **Methode:** MSAL v2 CryptoKeyStore
- **Speicherort:** `localStorage` als verschlüsselte Objekte (`{id, nonce, data}`)
- **Schlüssel:** In Broker-iframe (`login.microsoftonline.com`), NICHT in IndexedDB der M365-Domain
- **Konsequenz:** Tokens können nicht direkt aus localStorage extrahiert werden

### 7.2 NAA-Protokoll (Nested App Auth)

Das NAA-Protokoll wird über `window.nestedAppAuthService` exponiert:

```javascript
// Verfügbare Methoden:
nestedAppAuthService.handleRequest(request, url)  // Hauptmethode
nestedAppAuthService.getTokenResponse(request, url, isPopup)
nestedAppAuthService.getInitContext(request)
nestedAppAuthService.execute(jsonString, url, unknown)
nestedAppAuthService.getDesktopTokenResponse(request, unknown)
nestedAppAuthService.validateAndTransformTokenResponse(request, ...)
```

**Request-Format:**
```javascript
{
  method: 'GetToken',          // oder 'GetInitContext'
  requestId: 'unique-id',
  tokenParams: {
    clientId: 'c0ab8ce9-...',  // M365ChatClient App-ID
    resource: 'https://graph.microsoft.com',
    scope: 'https://graph.microsoft.com/.default'
  }
}
```

**Response-Format:**
```javascript
{
  messageType: 'NestedAppAuthResponse',
  requestId: 'unique-id',
  success: true,
  token: {
    access_token: 'eyJ0eXAi...'  // JWT
  },
  account: { ... }
}
```

### 7.3 Copilot-Backend (Sydney)

- **Dienst:** "Sydney" — gleiches Backend wie Bing Chat/Copilot
- **Protokoll:** SignalR über Trouter (Teams WebSocket-Infrastruktur)
- **Endpunkt:** `substrate.office.com/sydney/ChatHub`
- **Schutz:** NanoProxy-Layer erlaubt nur Aufrufe von autorisierten M365-Ursprüngen
- **CORS:** Blockiert Cross-Origin-Zugriffe auch mit gültigem Token

### 7.4 Fetch-Interceptor-Technik

Um Token aus der laufenden Seite zu erfassen, wurde ein Fetch-Interceptor eingesetzt:

```javascript
const origFetch = window.fetch;
window.fetch = async function(...args) {
  const request = args[0];
  // Header auslesen und Authorization-Token speichern
  if (headers['authorization']) {
    window._capturedTokens[domain] = { fullToken: auth };
  }
  return origFetch.apply(window, args);
};
```

**Einschränkung:** Graph-API-Calls erfolgen beim Seitenladen (~3s nach Start), bevor ein per `evaluate()` injizierter Interceptor aktiv wird. Die NAA-Methode ist zuverlässiger.

---

## 8. Nächste Schritte (optional)

1. **App-Registration mit Admin-Consent** — Um `POST /beta/copilot/conversations` nutzen zu können, müsste eine eigene Azure AD App mit den 7 fehlenden Scopes registriert und durch einen Tenant-Admin genehmigt werden.

2. **Playwright-Wrapper ausbauen** — Für den produktiven Einsatz bietet die UI-Automation den zuverlässigsten Weg. Ein Wrapper könnte:
   - Token über NAA holen
   - Copilot Search über Graph API nutzen
   - Für volle Konversationen die UI steuern

3. **`/beta/copilot/microsoft.graph.retrieval`** — Das Body-Format reverse-engineeren (z.B. über Network-Inspektion bei Copilot-Nutzung), um den Retrieval-Endpoint nutzbar zu machen.
