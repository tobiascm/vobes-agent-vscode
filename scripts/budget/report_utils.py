from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence

from tabulate import tabulate


WORKSPACE = Path(__file__).resolve().parent.parent.parent
SESSIONS_DIR = WORKSPACE / "userdata" / "sessions"


def slug(value: str | None) -> str:
    text = (value or "").strip().lower()
    out = []
    for ch in text:
        out.append(ch if ch.isalnum() or ch in {"_", "-"} else "_")
    s = "".join(out)
    while "__" in s:
        s = s.replace("__", "_")
    return (s.strip("_") or "report")[:48]


def report_path(prefix: str, label: str | None = None, output: str | None = None) -> Path:
    if output:
        path = Path(output)
    else:
        name = f"{datetime.now():%Y%m%d}_{slug(prefix)}"
        if label:
            name += f"_{slug(label)}"
        path = SESSIONS_DIR / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def table_md(rows: Iterable[Sequence[object]], headers: Sequence[str]) -> str:
    rows = list(rows)
    if not rows:
        return "> Keine Ergebnisse gefunden.\n"
    return tabulate(rows, headers=headers, tablefmt="pipe") + "\n"


def section(title: str, body: str) -> str:
    return f"## {title}\n\n{body.rstrip()}\n"


def note(text: str) -> str:
    return f"> {text}\n"


def warning(text: str) -> str:
    return f"> **WARNUNG:** {text}\n"


def sync_info(db_path: Path, table: str) -> str:
    """Return a markdown line showing the sync timestamp for *table*."""
    import sqlite3 as _sql

    try:
        with _sql.connect(db_path) as conn:
            conn.row_factory = _sql.Row
            row = conn.execute(
                "SELECT synced_at FROM _sync_meta WHERE table_name = ?", (table,)
            ).fetchone()
        if row:
            return f"- Datenstand `{table}`: {row['synced_at']}"
    except Exception:
        pass
    return f"- Datenstand `{table}`: unbekannt"


def write_report(path: Path, title: str, sections: list[str], *, meta_lines: list[str] | None = None) -> Path:
    content = [
        f"# {title}",
        "",
        f"- Erstellt: {datetime.now():%Y-%m-%d %H:%M:%S}",
    ]
    if meta_lines:
        content.extend(meta_lines)
    content += ["", *sections, ""]
    path.write_text("\n".join(content), encoding="utf-8")
    return path
