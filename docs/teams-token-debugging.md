# Teams Graph Token – Debugging-Erkenntnisse & Referenz

> Stand: 2026-04-09 – Ergebnisse aus dem Debugging eines Token-Ausfalls über Nacht.

## Überblick

Der `skill-m365-copilot-mail-search` nutzt einen **separaten Token-Resolver** (`m365_mail_search_token.py`), der unabhängig vom zentralen Copilot-NAA-Resolver arbeitet. Der Token wird für die Microsoft Graph API benötigt und muss den Scope `Mail.Read` enthalten.

### Beteiligte Dateien

| Datei | Zweck |
|---|---|
| `.agents/skills/skill-m365-copilot-mail-search/scripts/m365_mail_search_token.py` | Token-Resolver (6-Stufen-Fallback) |
| `scripts/m365_copilot_graph_token.py` | Playwright-Bridge-Infrastruktur (importiert) |
| `userdata/tmp/.graph_token_cache_teams.json` | Cache-Datei für den Teams-Token |
| `userdata/tmp/.graph_token_cache.json` | Cache für den Copilot-NAA-Token (anderes System!) |

### Nicht verwechseln: Drei Token-Systeme

```
┌──────────────────────────┬──────────────────────────┬──────────────────────────┐
│ Mail Search Token        │ Copilot File Search      │ Outlook REST Token       │
│ (dieser Resolver)        │ Token                    │                          │
├──────────────────────────┼──────────────────────────┼──────────────────────────┤
│ Teams Web MSAL           │ Playwright NAA Bridge    │ Playwright Request       │
│                          │ zu Copilot               │ Interception             │
├──────────────────────────┼──────────────────────────┼──────────────────────────┤
│ Mail.Read, Calendar.Read │ Graph/.default (breit)   │ outlook.office.com       │
├──────────────────────────┼──────────────────────────┼──────────────────────────┤
│ .graph_token_cache_      │ .graph_token_cache.json  │ .outlook_token_          │
│ teams.json               │                          │ cache.json               │
├──────────────────────────┼──────────────────────────┼──────────────────────────┤
│ Client-ID:               │ NAA (Copilot-App)        │ Nonce-gebunden           │
│ 5e3ce6c0-...             │                          │                          │
└──────────────────────────┴──────────────────────────┴──────────────────────────┘
```

---

## Die 6-Stufen-Fallback-Kette

```
1. Expliziter Token (--token)
2. Cache-Datei (.graph_token_cache_teams.json)
3. Playwright Bridge (Teams localStorage)
4. LevelDB Local Recovery (Edge Dateien)
5. Refresh Token (OAuth2 Token Endpoint)
6. Teams Reopen (Edge öffnen + warten)
```

### Stufe 1: Expliziter Token

```python
# Aufruf mit explizitem Token
python m365_mail_search.py search --token "eyJ0eXAi..." --query "Budget"
```

Das Script validiert, ob der Token den benötigten Scope hat:

```python
def _has_required_scope(token: str, required_scopes: tuple[str, ...]) -> bool:
    payload = _decode_jwt_payload(token)
    scope_set = {scope.lower() for scope in payload.get("scp", "").split()}
    return all(scope.lower() in scope_set for scope in required_scopes)
```

### Stufe 2: Cache-Datei

```json
// userdata/tmp/.graph_token_cache_teams.json
{
  "token": "eyJ0eXAi...",
  "exp": 1775683504,
  "source": "teams-refresh-token"
}
```

**Validierung:**
- `exp` muss mindestens 120 Sekunden in der Zukunft liegen (`MIN_TOKEN_LIFETIME = 120`)
- JWT-Payload muss die benötigten Scopes enthalten
- Token wird **nicht** gegen `/me` validiert (nur Expiry + Scope-Check)

```python
def _candidate_from_cache_payload(data, required_scopes):
    token = str(data.get("token", "")).strip()
    exp = int(data["exp"])
    if exp <= time.time() + MIN_TOKEN_LIFETIME:
        return None  # abgelaufen
    if not _has_required_scope(token, required_scopes):
        return None  # falscher Scope
    return token, exp, source
```

### Stufe 3: Playwright Bridge

Öffnet Teams im Browser über Playwright MCP und liest den MSAL-Token aus `localStorage`:

