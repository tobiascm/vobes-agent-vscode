# ChatGPT File Upload Protocol — Reverse-Engineering Dokumentation

## Datum: 2026-04-23

## Methodik

Upload-Flow per **Playwright MCP Network-Interceptor** im Browser analysiert.
Drei Interceptor-Iterationen waren nötig:

1. **v1** — Basis-fetch-Interceptor: URLs + Response-Bodies erfasst, aber Request-Bodies fehlten (ChatGPT nutzt `new Request()` statt plain-URL fetch)
2. **v2** — Header-Interceptor: Alle Request/Response-Headers erfasst, Body noch leer
3. **v3** — Request.clone()-Interceptor: Body des `Request`-Objekts via `.clone().text()` extrahiert → **vollständige API-Spec**

Der PUT-Upload auf Azure Blob Storage wurde vom Interceptor nicht erfasst, da ChatGPT dafür vermutlich den nativen `XMLHttpRequest` oder einen separaten fetch-Pfad nutzt.

## Upload-Flow (4 Schritte)

### Schritt 0: Conversation Prepare (parallel zum Upload)

```
POST /backend-api/f/conversation/prepare
Content-Type: application/json
```

```json
{
  "action": "next",
  "fork_from_shared_post": false,
  "parent_message_id": "client-created-root",
  "model": "gpt-5-4-thinking",
  "client_prepare_state": "success",
  "timezone_offset_min": -120,
  "timezone": "Europe/Berlin",
  "conversation_mode": {"kind": "primary_assistant"},
  "system_hints": [],
  "attachment_mime_types": ["text/plain"],
  "supports_buffering": true,
  "supported_encodings": ["v1"],
  "client_contextual_info": {"app_name": "chatgpt.com"},
  "thinking_effort": "extended"
}
```

**Bemerkenswert:** `attachment_mime_types` enthält den MIME-Type der hochgeladenen Datei.

### Schritt 1: Upload-URL anfordern

```
POST /backend-api/files
Content-Type: application/json
Authorization: Bearer <jwt>
```

**Request Body:**
```json
{
  "file_name": "example.txt",
  "file_size": 3647,
  "use_case": "my_files",
  "timezone_offset_min": -120,
  "reset_rate_limits": false
}
```

**Response:**
```json
{
  "status": "success",
  "upload_url": "https://sdmntpr<region>.oaiusercontent.com/files/<file_id>/raw?se=...&sig=...",
  "file_id": "file_<hex>"
}
```

Die `upload_url` ist eine **Azure Blob Storage SAS-URL** mit zeitlich begrenzter Schreibberechtigung (~5 Min).

### Schritt 2: Datei auf Azure Blob hochladen

```
PUT <upload_url>
Content-Type: application/octet-stream
Body: <raw file bytes>
```

Direkt-Upload auf Azure Storage. Kein ChatGPT-Backend involviert.

### Schritt 3: Processing starten + Stream abonnieren

```
POST /backend-api/files/process_upload_stream
Content-Type: application/json
Authorization: Bearer <jwt>
```

**Request Body:**
```json
{
  "file_id": "file_<hex>",
  "use_case": "my_files",
  "index_for_retrieval": true,
  "file_name": "example.txt",
  "entry_surface": "chat_composer"
}
```

**Response:** NDJSON-Stream (`text/event-stream`):

| Progress | Event | Beschreibung |
|----------|-------|--------------|
| 0% | `file.processing.started` | Processing gestartet |
| 20% | `file.processing.file_ready` | Datei downloadbereit |
| — | `file.indexing.in_progress` | Retrieval-Index wird aufgebaut |
| 40% | `file.indexing.in_progress` | `total_tokens` verfügbar |
| 60% | `file.indexing.in_progress` | Weiter indexiert |
| 80% | `file.indexing.in_progress` | Fast fertig |
| — | `file.indexing.completed` | Index fertig |
| — | `file.indexing.done` | `[DONE]` |
| 100% | `file.processing.completed` | Alles abgeschlossen |

### Schritt 4: Prompt mit file_id senden

Die `file_id` wird im normalen `/backend-api/conversation`-Payload als Attachment referenziert.

## DOM nach Upload

Die Datei erscheint im Composer als `group`-Element:

```
group "example.txt"
  ├── button "example.txt"           (klickbar, öffnet Preview)
  ├── generic: Dateiname + "Dokument"
  └── button "Datei 1 entfernen: example.txt"  (Entfernen-Button)
```

## Relevante Headers

Alle API-Calls verwenden diese Custom-Headers:

| Header | Wert |
|--------|------|
| `authorization` | `Bearer <JWT>` |
| `content-type` | `application/json` |
| `oai-client-build-number` | `6108575` |
| `oai-client-version` | `prod-...` |
| `oai-device-id` | UUID |
| `oai-language` | `de-DE` |
| `oai-session-id` | UUID |

## Implementierungsentscheidung

### Gewählter Ansatz: Playwright FileChooser (Variante A)

Statt die API direkt nachzubauen (was Base64-Transfer der Datei in den Browser und Token-Management erfordern würde), nutzen wir Playwright's native FileChooser-API:

```javascript
const [fileChooser] = await Promise.all([
    page.waitForEvent('filechooser', {timeout: 10000}),
    attachButton.click(),
]);
await fileChooser.setFiles(filePath);
```

**Vorteile:**
- ~50 Zeilen statt ~200 für API-Ansatz
- Kein Token-Management, kein Base64-Transfer
- Automatisch kompatibel mit API-Änderungen
- Nutzt bestehende `browser_run_code`-Infrastruktur

**Erkenntnisse zum FileChooser-Button:**
- Manueller Klick auf "Dateien und mehr hinzufügen" öffnet manchmal kein Dialog (Bug in ChatGPT UI?)
- Drag & Drop funktioniert zuverlässig
- Programmatischer Klick via `page.locator().click()` in `browser_run_code` funktioniert zuverlässig
- Der Button hat `aria-label="Dateien und mehr hinzufügen"` (DE) bzw. `aria-label="Attach files"` (EN)

### Verworfene Alternativen

| Variante | Grund der Ablehnung |
|----------|---------------------|
| **B: API-Upload via evaluate** | Zu viel Code (Base64-Transfer, Token-Extraktion, SAS-URL-Handling, NDJSON-Parsing) |
| **C: Drag & Drop Simulation** | DataTransfer-API fragil, browser-abhängig |

## CLI-Usage

```bash
# Datei + Frage
python chatgpt_research.py run --question "Analysiere diese Datei" --file /pfad/zur/datei.txt

# Nur Frage (wie bisher)
python chatgpt_research.py run --question "Was ist 1+1?"
```
