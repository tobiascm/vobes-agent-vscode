"""Teams-Recordings und Audioaufzeichnungen aus OneDrive listen und Transkripte laden.

Subcommands:
  list-recent [--limit N]     Recordings + Audioaufzeichnungen zusammengefuehrt (neueste zuerst).
  fetch <item-id>             Transkript nach userdata/sessions/{YYYYMMDD_HHMM}_{slug}/ laden.
  suggest-page <item-id>      Regel-Match + Kalender-Lookup -> Ziel-Confluence-Seite (JSON).
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parents[4]
TOKEN_SKILL = REPO_ROOT / ".agents" / "skills" / "skill-m365-copilot-mail-search" / "scripts"
sys.path.insert(0, str(TOKEN_SKILL))
import m365_mail_search_token as mst  # noqa: E402

GRAPH = "https://graph.microsoft.com/v1.0"
SP_HOST = "volkswagengroup-my.sharepoint.com"
GRAPH_TOKEN_CACHE = REPO_ROOT / "userdata" / "tmp" / ".graph_token_cache_teams.json"
SESSIONS_DIR = REPO_ROOT / "userdata" / "sessions"
RECORDINGS_PATH = "Recordings"
AUDIO_DIR = Path.home() / "OneDrive - Volkswagen AG" / "Dokumente" / "Audioaufzeichnungen"

RULES = [
    ("KC Vibe Coding",                      "6932124640", "EKEK1", "KC Vibe Coding - {date}"),
    ("Easy-Migration-Selfservice",          "6698589657", "VOBES", "Workshop Easy-Migration-Selfservice {date}"),
    ("PO-APO",                              "144309929",  "VOBES", "Protokoll PO-APO-Prio-Runde {date}"),
    ("Fachthemen",                          "282753506",  "VOBES", "Protokoll Fachthemen-Runde {date}"),
    ("FB-IT-Abstimmung",                    "754406190",  "VOBES", "VOBES FB-IT-Abstimmung {date}"),
]

REC_RE = re.compile(r"^(?P<prefix>.+?)-(?P<date>\d{8})_(?P<time>\d{6})-Besprechungstranskript\.mp4$")
AUDIO_RE = re.compile(r"^meeting_(?P<date>\d{8})_(?P<start>\d{4})-(?P<end>\d{4})\.md$")
SCREENSHOT_DIR = Path.home() / "OneDrive - Volkswagen AG" / "Desktop" / "Screenshots"
SCREENSHOT_RE = re.compile(r"^(?P<d>\d{4}-\d{2}-\d{2}) (?P<t>\d{2}_\d{2}_\d{2})-(?P<title>.+)\.(?P<ext>png|jpg|jpeg)$", re.I)
VTT_CUE_RE = re.compile(r"(\d{2}:)?\d{2}:\d{2}\.\d{3}\s*-->\s*(\d{2}:)?\d{2}:\d{2}\.\d{3}")


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


def graph_token() -> str:
    raw = GRAPH_TOKEN_CACHE.read_text("utf-8")
    if raw.startswith('"'):
        raw = json.loads(raw)
    return json.loads(raw)["token"]


def sp_token() -> str:
    records = mst._collect_token_records()
    rt = mst._best_refresh_token(records)
    if rt is None:
        raise RuntimeError("Kein RefreshToken im Teams-LocalStorage gefunden.")
    tenant = mst._tenant_id(records)
    r = requests.post(
        f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
        data={"client_id": mst.CLIENT_ID, "grant_type": "refresh_token",
              "refresh_token": rt.secret, "scope": f"https://{SP_HOST}/.default"},
        headers={"Origin": "https://teams.microsoft.com"}, timeout=20,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def _parse_dt(date_s: str, time_s: str) -> datetime:
    if len(time_s) == 4:
        time_s += "00"
    return datetime.strptime(date_s + time_s, "%Y%m%d%H%M%S")


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
        source="audio", item_id=p.name, name=p.name,
        started_at=_parse_dt(m["date"], m["start"]),
        ended_at=_parse_dt(m["date"], m["end"]),
        web_url=p.as_uri(), ext="md",
    )


def _list_folder(hdr: dict[str, str], path: str) -> list[dict]:
    url = (f"{GRAPH}/me/drive/root:/{path}:/children"
           "?$top=100&$orderby=lastModifiedDateTime desc"
           "&$select=id,name,webUrl,createdDateTime,lastModifiedDateTime")
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
                if (parsed := _parse_recording(raw)):
                    items.append(parsed)
        except Exception as exc:
            print(f"# warn: Recordings-Listing fehlgeschlagen ({exc}) — nur lokale Audios.", file=sys.stderr)
    items.sort(key=lambda x: x.started_at or datetime.min, reverse=True)
    return items


def _find(item_id: str) -> Item:
    if AUDIO_RE.match(item_id):
        p = AUDIO_DIR / item_id
        if p.is_file() and (it := _parse_audio_local(p)):
            return it
    hdr = {"Authorization": f"Bearer {graph_token()}"}
    for raw in _list_folder(hdr, RECORDINGS_PATH):
        if (it := _parse_recording(raw)) and it.item_id == item_id:
            return it
    raise ValueError(f"Item {item_id} nicht gefunden in Recordings/Audioaufzeichnungen.")


def _slug(text: str) -> str:
    return (re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "unbenannt")[:60]


def _drive_id(hdr: dict[str, str]) -> str:
    r = requests.get(f"{GRAPH}/me/drive", headers=hdr, timeout=20)
    r.raise_for_status()
    return r.json()["id"]


def _lookup_subject(hdr: dict[str, str], it: Item) -> str | None:
    if it.started_at is None or it.ended_at is None:
        return None
    params = {
        "startDateTime": it.started_at.strftime("%Y-%m-%dT%H:%M:%S"),
        "endDateTime": (it.ended_at + timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%S"),
        "$select": "subject,start", "$top": "10",
    }
    extra = {**hdr, "Prefer": 'outlook.timezone="Europe/Berlin"'}
    r = requests.get(f"{GRAPH}/me/calendarView", headers=extra, params=params, timeout=30)
    if r.status_code >= 400:
        return None
    events = r.json().get("value", [])
    if not events:
        return None
    events.sort(key=lambda e: abs(datetime.fromisoformat(e["start"]["dateTime"][:19]) - it.started_at))
    return events[0].get("subject")


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
    hdr_sp = {"Authorization": f"Bearer {sp_token()}", "Accept": "application/json"}
    drive = _drive_id(hdr)
    r = requests.get(
        f"https://{SP_HOST}/_api/v2.1/drives/{drive}/items/{it.item_id}/media/transcripts",
        headers=hdr_sp, timeout=30,
    )
    r.raise_for_status()
    entries = r.json().get("value", [])
    if not entries:
        raise RuntimeError(f"Kein Transkript fuer {it.name} verfuegbar.")
    dr = requests.get(entries[0]["temporaryDownloadUrl"], timeout=60)
    dr.raise_for_status()
    dst = out / "transcript.vtt"
    dst.write_bytes(dr.content)
    return dst


def _download_audio(it: Item, out: Path) -> Path:
    dst = out / f"transcript.{it.ext}"
    shutil.copy2(AUDIO_DIR / it.name, dst)
    return dst


def cmd_list_recent(limit: int) -> int:
    try:
        hdr: dict[str, str] | None = {"Authorization": f"Bearer {graph_token()}"}
    except Exception as exc:
        print(f"# warn: kein Graph-Token ({exc}) — nur lokale Audios.", file=sys.stderr)
        hdr = None
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
    subject = None
    if it.source == "audio":
        try:
            subject = _lookup_subject({"Authorization": f"Bearer {graph_token()}"}, it)
        except Exception:
            subject = None
    hint = subject or (it.rule[0] if it.rule else Path(it.name).stem)
    out = SESSIONS_DIR / f"{it.slug_date}_{_slug(hint)}"
    out.mkdir(parents=True, exist_ok=True)
    if it.source == "recording":
        hdr = {"Authorization": f"Bearer {graph_token()}"}
        transcript = _download_recording(it, hdr, out)
    else:
        transcript = _download_audio(it, out)
    if it.source == "audio" and subject:
        it.rule = _match_rule(subject)
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
                shots_meta.append({
                    "filename": s["path"].name,
                    "takenAt": s["taken_at"].isoformat(),
                    "offsetSeconds": int((s["taken_at"] - start).total_seconds()),
                    "title": s["title"],
                })
    meta = {
        "source": it.source,
        "itemId": it.item_id,
        "name": it.name,
        "startedAt": it.started_at.isoformat() if it.started_at else None,
        "endedAt": it.ended_at.isoformat() if it.ended_at else None,
        "webUrl": it.web_url,
        "rule": it.rule[0] if it.rule else None,
        "calendarSubject": subject,
        "screenshots": shots_meta,
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"transcript": str(transcript), "meta": str(out / "meta.json"),
                      "screenshots": len(shots_meta)},
                     indent=2, ensure_ascii=False))
    return 0


def cmd_suggest_page(item_id: str) -> int:
    it = _find(item_id)
    subject = None
    if it.source == "audio":
        try:
            subject = _lookup_subject({"Authorization": f"Bearer {graph_token()}"}, it)
        except Exception:
            subject = None
    if it.source == "audio" and subject and not it.rule:
        it.rule = _match_rule(subject)
    date_str = it.started_at.strftime("%Y-%m-%d") if it.started_at else ""
    if it.rule:
        out = {
            "matched": True,
            "source": it.source,
            "title": it.rule[3].format(date=date_str),
            "parent_id": it.rule[1],
            "space": it.rule[2],
            "calendarSubject": subject,
        }
    else:
        out = {
            "matched": False,
            "source": it.source,
            "calendarSubject": subject,
            "fallback": "userdata/sessions/",
        }
    print(json.dumps(out, indent=2, ensure_ascii=False))
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
    args = p.parse_args()
    if args.cmd == "list-recent":
        return cmd_list_recent(args.limit)
    if args.cmd == "fetch":
        return cmd_fetch(args.item_id)
    if args.cmd == "suggest-page":
        return cmd_suggest_page(args.item_id)
    return 2


if __name__ == "__main__":
    sys.exit(main())
