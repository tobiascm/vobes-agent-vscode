"""File Converter: lokale Dateien nach PDF oder Markdown.

Usage:
    python .agents/skills/skill-file-converter/scripts/file_converter.py to-markdown INPUT [OUTPUT] [--no-llm] [--no-llm-pdf] [--all-sheets] [--clipboard]
    python .agents/skills/skill-file-converter/scripts/file_converter.py to-pdf INPUT [OUTPUT]

Markdown-Konvertierung:
    --no-llm       Lokale Extraktion via file_parsers (PPTX, DOCX, XLSX, PDF, CSV, ...)
                   Schnell, kein LLM noetig, aber ohne semantische Aufbereitung.
    --no-llm-pdf   Nur PDF ohne LLM (pymupdf4llm). PPTX/DOCX/XLSX weiterhin via LLM.
    (ohne Flag)    LLM-basiert via lightrag_test (Docling + Claude).

Exit codes:
    0  Erfolg
    1  Fehler
    2  Format nicht unterstuetzt
    3  Abhaengigkeit fehlt (Office/lightrag_test nicht gefunden)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Windows UTF-8
if sys.platform == "win32":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

# Ensure this script's directory is on sys.path for sibling imports
_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

# Non-LLM parser formats (from file_parsers.py)
_NON_LLM_EXTS = {".pptx", ".xlsx", ".xls", ".docx", ".pdf", ".csv",
                  ".txt", ".md", ".json", ".xml", ".html", ".htm", ".log",
                  ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".tif", ".svg", ".webp"}


# ---------------------------------------------------------------------------
# to-markdown: Router zwischen non-LLM (file_parsers) und LLM (file_llm_converter)
# ---------------------------------------------------------------------------


def _to_markdown(input_path: Path, output_path: Path, *, no_llm_pdf: bool = False,
                 no_llm: bool = False, all_sheets: bool = False, debug: bool = False,
                 prompt: str | None = None) -> int:
    """Konvertiert eine Datei nach Markdown.

    Wenn no_llm=True und das Format von file_parsers unterstuetzt wird,
    wird die lokale Extraktion verwendet. Sonst wird an die LLM-Pipeline delegiert.
    """
    if not input_path.is_file():
        print(f"ERROR: Eingabedatei nicht gefunden: {input_path}", file=sys.stderr)
        return 1

    ext = input_path.suffix.lower()

    # --- Non-LLM path: file_parsers ---
    if no_llm and ext in _NON_LLM_EXTS:
        from file_parsers import convert_bytes
        data = input_path.read_bytes()
        text = convert_bytes(data, input_path.name)
        if text is None:
            print(f"ERROR: Format '{ext}' nicht unterstuetzt fuer non-LLM Markdown", file=sys.stderr)
            return 2
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")
        print(f"Markdown erstellt (non-LLM): {output_path}")
        print(f"  {len(text):,} Zeichen, {text.count(chr(10)) + 1} Zeilen")
        return 0

    # --- LLM path: file_llm_converter ---
    from file_llm_converter import _to_markdown as _llm_to_markdown
    return _llm_to_markdown(input_path, output_path, no_llm_pdf=no_llm_pdf, all_sheets=all_sheets, debug=debug, prompt=prompt)


# ---------------------------------------------------------------------------
# to-pdf: delegiert komplett an file_llm_converter (COM-Automation)
# ---------------------------------------------------------------------------


def _to_pdf(input_path: Path, output_path: Path) -> int:
    from file_llm_converter import _to_pdf as _llm_to_pdf
    return _llm_to_pdf(input_path, output_path)


# ---------------------------------------------------------------------------
# Clipboard
# ---------------------------------------------------------------------------

_DEFAULT_CLIPBOARD_PROMPT = (
    "Wandel das Bild so genau und exakt wie moeglich in ein Markdown um. "
    "Wandel auch tabellen mit allen Werten und Zahlen so exakt wie moeglich um!"
)


def _grab_clipboard_image(save_dir: Path) -> tuple[Path | None, str | None]:
    """Bild aus Windows-Zwischenablage holen und als PNG speichern.

    Returns (png_path, None) bei Erfolg, (None, error_msg) bei Fehler.
    """
    if sys.platform != "win32":
        return None, "ERROR: --clipboard benoetigt Windows"

    try:
        from PIL import ImageGrab
    except ImportError:
        return None, "ERROR: --clipboard benoetigt Pillow (pip install Pillow)"

    clip = ImageGrab.grabclipboard()
    if clip is None:
        return None, "ERROR: Zwischenablage ist leer (kein Bild gefunden)"
    if isinstance(clip, list):
        hint = clip[0] if clip else "?"
        return None, (
            f"ERROR: Zwischenablage enthaelt Dateipfade, kein Bild:\n"
            f"  {hint}\n"
            f'  Nutze stattdessen: to-markdown "{hint}"'
        )

    from PIL import Image
    if not isinstance(clip, Image.Image):
        return None, f"ERROR: Unerwarteter Clipboard-Inhalt: {type(clip)}"

    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    png_name = f"clipboard_{ts}.png"
    save_dir.mkdir(parents=True, exist_ok=True)
    png_path = save_dir / png_name
    clip.save(png_path, format="PNG")
    print(f"Clipboard-Bild gespeichert: {png_path}  ({clip.size[0]}x{clip.size[1]} px)")
    return png_path, None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _default_output(input_path: Path, new_suffix: str) -> Path:
    return input_path.with_suffix(new_suffix)


def main() -> int:
    parser = argparse.ArgumentParser(description="File Converter: lokale Dateien nach PDF oder Markdown")
    sub = parser.add_subparsers(dest="command", required=True)

    # to-markdown
    md = sub.add_parser("to-markdown", help="Datei nach Markdown konvertieren")
    md.add_argument("input", type=Path, nargs="?", default=None,
                    help="Eingabedatei (nicht noetig bei --clipboard)")
    md.add_argument("output", type=Path, nargs="?", help="Ausgabedatei (default: <stem>.md)")
    md.add_argument("--no-llm", action="store_true",
                    help="Lokale Extraktion ohne LLM (PPTX, DOCX, XLSX, PDF, CSV, ...)")
    md.add_argument("--no-llm-pdf", action="store_true",
                    help="Nur PDF ohne LLM extrahieren (pymupdf4llm)")
    md.add_argument("--all-sheets", action="store_true", help="Excel: alle Worksheets")
    md.add_argument("--prompt", type=str, default=None,
                    help="Custom prompt fuer Bild-Konvertierung (LLM)")
    md.add_argument("--clipboard", action="store_true",
                    help="Bild aus Windows-Zwischenablage statt Eingabedatei verwenden")

    # to-pdf
    pdf = sub.add_parser("to-pdf", help="Datei nach PDF konvertieren (Office COM)")
    pdf.add_argument("input", type=Path, help="Eingabedatei")
    pdf.add_argument("output", type=Path, nargs="?", help="Ausgabedatei (default: <stem>.pdf)")

    args = parser.parse_args()

    if args.command == "to-markdown":
        # --- Clipboard mode ---
        if args.clipboard:
            if args.input is not None:
                parser.error("--clipboard und INPUT sind nicht kombinierbar")

            if args.output:
                save_dir = args.output.resolve().parent
            else:
                save_dir = Path(__file__).resolve().parents[4] / "userdata" / "tmp"
            png_path, err = _grab_clipboard_image(save_dir)
            if err:
                print(err, file=sys.stderr)
                return 3 if "benoetigt" in err else 1
            input_path = png_path
            prompt = args.prompt or _DEFAULT_CLIPBOARD_PROMPT
        else:
            if args.input is None:
                parser.error("INPUT ist erforderlich (oder --clipboard verwenden)")
            input_path = args.input.resolve()
            prompt = args.prompt

        output_path = (args.output or _default_output(input_path, ".md")).resolve()
        return _to_markdown(
            input_path, output_path,
            no_llm=args.no_llm,
            no_llm_pdf=args.no_llm_pdf,
            all_sheets=args.all_sheets,
            prompt=prompt,
        )

    elif args.command == "to-pdf":
        input_path = args.input.resolve()
        output_path = (args.output or _default_output(input_path, ".pdf")).resolve()
        return _to_pdf(input_path, output_path)

    return 1


if __name__ == "__main__":
    sys.exit(main())
