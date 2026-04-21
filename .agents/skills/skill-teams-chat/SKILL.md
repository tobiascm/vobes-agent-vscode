---
name: skill-teams-chat
description: "1:1 Teams-Chat-Nachrichten ueber die Teams Chat Service API senden."
---

# Skill: Teams Chat

Sendet und liest 1:1 Chat-Nachrichten in Microsoft Teams ueber die Chat Service API (kein Playwright noetig).

## Wann verwenden?

- Agent soll eine Teams-Chat-Nachricht an eine Person senden
- Agent soll Nachrichten aus einem 1:1 Chat lesen
- Trigger: Teams-Nachricht senden, Teams Chat, schicke Nachricht an, Teams Message, Teams Chat lesen

## Wann NICHT verwenden?

- **Kanal-Nachrichten** (Channel Posts) — nicht unterstuetzt
- **Gruppen-Chats** — nicht unterstuetzt (nur 1:1)
- **E-Mails senden** → `skill-m365-mail-agent`

## Voraussetzungen

- Edge mit Teams eingeloggt (fuer Token aus LocalStorage)
- `requests` installiert

## Workflow

### Schritt 1: Empfaenger-Email ermitteln

Falls nur ein Name bekannt ist, zuerst per Outlook-Adress-Cache (`outlook_address_cache.py` → `lookup_cached_addresses()`) die Email-Adresse aufloesen. Nur bei Cache-Miss auf `skill-personensuche-groupfind` zurueckfallen.

### Schritt 2: Nachricht senden

```bash
python .agents/skills/skill-teams-chat/scripts/teams_chat.py send <email> <nachricht...>
```

### Schritt 3: Nachrichten lesen (optional)

```bash
python .agents/skills/skill-teams-chat/scripts/teams_chat.py read <email> [--limit N]
```

Gibt die letzten N Nachrichten (default 20) als Plaintext aus, HTML-Tags werden entfernt.

**Beispiel:**

```bash
python .agents/skills/skill-teams-chat/scripts/teams_chat.py send max.mustermann@volkswagen.de "Hallo Max, kurze Info zum Stand."
```

**Ausgabe bei Erfolg:** `OK — gesendet an max.mustermann@volkswagen.de (id=...)`
**Ausgabe bei Fehler:** `FEHLER: ...` auf stderr, Exit-Code 1

## Script-Referenz

| Befehl | Beschreibung |
|--------|-------------|
| `send <email> <text...>` | Sendet 1:1 Chat-Nachricht an die Person mit der angegebenen Email |
| `read <email> [--limit N]` | Liest die letzten N Nachrichten (default 20) aus dem 1:1 Chat |

## API-Details

| Parameter | Wert |
|-----------|------|
| Endpoint | `POST https://teams.microsoft.com/api/chatsvc/emea/v1/users/ME/conversations/{conv}/messages` |
| Auth | Bearer Token (Scope `ic3.teams.office.com`) |
| Token-Quelle | Refresh-Token aus Edge LocalStorage (via `m365_mail_search_token`) |
| Empfaenger-Aufloesung | Graph API `/users/{email}` → AAD Object-ID |
| Conv-ID-Format | `19:{sorted_uuid1}_{sorted_uuid2}@unq.gbl.spaces` (Auto-Create) |
| Nachrichtenformat | `RichText/Html` — Plain-Text wird in `<p>...</p>` gewrappt |

## Haeufige Fehler

| Fehler | Ursache | Loesung |
|--------|---------|---------|
| `Kein RefreshToken` | Edge/Teams nicht eingeloggt oder Token abgelaufen | Edge oeffnen, teams.microsoft.com aufrufen |
| `403 Forbidden` | Token ohne ausreichende Rechte | Edge/Teams neu einloggen |
| `404 Not Found` | Email-Adresse nicht im AAD gefunden | Email pruefen, ggf. per GroupFind aufloesen |
| `TOKEN_REQUEST_FAILED` | Azure AD lehnt Refresh ab | Teams in Edge neu oeffnen |
