"""Teams-Recordings und Audioaufzeichnungen listen, transkribieren und tracken.

Subcommands:
  list-recent [--limit N]            Recordings + Audioaufzeichnungen (neueste zuerst)
  fetch <item-id>                    Transkript nach userdata/sessions/{YYYYMMDD_HHMM}_{slug}/ laden
  suggest-page <item-id>             Regel-Match + Kalender-Lookup -> Ziel-Confluence-Seite (JSON)
  sync-register                      Register userdata/transcriptions/transcriptions.csv aktualisieren
  materialize-transcript <id>        Master-Markdown in userdata/transcriptions/transcripts schreiben
  list-open [--limit N]              Offene Transkriptionen (ohne integrated_targets) aus dem Register
  next-open                          Naechste offene Transkription als JSON
  mark-integrated <id> --target TXT  Zielort in integrated_targets hinterlegen (mehrfach moeglich)
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

REPO_ROOT = Path(__file__).resolve().parents[4]
TOKEN_SKILL = REPO_ROOT / ".agents" / "skills" / "skill-m365-copilot-mail-search" / "scripts"
sys.path.insert(0, str(TOKEN_SKILL))
import m365_mail_search_token as mst  # noqa: E402

GRAPH = "https://graph.microsoft.com/v1.0"
SP_HOST = "volkswagengroup-my.sharepoint.com"
GRAPH_TOKEN_CACHE = REPO_ROOT / "userdata" / "tmp" / ".graph_token_cache_teams.json"
SESSIONS_DIR = REPO_ROOT / "userdata" / "sessions"
TRANSCRIPTIONS_DIR = REPO_ROOT / "userdata" / "transcriptions"
TRANSCRIPTS_DIR = TRANSCRIPTIONS_DIR / "transcripts"
REGISTRY_CSV = TRANSCRIPTIONS_DIR / "transcriptions.csv"
TMP_DIR = TRANSCRIPTIONS_DIR / ".tmp"

RECORDINGS_PATH = "Recordings"
AUDIO_DIR = Path.home() / "OneDrive - Volkswagen AG" / "Dokumente" / "Audioaufzeichnungen"

CSV_FIELDS = [
    "transcription_id",
    "meeting_at",
    "meeting_title",
    "source_type",
    "source_item_id",
    "source_location",
    "transcript_md_path",
    "integrated_targets",
    "suggested_title",
    "last_action_at",
    "notes",
]

RULES = [
    ("KC Vibe Coding", "6932124640", "EKEK1", "KC Vibe Coding - {date}"),
    ("Easy-Migration-Selfservice", "6698589657", "VOBES", "Workshop Easy-Migration-Selfservice {date}"),
    ("PO-APO", "144309929", "VOBES", "Protokoll PO-APO-Prio-Runde {date}"),
    ("Fachthemen", "282753506", "VOBES", "Protokoll Fachthemen-Runde {date}"),
    ("FB-IT-Abstimmung", "754406190", "VOBES", "VOBES FB-IT-Abstimmung {date}"),
    ("Übergreifendes techn. Refinement", "6612851628", "VOBES", "{date} Protokoll Übergr. techn. Refinement"),
]

REC_RE = re.compile(r"^(?P<prefix>.+?)-(?P<date>\d{8})_(?P<time>\d{6})-Besprechungstranskript\.mp4$")
AUDIO_RE = re.compile(r"^meeting_(?P<date>\d{8})_(?P<start>\d{4})-(?P<end>\d{4})\.md$")
SCREENSHOT_DIR = Path.home() / "OneDrive - Volkswagen AG" / "Desktop" / "Screenshots"
SCREENSHOT_RE = re.compile(r"^(?P<d>\d{4}-\d{2}-\d{2}) (?P<t>\d{2}_\d{2}_\d{2})-(?P<title>.+)\.(?P<ext>png|jpg|jpeg)$", re.I)
VTT_CUE_RE = re.compile(r"(\d{2}:)?\d{2}:\d{2}\.\d{3}\s*-->\s*(\d{2}:)?\d{2}:\d{2}\.\d{3}")
INVALID_FILENAME_RE = re.compile(r"[<>:\"/\\|?*\x00-\x1F]")
VOICE_TAG_RE = re.compile(r"<v\s+([^>]+)>(.*)</v>")
HTML_TAG_RE = re.compile(r"</?[^>]+>")
BERLIN_TZ = ZoneInfo("Europe/Berlin")


@dataclass
class Item:
    source: str
    item_id: str
    name: str
    started_at: datetime | None
    ended_at: datetime | None
    web_url: str
    ext: str
    rule: tuple[str, str, str, str] | None = None

    @property
    def slug_date(self) -> str:
        return self.started_at.strftime("%Y%m%d_%H%M") if self.started_at else "unknown"


@dataclass
class CalendarMatch:
    subject: str
    categories: list[str]
    start: datetime | None

    @property
    def has_category(self) -> bool:
        return bool(self.categories)


def graph_token() -> str:
    raw = GRAPH_TOKEN_CACHE.read_text("utf-8")
    if raw.startswith('"'):
        raw = json.loads(raw)
    return json.loads(raw)["token"]


def graph_headers(required_scopes: tuple[str, ...], force_refresh: bool = False) -> dict[str, str] | None:
    try:
        token, _exp, _source = mst.fetch_graph_token(
            required_scopes=required_scopes,
            open_teams_if_needed=False,
            force_refresh=force_refresh,
        )
        return {"Authorization": f"Bearer {token}"}
    except Exception:  # noqa: BLE001
        try:
            return {"Authorization": f"Bearer {graph_token()}"}
        except Exception:  # noqa: BLE001
            return None


def sp_token() -> str:
    records = mst._collect_token_records()
    rt = mst._best_refresh_token(records)
    if rt is None:
        raise RuntimeError("Kein RefreshToken im Teams-LocalStorage gefunden.")
    tenant = mst._tenant_id(records)
    r = requests.post(
        f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
        data={
            "client_id": mst.CLIENT_ID,
            "grant_type": "refresh_token",
            "refresh_token": rt.secret,
            "scope": f"https://{SP_HOST}/.default",
        },
        headers={"Origin": "https://teams.microsoft.com"},
        timeout=20,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def _now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _parse_dt(date_s: str, time_s: str) -> datetime:
    if len(time_s) == 4:
        time_s += "00"
    return datetime.strptime(date_s + time_s, "%Y%m%d%H%M%S")


def _parse_graph_datetime(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw[:19])
    except ValueError:
        return None


def _iso_berlin(dt: datetime) -> str:
    return dt.replace(tzinfo=BERLIN_TZ).isoformat(timespec="seconds")


def _match_rule(text: str) -> tuple[str, str, str, str] | None:
    low = text.lower()
    for rule in RULES:
        if rule[0].lower() in low:
            return rule
    return None


def _parse_recording(raw: dict) -> Item | None:
    m = REC_RE.match(raw["name"])
    if not m:
        return None
    return Item(
        source="recording",
        item_id=raw["id"],
        name=raw["name"],
        started_at=_parse_dt(m["date"], m["time"]),
        ended_at=None,
        web_url=raw.get("webUrl", ""),
        ext="vtt",
        rule=_match_rule(m["prefix"]),
    )


def _parse_audio_local(p: Path) -> Item | None:
    m = AUDIO_RE.match(p.name)
    if not m:
        return None
    return Item(
        source="audio",
        item_id=p.name,
        name=p.name,
        started_at=_parse_dt(m["date"], m["start"]),
        ended_at=_parse_dt(m["date"], m["end"]),
        web_url=p.as_uri(),
        ext="md",
    )


def _list_folder(hdr: dict[str, str], path: str) -> list[dict]:
    url = (
        f"{GRAPH}/me/drive/root:/{path}:/children"
        "?$top=100&$orderby=lastModifiedDateTime desc"
        "&$select=id,name,webUrl,createdDateTime,lastModifiedDateTime"
    )
    r = requests.get(url, headers=hdr, timeout=30)
    if r.status_code == 404:
        return []
    r.raise_for_status()
    return r.json().get("value", [])


def _list_audio_local() -> list[Item]:
    if not AUDIO_DIR.is_dir():
        return []
    return [it for p in AUDIO_DIR.iterdir() if (it := _parse_audio_local(p))]


def _collect(hdr: dict[str, str] | None) -> list[Item]:
    items: list[Item] = _list_audio_local()
    if hdr is not None:
        try:
            for raw in _list_folder(hdr, RECORDINGS_PATH):
                if parsed := _parse_recording(raw):
                    items.append(parsed)
        except Exception as exc:  # noqa: BLE001
            print(f"# warn: Recordings-Listing fehlgeschlagen ({exc}) — nur lokale Audios.", file=sys.stderr)
    items.sort(key=lambda x: x.started_at or datetime.min, reverse=True)
    return items


def _find(item_id: str) -> Item:
    if AUDIO_RE.match(item_id):
        p = AUDIO_DIR / item_id
        if p.is_file() and (it := _parse_audio_local(p)):
            return it
    hdr = graph_headers(("Files.ReadWrite.All",))
    if hdr is None:
        raise ValueError("Kein gueltiger Graph-Token fuer Recordings vorhanden.")
    for raw in _list_folder(hdr, RECORDINGS_PATH):
        if (it := _parse_recording(raw)) and it.item_id == item_id:
            return it
    raise ValueError(f"Item {item_id} nicht gefunden in Recordings/Audioaufzeichnungen.")


def _slug(text: str) -> str:
    return (re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "unbenannt")[:60]


def _sanitize_filename_title(text: str) -> str:
    cleaned = INVALID_FILENAME_RE.sub(" ", text).strip().strip(".")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned or "Unbenannt"


def _extract_recording_title(filename: str) -> str:
    m = REC_RE.match(filename)
    if m:
        return m["prefix"].strip()
    stem = Path(filename).stem
    stem = stem.replace("-Besprechungstranskript", "").strip()
    return stem or "Unbenannt"


def _drive_id(hdr: dict[str, str]) -> str:
    r = requests.get(f"{GRAPH}/me/drive", headers=hdr, timeout=20)
    r.raise_for_status()
    return r.json()["id"]


def _lookup_calendar_event(hdr: dict[str, str], it: Item) -> CalendarMatch | None:
    if it.started_at is None:
        return None
    start = it.started_at - timedelta(minutes=20)
    if it.source == "audio":
        end = (it.ended_at or it.started_at) + timedelta(minutes=20)
        target_end = it.ended_at or (it.started_at + timedelta(hours=1))
    else:
        end = (it.started_at or start) + timedelta(hours=4)
        target_end = it.started_at + timedelta(hours=4)
    params = {
        "startDateTime": _iso_berlin(start),
        "endDateTime": _iso_berlin(end),
        "$select": "subject,start,end,categories",
        "$top": "25",
    }
    extra = {**hdr, "Prefer": 'outlook.timezone="Europe/Berlin"'}
    r = requests.get(f"{GRAPH}/me/calendarView", headers=extra, params=params, timeout=30)
    if r.status_code >= 400:
        return None
    events = r.json().get("value", [])
    if not events:
        return None

    lunch_re = re.compile(r"\b(mittag|mittagessen|lunch)\b", re.IGNORECASE)

    def _sort_key(event: dict) -> tuple[int, int, int, int, float, float]:
        subject = (event.get("subject") or "").strip()
        categories = event.get("categories") or []
        category_penalty = 0 if categories else 1
        ev_start = _parse_graph_datetime((event.get("start") or {}).get("dateTime"))
        ev_end = _parse_graph_datetime((event.get("end") or {}).get("dateTime"))
        if ev_start is None or ev_end is None:
            return (1, 1, 1, 1, 999999999.0, 999999999.0)
        overlap = max(0.0, (min(target_end, ev_end) - max(it.started_at, ev_start)).total_seconds())
        overlap_penalty = 0 if overlap > 0 else 1
        duration = max(0.0, (ev_end - ev_start).total_seconds())
        all_day_penalty = 1 if duration >= 23 * 3600 else 0
        lunch_penalty = 1 if lunch_re.search(subject) else 0
        delta = abs((ev_start - it.started_at).total_seconds())
        return lunch_penalty, all_day_penalty, overlap_penalty, category_penalty, -overlap, delta

    best = sorted(events, key=_sort_key)[0]
    return CalendarMatch(
        subject=(best.get("subject") or "").strip(),
        categories=[str(x) for x in (best.get("categories") or [])],
        start=_parse_graph_datetime((best.get("start") or {}).get("dateTime")),
    )


def _meeting_title_for_item(it: Item, event: CalendarMatch | None) -> str:
    if it.source == "recording":
        return _extract_recording_title(it.name)
    if event and event.subject:
        return event.subject
    return Path(it.name).stem


def _resolve_rule(it: Item, title: str, event: CalendarMatch | None) -> tuple[str, str, str, str] | None:
    candidates = []
    if event and event.subject:
        candidates.append(event.subject)
    candidates.extend([title, it.name])
    for text in candidates:
        if rule := _match_rule(text):
            return rule
    return it.rule


def _vtt_end(vtt: Path) -> timedelta | None:
    last = None
    for m in VTT_CUE_RE.finditer(vtt.read_text("utf-8", errors="ignore")):
        last = m.group(0)
    if not last:
        return None
    t = last.split("-->")[1].strip()
    parts = t.split(":")
    h, mi, s = (0, *parts) if len(parts) == 2 else parts
    return timedelta(hours=int(h), minutes=int(mi), seconds=float(s))


def _collect_screenshots(start: datetime, end: datetime) -> list[dict]:
    if not SCREENSHOT_DIR.is_dir():
        return []
    shots: list[dict] = []
    for p in SCREENSHOT_DIR.iterdir():
        if not p.is_file() or p.suffix.lower() not in (".png", ".jpg", ".jpeg"):
            continue
        m = SCREENSHOT_RE.match(p.name)
        if m:
            taken = datetime.strptime(f"{m['d']} {m['t'].replace('_', ':')}", "%Y-%m-%d %H:%M:%S")
            title = m["title"]
        else:
            taken = datetime.fromtimestamp(p.stat().st_mtime)
            title = p.stem
        if start <= taken <= end:
            shots.append({"path": p, "taken_at": taken, "title": title})
    shots.sort(key=lambda s: s["taken_at"])
    return shots


def _download_recording(it: Item, hdr: dict[str, str], out: Path) -> Path:
    tok = sp_token()
    drive = _drive_id(hdr)
    r = requests.get(
        f"https://{SP_HOST}/_api/v2.1/drives/{drive}/items/{it.item_id}/media/transcripts",
        headers={"Authorization": f"Bearer {tok}", "Accept": "application/json"},
        timeout=30,
    )
    r.raise_for_status()
    entries = r.json().get("value", [])
    if not entries:
        raise RuntimeError(f"Kein Transkript fuer {it.name} verfuegbar.")
    tr_id = entries[0]["id"]
    # applymediaedits=false ist Pflicht: nur so kommen <v Speaker>-Tags.
    url = (
        f"https://{SP_HOST}/_api/v2.1/drives/{drive}/items/{it.item_id}"
        f"/media/transcripts/{tr_id}/streamContent?is=1&applymediaedits=false"
    )
    dr = requests.get(url, headers={"Authorization": f"Bearer {tok}"}, timeout=60)
    dr.raise_for_status()
    dst = out / "transcript.vtt"
    dst.write_bytes(dr.content)
    return dst


def _download_audio(it: Item, out: Path) -> Path:
    dst = out / f"transcript.{it.ext}"
    shutil.copy2(AUDIO_DIR / it.name, dst)
    return dst


def _vtt_to_markdown(vtt_text: str) -> str:
    lines: list[str] = []
    for raw in vtt_text.splitlines():
        line = raw.strip()
        if not line or line == "WEBVTT" or "-->" in line or line.isdigit():
            continue
        match = VOICE_TAG_RE.fullmatch(line)
        if match:
            speaker = match.group(1).strip()
            text = HTML_TAG_RE.sub("", match.group(2)).strip()
            if text:
                lines.append(f"- **{speaker}:** {text}")
            continue
        text = HTML_TAG_RE.sub("", line).strip()
        if text:
            lines.append(f"- {text}")
    return "\n".join(lines).strip()


def _ensure_registry_dirs() -> None:
    TRANSCRIPTIONS_DIR.mkdir(parents=True, exist_ok=True)
    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    TMP_DIR.mkdir(parents=True, exist_ok=True)


def _read_registry() -> list[dict[str, str]]:
    if not REGISTRY_CSV.exists():
        return []
    with REGISTRY_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        rows: list[dict[str, str]] = []
        for row in reader:
            cleaned = {k: (row.get(k) or "") for k in CSV_FIELDS}
            rows.append(cleaned)
        return rows


def _write_registry(rows: list[dict[str, str]]) -> None:
    _ensure_registry_dirs()
    with REGISTRY_CSV.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=CSV_FIELDS,
            delimiter=";",
            quoting=csv.QUOTE_MINIMAL,
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in CSV_FIELDS})


def _transcription_id(it: Item) -> str:
    stamp = it.started_at.strftime("%Y%m%d_%H%M") if it.started_at else "unknown"
    short = hashlib.sha1(f"{it.source}:{it.item_id}".encode("utf-8")).hexdigest()[:12]
    return f"tr_{stamp}_{short}"


def _row_sort_key(row: dict[str, str]) -> datetime:
    ts = row.get("meeting_at", "")
    if not ts:
        return datetime.min
    try:
        return datetime.fromisoformat(ts[:19])
    except ValueError:
        return datetime.min


def _find_row(rows: list[dict[str, str]], key: str) -> dict[str, str] | None:
    for row in rows:
        if row.get("transcription_id") == key or row.get("source_item_id") == key:
            return row
    return None


def _render_suggested_title(rule: tuple[str, str, str, str] | None, started_at: datetime | None) -> str:
    if not rule or not started_at:
        return ""
    return rule[3].format(date=started_at.strftime("%Y-%m-%d"))


def _build_row(it: Item, event: CalendarMatch | None) -> dict[str, str]:
    title = _meeting_title_for_item(it, event)
    rule = _resolve_rule(it, title, event)
    notes: list[str] = []
    if event and event.has_category:
        notes.append("calendar-category-priority")
    if it.source == "audio" and not event:
        notes.append("calendar-title-missing")
    return {
        "transcription_id": _transcription_id(it),
        "meeting_at": it.started_at.replace(microsecond=0).isoformat() if it.started_at else "",
        "meeting_title": title,
        "source_type": it.source,
        "source_item_id": it.item_id,
        "source_location": it.web_url,
        "transcript_md_path": "",
        "integrated_targets": "",
        "suggested_title": _render_suggested_title(rule, it.started_at),
        "last_action_at": _now_iso(),
        "notes": " | ".join(notes),
    }


def _is_uncertain_audio_title(title: str) -> bool:
    t = (title or "").strip()
    if not t:
        return True
    if t.lower().startswith("meeting_"):
        return True
    if re.search(r"\b(mittag|mittagessen|lunch)\b", t, re.IGNORECASE):
        return True
    return False


def _should_lookup_calendar(existing: dict[str, str] | None, it: Item, refresh_existing: bool) -> bool:
    if existing is None:
        return True
    if refresh_existing:
        return True
    if it.source != "audio":
        return False
    title = existing.get("meeting_title", "")
    notes = existing.get("notes", "")
    return _is_uncertain_audio_title(title) or "calendar-title-missing" in notes


def _update_existing_row(base: dict[str, str], refreshed: dict[str, str]) -> dict[str, str]:
    keep = {
        "transcription_id": base.get("transcription_id", "") or refreshed["transcription_id"],
        "transcript_md_path": base.get("transcript_md_path", ""),
        "integrated_targets": base.get("integrated_targets", ""),
        "notes": base.get("notes", ""),
    }
    out = {**refreshed, **keep}
    if not out["last_action_at"]:
        out["last_action_at"] = _now_iso()
    return out


def _materialize_markdown(it: Item, meeting_title: str) -> tuple[Path, str]:
    _ensure_registry_dirs()
    stamp = it.started_at.strftime("%Y-%m-%d_%H%M") if it.started_at else "unknown"
    safe_title = _sanitize_filename_title(meeting_title)
    filename = f"{stamp}__{it.source}__{safe_title}.md"
    out = TRANSCRIPTS_DIR / filename
    if it.source == "recording":
        hdr = graph_headers(("Files.ReadWrite.All",))
        if hdr is None:
            raise RuntimeError("Kein gueltiger Graph-Token fuer Recordings vorhanden.")
        vtt_path = _download_recording(it, hdr, TMP_DIR)
        body = _vtt_to_markdown(vtt_path.read_text("utf-8", errors="ignore"))
        if body:
            content = body + "\n"
        else:
            content = "_Leeres oder nicht parsebares VTT._\n"
    else:
        src = AUDIO_DIR / it.name
        content = src.read_text("utf-8", errors="ignore")
        if not content.endswith("\n"):
            content += "\n"
    header = [
        f"# {meeting_title}",
        "",
        f"- Quelle: {it.source}",
        f"- Source-ID: {it.item_id}",
        f"- Start: {(it.started_at.replace(microsecond=0).isoformat() if it.started_at else '-')}",
        "",
        "## Transkription",
        "",
    ]
    out.write_text("\n".join(header) + content, encoding="utf-8")
    return out, filename


def cmd_list_recent(limit: int) -> int:
    hdr = graph_headers(("Files.ReadWrite.All",))
    if hdr is None:
        print("# warn: kein Graph-Token (Files.ReadWrite.All) — nur lokale Audios.", file=sys.stderr)
    items = _collect(hdr)[:limit]
    if not items:
        print("Keine Eintraege gefunden.")
        return 0
    print("| Source | Name | Start | Ende | Item-ID | Match | Ziel |")
    print("|---|---|---|---|---|---|---|")
    for it in items:
        start = it.started_at.strftime("%Y-%m-%d %H:%M") if it.started_at else "?"
        end = it.ended_at.strftime("%H:%M") if it.ended_at else "-"
        match = it.rule[0] if it.rule else "(unmatched)"
        if it.rule and it.started_at:
            title = it.rule[3].format(date=it.started_at.strftime("%Y-%m-%d"))
            target = f"{it.rule[2]} / {title}"
        else:
            target = "(userdata/sessions/)"
        print(f"| {it.source} | {it.name} | {start} | {end} | {it.item_id} | {match} | {target} |")
    return 0


def cmd_fetch(item_id: str) -> int:
    it = _find(item_id)
    event = None
    try:
        cal_hdr = graph_headers(("Calendars.Read",))
        if cal_hdr is not None:
            event = _lookup_calendar_event(cal_hdr, it)
    except Exception:  # noqa: BLE001
        event = None
    hint = _meeting_title_for_item(it, event)
    out = SESSIONS_DIR / f"{it.slug_date}_{_slug(hint)}"
    out.mkdir(parents=True, exist_ok=True)
    if it.source == "recording":
        hdr = graph_headers(("Files.ReadWrite.All",))
        if hdr is None:
            raise RuntimeError("Kein gueltiger Graph-Token fuer Recordings vorhanden.")
        transcript = _download_recording(it, hdr, out)
    else:
        transcript = _download_audio(it, out)
    if event and not it.rule:
        it.rule = _match_rule(event.subject)
    start = it.started_at
    if it.source == "recording":
        dur = _vtt_end(transcript) or timedelta(hours=4)
        end = start + dur
    else:
        end = (it.ended_at or start) + timedelta(minutes=1)
    shots_meta: list[dict] = []
    if start:
        shots = _collect_screenshots(start, end)
        if shots:
            sdir = out / "screenshots"
            sdir.mkdir(exist_ok=True)
            for s in shots:
                shutil.copy2(s["path"], sdir / s["path"].name)
                shots_meta.append(
                    {
                        "filename": s["path"].name,
                        "takenAt": s["taken_at"].isoformat(),
                        "offsetSeconds": int((s["taken_at"] - start).total_seconds()),
                        "title": s["title"],
                    }
                )
    meta = {
        "source": it.source,
        "itemId": it.item_id,
        "name": it.name,
        "startedAt": it.started_at.isoformat() if it.started_at else None,
        "endedAt": it.ended_at.isoformat() if it.ended_at else None,
        "webUrl": it.web_url,
        "rule": it.rule[0] if it.rule else None,
        "calendarSubject": event.subject if event else None,
        "calendarCategories": event.categories if event else [],
        "screenshots": shots_meta,
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        json.dumps(
            {"transcript": str(transcript), "meta": str(out / "meta.json"), "screenshots": len(shots_meta)},
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


def cmd_suggest_page(item_id: str) -> int:
    it = _find(item_id)
    event = None
    try:
        cal_hdr = graph_headers(("Calendars.Read",))
        if cal_hdr is not None:
            event = _lookup_calendar_event(cal_hdr, it)
    except Exception:  # noqa: BLE001
        event = None
    title = _meeting_title_for_item(it, event)
    if not it.rule:
        it.rule = _resolve_rule(it, title, event)
    date_str = it.started_at.strftime("%Y-%m-%d") if it.started_at else ""
    if it.rule:
        out = {
            "matched": True,
            "source": it.source,
            "title": it.rule[3].format(date=date_str),
            "parent_id": it.rule[1],
            "space": it.rule[2],
            "meetingTitle": title,
            "calendarSubject": event.subject if event else None,
            "calendarCategories": event.categories if event else [],
        }
    else:
        out = {
            "matched": False,
            "source": it.source,
            "meetingTitle": title,
            "calendarSubject": event.subject if event else None,
            "calendarCategories": event.categories if event else [],
            "fallback": "userdata/sessions/",
        }
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


def cmd_sync_register(refresh_existing_calendar: bool = False) -> int:
    rec_hdr = graph_headers(("Files.ReadWrite.All",))
    cal_hdr = graph_headers(("Calendars.Read",))
    if rec_hdr is None:
        print("# warn: kein Graph-Token (Files.ReadWrite.All) — nur lokale Audios.", file=sys.stderr)
    items = _collect(rec_hdr)
    rows = _read_registry()
    by_source = {row["source_item_id"]: row for row in rows if row.get("source_item_id")}
    created = 0
    updated = 0
    out_rows = rows[:]

    for it in items:
        existing = by_source.get(it.item_id)
        lookup_calendar = cal_hdr is not None and _should_lookup_calendar(existing, it, refresh_existing_calendar)
        event = _lookup_calendar_event(cal_hdr, it) if lookup_calendar else None
        refreshed = _build_row(it, event)
        if existing is None:
            out_rows.append(refreshed)
            created += 1
            by_source[it.item_id] = refreshed
        else:
            merged = _update_existing_row(existing, refreshed)
            # Fast path: bestehende Eintraege ohne Kalender-Refresh nicht ueberschreiben.
            if not lookup_calendar:
                merged["meeting_title"] = existing.get("meeting_title", "") or merged["meeting_title"]
                merged["suggested_title"] = existing.get("suggested_title", "") or merged["suggested_title"]
                merged["notes"] = existing.get("notes", "")
                merged["last_action_at"] = existing.get("last_action_at", "") or merged["last_action_at"]
            idx = out_rows.index(existing)
            out_rows[idx] = merged
            by_source[it.item_id] = merged
            updated += 1

    out_rows.sort(key=_row_sort_key, reverse=True)
    _write_registry(out_rows)
    print(
        json.dumps(
            {
                "registry": str(REGISTRY_CSV),
                "total": len(out_rows),
                "created": created,
                "updated": updated,
                "refresh_existing_calendar": refresh_existing_calendar,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


def cmd_materialize_transcript(key: str) -> int:
    rows = _read_registry()
    row = _find_row(rows, key)
    if row is None:
        raise ValueError(f"Eintrag nicht gefunden: {key}. Erst sync-register ausfuehren.")
    it = _find(row["source_item_id"])
    meeting_title = row.get("meeting_title") or _meeting_title_for_item(it, None)
    out_path, filename = _materialize_markdown(it, meeting_title)
    row["transcript_md_path"] = f"transcripts/{filename}"
    row["last_action_at"] = _now_iso()
    if "materialized" not in row.get("notes", ""):
        row["notes"] = (row.get("notes", "") + (" | " if row.get("notes") else "") + "materialized").strip()
    _write_registry(sorted(rows, key=_row_sort_key, reverse=True))
    print(
        json.dumps(
            {
                "transcription_id": row["transcription_id"],
                "source_item_id": row["source_item_id"],
                "transcript_md_path": row["transcript_md_path"],
                "file": str(out_path),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


def _open_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in rows if not row.get("integrated_targets", "").strip()]


def cmd_list_open(limit: int) -> int:
    rows = sorted(_open_rows(_read_registry()), key=_row_sort_key)
    if not rows:
        print("Keine offenen Transkriptionen.")
        return 0
    print("| transcription_id | meeting_at | meeting_title | source | source_item_id | transcript_md_path |")
    print("|---|---|---|---|---|---|")
    for row in rows[:limit]:
        print(
            f"| {row['transcription_id']} | {row['meeting_at']} | {row['meeting_title']} | "
            f"{row['source_type']} | {row['source_item_id']} | {row['transcript_md_path'] or '(missing)'} |"
        )
    return 0


def cmd_next_open() -> int:
    rows = sorted(_open_rows(_read_registry()), key=_row_sort_key)
    if not rows:
        print(json.dumps({"open": False}, indent=2))
        return 0
    print(json.dumps({"open": True, "item": rows[0]}, indent=2, ensure_ascii=False))
    return 0


def cmd_mark_integrated(key: str, target: str, note: str | None) -> int:
    rows = _read_registry()
    row = _find_row(rows, key)
    if row is None:
        raise ValueError(f"Eintrag nicht gefunden: {key}")
    entries = [x for x in row.get("integrated_targets", "").splitlines() if x.strip()]
    if target not in entries:
        entries.append(target)
    row["integrated_targets"] = "\n".join(entries)
    row["last_action_at"] = _now_iso()
    if note:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        snippet = f"{stamp}: {note}"
        row["notes"] = (row.get("notes", "") + (" | " if row.get("notes") else "") + snippet).strip()
    _write_registry(sorted(rows, key=_row_sort_key, reverse=True))
    print(
        json.dumps(
            {
                "transcription_id": row["transcription_id"],
                "targets": len(entries),
                "integrated_targets": row["integrated_targets"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="OneDrive Recordings & Audioaufzeichnungen")
    sub = p.add_subparsers(dest="cmd", required=True)

    pl = sub.add_parser("list-recent")
    pl.add_argument("--limit", type=int, default=5)

    pf = sub.add_parser("fetch")
    pf.add_argument("item_id")

    ps = sub.add_parser("suggest-page")
    ps.add_argument("item_id")

    sr = sub.add_parser("sync-register")
    sr.add_argument(
        "--refresh-existing-calendar",
        action="store_true",
        help="Kalender auch fuer bestehende Eintraege erneut abgleichen (langsamer).",
    )
    sr.set_defaults(_cmd="sync-register")

    mt = sub.add_parser("materialize-transcript")
    mt.add_argument("key", help="transcription_id oder source_item_id")

    lo = sub.add_parser("list-open")
    lo.add_argument("--limit", type=int, default=20)

    no = sub.add_parser("next-open")
    no.set_defaults(_cmd="next-open")

    mi = sub.add_parser("mark-integrated")
    mi.add_argument("key", help="transcription_id oder source_item_id")
    mi.add_argument("--target", required=True, help="z.B. confluence|url=...|page_id=...")
    mi.add_argument("--note", default=None)

    args = p.parse_args()
    if args.cmd == "list-recent":
        return cmd_list_recent(args.limit)
    if args.cmd == "fetch":
        return cmd_fetch(args.item_id)
    if args.cmd == "suggest-page":
        return cmd_suggest_page(args.item_id)
    if args.cmd == "sync-register":
        return cmd_sync_register(args.refresh_existing_calendar)
    if args.cmd == "materialize-transcript":
        return cmd_materialize_transcript(args.key)
    if args.cmd == "list-open":
        return cmd_list_open(args.limit)
    if args.cmd == "next-open":
        return cmd_next_open()
    if args.cmd == "mark-integrated":
        return cmd_mark_integrated(args.key, args.target, args.note)
    return 2


if __name__ == "__main__":
    sys.exit(main())
