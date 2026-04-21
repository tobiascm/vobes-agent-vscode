# Teams-Transkription mit Sprechern — was geht, was nicht

Stand: 2026-04-21. Quelle: Reverse-Engineering der Teams-Web-UI per Playwright (Network-Capture beim "Als VTT herunterladen"-Klick) und Tests gegen Graph + Outlook-Collab + SharePoint-REST.

Implementierung: `.agents/skills/skill-protokoll-confluence/scripts/recordings.py::_download_recording`.

## TL;DR

- **Sprecher (`<v Name>`-Tags) im VTT bekommen**: nur `streamContent?is=1&applymediaedits=false` mit **SharePoint**-Token.
- **Alle anderen Pfade** (`temporaryDownloadUrl`, `/content`, OneDrive-Sync der `.mp4`) liefern entweder das "edited" VTT ohne Sprecher oder gar kein VTT.
- **Graph `onlineMeetings/{id}/transcripts/{id}/metadataContent`** waere das saubere JSON mit `speakerName` — aber der Teams-Web-Client (App-ID `5e3ce6c0-2b1f-4285-8d4b-75ee78787346`) ist fuer den noetigen Scope `OnlineMeetingTranscript.Read.All` **nicht preautorisiert** (AADSTS65002). Eigene App-Registrierung waere noetig.
- **Fremd-organisierte Meetings** (Recording liegt nicht im eigenen `/Recordings/`-Ordner): ueber Outlook-Calendar `iCalUId` → Outlook-Collab-API → `TranscriptV2.location` → dann wieder `streamContent?...&applymediaedits=false`.
- **Lokale `.mp4`-Datei aus OneDrive-Sync**: enthaelt **kein** VTT-Sidecar, nur den Video-Stream (per `ffprobe` verifiziert). Diarization waere nur ueber lokale Audio-Pipeline moeglich.

## Was geht

### Eigenes Recording → VTT mit Sprechern

```
GET https://volkswagengroup-my.sharepoint.com/_api/v2.1/drives/{drive}/items/{item}/media/transcripts/{tr}/streamContent?is=1&applymediaedits=false
Authorization: Bearer <SP-Token, Scope: volkswagengroup-my.sharepoint.com/.default>
```

- Liefert WebVTT mit `<v Name>`-Voice-Tags pro Cue.
- `applymediaedits=false` ist Pflicht. Default (`true`) liefert die "edited" Variante ohne Sprecher.
- Drive- und Item-ID stammen aus dem Graph-Listing `/me/drive/root:/Recordings:/children`.
- Transcript-ID aus `/media/transcripts` (JSON-Liste, erstes Element).
- SP-Token wird per Refresh-Token-Flow aus dem Teams-Web-Client gegen `volkswagengroup-my.sharepoint.com/.default` gezogen (siehe `recordings.py::sp_token`).

### Fremd-organisiertes Meeting → Drive/Item discovern

Wenn das Recording nicht im eigenen `/Recordings/`-Ordner liegt (Organisator war jemand anderes), reicht das Graph-Listing nicht. Fallback:

1. Graph `/me/calendarView` → `iCalUId` des Termins.
2. Outlook-Collab-Endpoint:
   ```
   GET https://outlook.office.com/Collab/v1/smtp:{mail}/collabs?collab_id=2SMTP:{mail}externalentitykey:{iCalUid}&response_data_filter.include_resource_types=transcript|Recording|TranscriptV2
   Authorization: Bearer <Outlook-Token, Scope: outlook.office.com/.default>
   X-AnchorMailbox: {mail}
   Prefer: IdType="ImmutableId"
   ```
3. Antwort enthaelt `resources[]` mit `TranscriptV2.location` → daraus Drive-ID, Item-ID, Transcript-ID extrahieren.
4. Mit diesen IDs wieder `streamContent?is=1&applymediaedits=false` (SP-Token, wie oben).

Der `Collab-Internal.ReadWrite`-Scope ist im Default-Scope der Outlook-Audience enthalten, deshalb funktioniert dieser Pfad ohne separate App-Registrierung.

## Was nicht geht

| Endpoint / Quelle | Ergebnis | Warum |
|---|---|---|
| `temporaryDownloadUrl` aus dem `/media/transcripts`-Listing | VTT ohne Sprecher | Liefert die "edited" Variante. |
| `/media/transcripts/{tr}/content` | VTT ohne Sprecher | Gleiche edited Variante. |
| Graph `onlineMeetings/{id}/transcripts/{id}/metadataContent` | 401/403 (AADSTS65002) | Braucht `OnlineMeetingTranscript.Read.All` — Teams-Web-Client App-ID ist dafuer nicht preautorisiert. Liefert *theoretisch* JSON mit `speakerName` pro Segment. |
| Lokale `.mp4` aus OneDrive-Sync (`~/OneDrive - Volkswagen AG/Recordings/`) | Kein VTT vorhanden | OneDrive synct nur den Video-Stream, nicht die Transkript-Sidecars. Per `ffprobe` verifiziert. |
| Manuell aufgenommene Audios (`Dokumente/Audioaufzeichnungen/meeting_*.md`) | Text vorhanden, keine Sprecher | Kommt aus dem Windows-Voice-Recorder, der keine Diarization liefert. |

## Optionen, falls Sprecher fehlen

Stand der Recherche (ChatGPT, 2026-04-21, Datei `tmp/20260421_chatgpt_teams-speaker-diarization.md` — Antwort wurde abgeschnitten):

- **Eigene Azure App-Registrierung** mit `OnlineMeetingTranscript.Read.All` und `metadataContent`-Endpoint nutzen. Saubere Loesung, aber Tenant-Admin-Consent noetig.
- **Lokale Diarization** ueber `pyannote.audio` (3.x) oder `whisperx` auf der `.mp4` (Audio-Spur extrahieren). Erfordert HuggingFace-Token fuer pyannote-Modelle und CPU/GPU-Zeit. Qualitaet auf deutschen Business-Meetings mit 3-10 Sprechern: laut Benchmarks DER ~10-15% — brauchbar fuer Zuordnung, nicht perfekt.
- **Azure Speech Service** — Realtime/Batch-Diarization-Endpoint, kostenpflichtig.

Wenn das Thema konkret wird: vollstaendige ChatGPT-Recherche neu fahren (`skill-chatgpt-research`), die abgespeicherte Antwort enthaelt nur die ersten Zeilen.

## Quick-Check: hat mein VTT Sprecher?

```bash
grep -m1 '<v ' userdata/sessions/{slug}/transcript.vtt
```

- Treffer → Sprecher sind drin (`<v Name>Text</v>`).
- Kein Treffer → entweder via "edited"-Endpoint geladen (dann erneut mit `applymediaedits=false` ziehen) oder Audio-Quelle ohne Diarization (dann lokale Pipeline noetig).
