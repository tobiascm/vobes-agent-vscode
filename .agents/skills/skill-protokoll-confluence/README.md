# skill-protokoll-confluence

Erstellt und pflegt **Protokollseiten** in Confluence (Spaces `VOBES` und `EKEK1`) fuer Regeltermine. Der Skill kann den Inhalt entweder direkt vom User entgegennehmen oder aus **Teams-Recordings** und **lokalen Audioaufzeichnungen** automatisch beschaffen — inklusive Sprecher-Tags und Meeting-Screenshots.

> **Definitive Spec:** Verbindliche Regeln (Sammlerseiten, Wiki-Markup, Task-Format, Diff-Workflow) stehen in [`SKILL.md`](SKILL.md). Diese README ist die Einstiegs-Uebersicht.

## Wann verwendet?

Trigger-Phrasen:
- *"Bitte Protokoll erstellen"*, *"Mache das Protokoll vom letzten Termin"*
- *"Protokoll vom Meeting XY"*, *"Protokoll aus Recording bauen"*
- *"Aktualisiere das Protokoll vom 12.03."*

## Zwei Workflows

### A. Manuell — User liefert Inhalt
Der User uebergibt Stichpunkte/Notizen direkt im Chat. Skill formt sie in Wiki-Markup, prueft auf bestehende Kindseite, legt an oder updatet via `mcp-atlassian`. Details: [`SKILL.md` Abschnitte 1-6](SKILL.md).

### B. Aus Recording oder Audio — Skript holt Transkript
Quellen-Kaskade (chronologisch zusammengefuehrt):

| # | Quelle | Token | Sprecher? |
|---|---|---|---|
| 1 | OneDrive `Recordings/*.mp4` (Teams) | Graph + SharePoint | **Ja** ueber `streamContent?is=1&applymediaedits=false` |
| 2 | OneDrive `Dokumente/Audioaufzeichnungen/meeting_*.md` | nur lokal (Sync) | Nein (Win-Voice-Recorder) |
| 3 | OneDrive `Desktop/Screenshots/*.png\|jpg` | nur lokal | n/a — werden zeitlich ins Meeting-Fenster einsortiert |

**Sprecher-Tags im VTT** sind ein eigenes Thema mit vielen Stolperfallen (welcher Endpoint, welcher Token, welcher Scope, welche Diarization-Fallbacks). Vollstaendige Referenz: [`docs/teams-transkription-mit-sprechern.md`](../../../docs/teams-transkription-mit-sprechern.md).

## Dateistruktur

```
skill-protokoll-confluence/
├── README.md                          ← diese Datei (Uebersicht)
├── SKILL.md                           ← verbindliche Spec (vom Agent geladen)
├── m365_copilot_protokoll_prompt.md   ← Alternativ-Prompt fuer skill-m365-copilot-chat
└── scripts/
    └── recordings.py                  ← list-recent | fetch | suggest-page
```

## CLI-Kommandos

Vom Repo-Root ausfuehren:

```bash
# Letzte 5 Eintraege (Recordings + Audios) als Markdown-Tabelle:
python .agents/skills/skill-protokoll-confluence/scripts/recordings.py list-recent --limit 5

# Transkript + Screenshots in userdata/sessions/{YYYYMMDD_HHMM}_{slug}/ ablegen:
python .agents/skills/skill-protokoll-confluence/scripts/recordings.py fetch <item-id>

# Zugehoerige Confluence-Seite auflösen (Regel-Match + Kalender-Lookup):
python .agents/skills/skill-protokoll-confluence/scripts/recordings.py suggest-page <item-id>
```

`<item-id>` ist bei Recordings die Graph-Item-ID, bei Audios der Dateiname (`meeting_YYYYMMDD_HHMM-HHMM.md`).

### Output von `fetch`