```javascript
// JavaScript wird in teams.microsoft.com ausgeführt
const tokenKeysRaw = localStorage.getItem('msal.token.keys.5e3ce6c0-...');
const keys = JSON.parse(tokenKeysRaw);

for (const atKey of (keys.accessToken || [])) {
  const atData = JSON.parse(localStorage.getItem(atKey));
  // Filter: nur graph.microsoft.com Tokens mit benötigten Scopes
  if (atData.target.includes('graph.microsoft.com')) {
    const payload = JSON.parse(atob(parts[1]));
    // Prüfe Scopes, wähle den mit dem spätesten Ablauf
  }
}
```

**Bekanntes Problem:** Teams braucht oft >30 Sekunden zum Laden, was zu Playwright-Timeouts führt. Wenn Teams nicht schnell genug lädt, schlägt diese Stufe fehl und die nächste wird versucht.

### Stufe 4: LevelDB Local Recovery

Liest die MSAL-Token direkt aus den Edge-Browserdateien im Dateisystem:

```
C:\Users\{user}\AppData\Local\Microsoft\Edge\User Data\Default\Local Storage\leveldb\
```

Die `.ldb`- und `.log`-Dateien enthalten die localStorage-Einträge im Binärformat.

```python
def _candidate_leveldb_files() -> list[Path]:
    leveldb_dir = _teams_leveldb_dir()
    files = []
    for path in leveldb_dir.iterdir():
        if path.suffix.lower() not in {".ldb", ".log"}:
            continue
        files.append(path)
    # Neueste zuerst
    return sorted(files, key=lambda item: item.stat().st_mtime, reverse=True)
```

#### KRITISCH: Multi-Needle-Suche (Fix vom 2026-04-09)

**Problem:** MSAL-Einträge in LevelDB haben **keine einheitliche JSON-Schlüsselreihenfolge**:

- AccessTokens beginnen typischerweise mit `{"homeAccountId":"...`
- RefreshTokens beginnen oft mit `{"credentialType":"RefreshToken",...`
- Manche Einträge beginnen mit `{"clientId":"...`

**Alter Code (fehlerhaft):**
```python
# ❌ Fand nur Objekte die mit homeAccountId beginnen
needle = b'{"homeAccountId":"'
```

**Neuer Code (korrekt):**
```python
# ✅ Drei verschiedene Needles decken alle MSAL-JSON-Varianten ab
needles = [
    b'{"homeAccountId":"',
    b'{"credentialType":"',
    b'{"clientId":"',
]
```

**Auswirkung des alten Bugs:** Wenn der AccessToken in LevelDB abgelaufen war (z. B. über Nacht), wurden die vorhandenen RefreshTokens nicht gefunden, weil sie mit einem anderen JSON-Key begannen. Die gesamte Fallback-Kette scheiterte.

#### JSON-Extraktion aus Binärdaten

LevelDB-Dateien sind Binärformat. Die JSON-Objekte werden mit einem Balanced-Brace-Parser extrahiert:

```python
def _extract_balanced_json(blob: bytes, start_index: int) -> bytes | None:
    depth = 0
    in_string = False
    escaped = False
    for index in range(start_index, len(blob)):
        value = blob[index]
        if in_string:
            if escaped:
                escaped = False
            elif value == 0x5C:  # backslash
                escaped = True
            elif value == 0x22:  # quote
                in_string = False
            continue
        if value == 0x22:      # quote
            in_string = True
        elif value == 0x7B:    # {
            depth += 1
        elif value == 0x7D:    # }
            depth -= 1
            if depth == 0:
                return blob[start_index:index + 1]
    return None
```

#### Deduplizierung

Gleiche Tokens können in mehreren LevelDB-Dateien vorkommen (durch Kompaktierung). Der Marker verhindert Duplikate:

```python
marker = "|".join([
    obj.get("credentialType", ""),
    obj.get("clientId", ""),
    obj.get("target", "") or "",
    obj.get("expiresOn", "") or "",
    obj.get("secret", "")[:64],  # Nur die ersten 64 Zeichen
])
```

### Stufe 5: Refresh Token

Wenn ein gültiger RefreshToken gefunden wurde (aus Stufe 4), wird ein neuer AccessToken per OAuth2-Refresh angefragt:

```python
token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
body = {
    "client_id": "5e3ce6c0-2b1f-4285-8d4b-75ee78787346",
    "grant_type": "refresh_token",
    "refresh_token": refresh_record.secret,
    "scope": "https://graph.microsoft.com/Mail.Read offline_access openid profile",
}
```

#### KRITISCH: SPA Origin-Header (Fix vom 2026-04-09)

**Problem:** Der Teams Web Client (`5e3ce6c0-...`) ist bei Azure AD als **Single-Page Application (SPA)** registriert. Azure AD verlangt für SPA-Token-Refreshes einen Cross-Origin-Request:

```
AADSTS9002327: Tokens issued for the 'Single-Page Application' client-type
may only be redeemed via cross-origin requests.
```

**Lösung:** Der `Origin`-Header muss auf `https://teams.microsoft.com` gesetzt werden:

```python
# ✅ Mit Origin-Header funktioniert der SPA-Refresh
headers = {"Origin": "https://teams.microsoft.com"}
response = requests.post(token_url, data=body, headers=headers, timeout=20)
```

**Ohne diesen Header scheitert JEDER Token-Refresh über Python**, auch wenn der RefreshToken selbst gültig ist.

#### Tenant-ID-Ermittlung

Die Tenant-ID wird aus dem `homeAccountId` der Token-Records extrahiert:

```python
def _tenant_id(records: list[TokenRecord]) -> str:
    for record in records:
        if "." in record.home_account_id:
            parts = record.home_account_id.split(".", 1)
            # homeAccountId = "{user-oid}.{tenant-id}"
            if len(parts) == 2 and parts[1]:
                return parts[1]
```

#### Scope-Kandidaten

Der Resolver probiert verschiedene Scope-Strings, die in den vorhandenen AccessTokens gefunden wurden:

```python
def _graph_scope_candidates(records: list[TokenRecord]) -> list[str]:
    scopes = []
    for record in records:
        if record.credential_type == "AccessToken":
            if "graph.microsoft.com" in record.target.lower():
                scopes.append(record.target.strip())
    # Fallback: Minimaler Scope
    minimal = "https://graph.microsoft.com/Mail.Read offline_access openid profile"
    scopes.append(minimal)
    return scopes
```

#### Fehlerbehandlung

```python
# Weiche Fehler → nächsten Scope/RefreshToken probieren
if error in {"invalid_grant", "invalid_request"}:
    return None

# Harte Fehler → Exception
raise TokenAcquisitionError("TOKEN_REQUEST_FAILED", ...)
```

`invalid_grant` bedeutet: der RefreshToken ist revoked oder abgelaufen.
`invalid_request` bedeutet: der Scope-String oder die Redirect-URI passt nicht → weich behandeln und nächsten probieren.

### Stufe 6: Teams Reopen

Wenn alles andere scheitert, wird Edge mit Teams geöffnet und auf neue Tokens gewartet:

```python
edge_path = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
subprocess.Popen([
    str(edge_path),
    "--new-window",
    "--profile-directory=Default",
    "https://teams.microsoft.com/v2/"
])

# Dann wird 25 Sekunden lang alle 3 Sekunden LevelDB gescannt
deadline = time.time() + 25
while time.time() < deadline:
    time.sleep(3)
    resolved = _resolve_from_local_state(...)
    if resolved:
        return token, exp, f"{source}+teams-reopen"
```

---

## Debugging: Token-Status prüfen

### Cache prüfen

```python
import json, time, base64
from pathlib import Path

cache = Path("userdata/tmp/.graph_token_cache_teams.json")
data = json.loads(cache.read_text("utf-8"))

# JWT dekodieren
parts = data["token"].split(".")
payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=="))

print(f"Quelle:   {data['source']}")
print(f"Ablauf:   {time.strftime('%H:%M:%S', time.localtime(data['exp']))}")
print(f"Restzeit: {(data['exp'] - time.time()) / 60:.1f} min")
print(f"Scopes:   {payload.get('scp', '')}")
print(f"Audience: {payload.get('aud', '')}")
```

### LevelDB scannen