```
userdata/sessions/{YYYYMMDD_HHMM}_{slug}/
├── transcript.vtt       (Recording, mit <v Speaker>-Tags)
│   oder transcript.md   (Audio, ohne Sprecher)
├── meta.json            (itemId, startedAt, calendarSubject, screenshots[])
└── screenshots/         (zeitlich gefilterte Bilder aus Desktop/Screenshots/)
```

## Sammlerseiten (parent_id) und Namenskonvention

| Termin | parent_id | Space | Titel |
|---|---|---|---|
| VOBES FB-IT-Abstimmung | `754406190` | VOBES | `VOBES FB-IT-Abstimmung YYYY-MM-DD` |
| PO-APO-Prio-Runde | `144309929` | VOBES | `Protokoll PO-APO-Prio-Runde YYYY-MM-DD` |
| Fachthemen-Runde | `282753506` | VOBES | `Protokoll Fachthemen-Runde YYYY-MM-DD` |
| Workshopreihe Sys-Designer | `212452410` | VOBES | `WS YYYY-MM-DD` |
| Workshop Easy-Migration-Selfservice | `6698589657` | VOBES | `Workshop Easy-Migration-Selfservice YYYY-MM-DD` |
| KC Vibe Coding | `6932124640` | EKEK1 | `KC Vibe Coding - YYYY-MM-DD` |
| Planung 2026 | `5127115694` | VOBES | *Sonderfall — kein datumsbasiertes Protokoll* |

Identische Tabelle ist in `RULES` in `recordings.py` hinterlegt.

## Voraussetzungen

- **Confluence-Push**: MCP-Server `mcp-atlassian` verfuegbar.
- **Recordings (VTT mit Sprechern)**: Teams-Token-Cache `userdata/tmp/.graph_token_cache_teams.json` (Scopes `Calendars.Read`, `Files.ReadWrite.All`). SharePoint-Token wird automatisch via Refresh-Token aus dem Teams-LocalStorage gezogen.
- **Audio + Screenshots**: OneDrive-Sync der Ordner `Dokumente/Audioaufzeichnungen/` und `Desktop/Screenshots/` — kein Token noetig.
- **Kalender-Subject-Lookup** (Audio-Fallback): Graph-Token. Ohne Token Fallback auf Filename-Stem.

## Verwandte Skills

- [`$skill-orga-ekek1`](../skill-orga-ekek1/) — Personen, Rollen, Regeltermine (Voraussetzung)
- [`$skill-important-pages-links-and-urls`](../skill-important-pages-links-and-urls/) — Standard-Links (Voraussetzung)
- [`$skill-update-confluence-page`](../skill-update-confluence-page/) — Diff-Review-Workflow fuer Updates
- [`$skill-m365-copilot-chat`](../skill-m365-copilot-chat/) — Alternative ueber `m365_copilot_protokoll_prompt.md`

## Bekannte Stolperfallen

- **VTT ohne Sprecher**: Wenn `grep '<v ' transcript.vtt` leer bleibt, wurde der "edited"-Endpoint genutzt. Loesung: erneut mit `applymediaedits=false` ziehen → siehe [`docs/teams-transkription-mit-sprechern.md`](../../../docs/teams-transkription-mit-sprechern.md).
- **Lokale `.mp4` aus OneDrive-Sync**: Enthaelt **kein** VTT-Sidecar (per `ffprobe` verifiziert). Recordings muessen ueber SharePoint-REST geladen werden.
- **Fremd-organisiertes Meeting**: Recording liegt nicht im eigenen `/Recordings/`-Ordner. Discovery via Outlook-Collab-API → siehe Knowledge-Doc.
- **Wiki-Markup vs. Storage-Format**: Bei Tasks/`<ac:>`-Makros immer `content_format="storage"`, sonst rendern die Tags als Klartext.
- **Markdown-Konvertierung**: `convert_to_markdown=true` zerstoert `<ac:>`-Makros — beim Update IMMER `convert_to_markdown=false`.