```python
import json, os
from pathlib import Path

CLIENT_ID = "5e3ce6c0-2b1f-4285-8d4b-75ee78787346"
leveldb_dir = (
    Path(os.environ["LOCALAPPDATA"])
    / "Microsoft" / "Edge" / "User Data" / "Default"
    / "Local Storage" / "leveldb"
)

needles = [b'{"homeAccountId":"', b'{"credentialType":"', b'{"clientId":"']
records = []

for path in sorted(leveldb_dir.glob("*.ldb"), key=lambda f: f.stat().st_mtime, reverse=True):
    blob = path.read_bytes()
    for needle in needles:
        start = 0
        while (idx := blob.find(needle, start)) >= 0:
            # ... _extract_balanced_json + json.loads ...
            start = idx + len(needle)

# Filtern auf Teams-Client
teams_records = [r for r in records if r.get("clientId") == CLIENT_ID]
access_tokens = [r for r in teams_records if r["credentialType"] == "AccessToken"]
refresh_tokens = [r for r in teams_records if r["credentialType"] == "RefreshToken"]

print(f"AccessTokens:  {len(access_tokens)}")
print(f"RefreshTokens: {len(refresh_tokens)}")
```

### Token gegen Graph API validieren

```python
import requests

token = "eyJ0eXAi..."
resp = requests.get(
    "https://graph.microsoft.com/v1.0/me",
    headers={"Authorization": f"Bearer {token}"},
    timeout=15
)
print(f"Status: {resp.status_code}")
if resp.status_code == 200:
    print(f"User: {resp.json().get('displayName')}")
elif resp.status_code == 401:
    print("Token ungültig oder abgelaufen")
```

### Manueller SPA-Refresh

```python
import requests

tenant_id = "2882be50-2012-4d88-ac86-544124e120c8"
refresh_token = "0.AVAA..."  # aus LevelDB extrahiert

resp = requests.post(
    f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
    data={
        "client_id": "5e3ce6c0-2b1f-4285-8d4b-75ee78787346",
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "scope": "https://graph.microsoft.com/Mail.Read offline_access openid profile",
    },
    # ⚠️ PFLICHT für SPA-Clients!
    headers={"Origin": "https://teams.microsoft.com"},
    timeout=20,
)

if resp.status_code == 200:
    new_token = resp.json()["access_token"]
    print("Refresh erfolgreich!")
else:
    print(f"Fehler: {resp.json().get('error_description', '')[:200]}")
```

---

## Typische Fehlerbilder

### 1. Token über Nacht abgelaufen

**Symptom:** `TOKEN_EXPIRED` beim Aufruf morgens, obwohl Teams im Browser läuft.

**Ursache:** 
- Graph AccessToken hat eine Lebensdauer von ca. 60–90 Minuten
- Über Nacht läuft der Token ab und wird von MSAL nicht automatisch erneuert
- LevelDB enthält dann nur noch Nicht-Graph-Tokens (augloop, pushchannel, etc.)
- Der Graph-Token wurde aus dem MSAL-Cache entfernt oder überschrieben (LevelDB-Kompaktierung)

**Lösung:** RefreshToken muss gefunden und genutzt werden (siehe Fixes oben).

### 2. AADSTS9002327 – SPA Cross-Origin

**Symptom:**
```
AADSTS9002327: Tokens issued for the 'Single-Page Application' client-type
may only be redeemed via cross-origin requests.
```

**Ursache:** Azure AD erkennt, dass der Request nicht aus einem Browser kommt (fehlender `Origin`-Header).

**Lösung:** `Origin: https://teams.microsoft.com` Header zum POST hinzufügen.

### 3. LevelDB-Dateien gesperrt

**Symptom:** `OSError` beim Lesen der LevelDB-Dateien.

**Ursache:** Edge hat die Dateien gelockt.

**Lösung:** Das Script verwendet `try/except OSError: continue` und überspringt gesperrte Dateien. In der Praxis reichen die ungesperrten Dateien aus.

### 4. Playwright-Timeout bei Teams

**Symptom:** `TimeoutError: browserBackend.callTool: Timeout 30000ms exceeded.` bei `browser_navigate` oder `browser_wait_for`.

**Ursache:** Teams Web ist eine schwere SPA mit SSO-Redirects, die oft >30 Sekunden braucht.

**Lösung:** Der Resolver fällt automatisch auf Stufe 4 (LevelDB) zurück. Wenn der Playwright-Schritt scheitert, wird der Cache wiederhergestellt.

### 5. Kein RefreshToken vorhanden

**Symptom:** Kein RefreshToken in LevelDB gefunden.

**Ursache:** 
- Edge-Profil wurde bereinigt
- Noch nie bei Teams angemeldet
- LevelDB wurde vollständig kompaktiert und enthält nur AccessTokens

**Lösung:** Teams manuell in Edge öffnen und anmelden → Stufe 6 (Teams Reopen).

---

## Wichtige Konstanten

```python
CLIENT_ID = "5e3ce6c0-2b1f-4285-8d4b-75ee78787346"  # Teams Web Client
TEAMS_URL = "https://teams.microsoft.com/v2/"
GRAPH_ME_URL = "https://graph.microsoft.com/v1.0/me"
MIN_TOKEN_LIFETIME = 120  # Sekunden
PLAYWRIGHT_WAIT_SECONDS = 5
```

## Token-Struktur in LevelDB

### AccessToken-Objekt

```json
{
  "homeAccountId": "4e71c99f-...-3d3a78362151.2882be50-...-544124e120c8",
  "credentialType": "AccessToken",
  "secret": "eyJ0eXAiOiJKV1Qi...",
  "target": "https://graph.microsoft.com/Mail.Read https://graph.microsoft.com/.default",
  "clientId": "5e3ce6c0-2b1f-4285-8d4b-75ee78787346",
  "expiresOn": "1775683504",
  "environment": "login.windows.net",
  "realm": "2882be50-2012-4d88-ac86-544124e120c8"
}
```

### RefreshToken-Objekt

```json
{
  "credentialType": "RefreshToken",
  "homeAccountId": "4e71c99f-...-3d3a78362151.2882be50-...-544124e120c8",
  "secret": "0.AVAAULuCKBI...",
  "clientId": "5e3ce6c0-2b1f-4285-8d4b-75ee78787346",
  "expiresOn": "1775774339",
  "environment": "login.windows.net",
  "realm": "2882be50-2012-4d88-ac86-544124e120c8",
  "lastUpdatedAt": "1775715133905"
}
```

**Beachte:** Das `expiresOn`-Feld bei RefreshTokens ist ebenfalls ein Unix-Timestamp, typischerweise 24 Stunden gültig. Die Reihenfolge der JSON-Keys ist **nicht garantiert** – deshalb die Multi-Needle-Suche.

---

## Checkliste: Token-Probleme debuggen

1. **Cache-Datei prüfen** → `userdata/tmp/.graph_token_cache_teams.json`
   - Existiert sie? Ist `exp` in der Zukunft?
2. **LevelDB scannen** → Gibt es Graph-AccessTokens? RefreshTokens?
   - Alle drei Needles verwenden!
3. **Scopes prüfen** → Hat der Token `Mail.Read`?
4. **Token validieren** → `GET https://graph.microsoft.com/v1.0/me` mit dem Token
5. **Refresh testen** → Mit `Origin: https://teams.microsoft.com` Header
6. **Edge-Profil prüfen** → Ist das Default-Profil das richtige?
7. **Teams im Browser öffnen** → Erzeugt das neue Tokens in LevelDB?

---

## Gesamtfluss (Diagramm)

```
          m365_mail_search.py search/read
                     │
           _resolve_token(scope=Mail.Read)
                     │
    ┌────────────────┼────────────────────────────────┐
    │                │                                │
    v                v                                v
 --token         Cache gültig?                    Playwright
(explizit)         │                              Bridge
                   ├── ja → FERTIG                   │
                   └── nein                          │
                         │                    ┌──────┴──────┐
                         │                    │ Teams lädt?  │
                         │                    ├─ ja → Token  │
                         │                    └─ nein (Timeout)
                         │                           │
                         ├───────────────────────────┘
                         │
                    LevelDB scannen
                    (3 Needles!)
                         │
               ┌─────────┼─────────┐
               │                   │
          AccessToken         RefreshToken
          mit Mail.Read?      vorhanden?
               │                   │
          ├─ ja → FERTIG      ├─ ja → OAuth2 Refresh
          └─ nein                  │   (+ Origin-Header!)
                                   │
                              ├─ Erfolg → FERTIG
                              └─ Fehler
                                   │
                            Teams in Edge öffnen
                            25s lang LevelDB pollen
                                   │
                              ├─ Token → FERTIG
                              └─ TOKEN_EXPIRED
```
