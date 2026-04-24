"""File Converter: lokale Dateien nach PDF oder Markdown.

Usage:
    python .agents/skills/skill-file-converter/scripts/file_converter.py to-markdown INPUT [OUTPUT] [--no-llm] [--no-llm-pdf] [--all-sheets] [--clipboard]
    python .agents/skills/skill-file-converter/scripts/file_converter.py to-pdf INPUT [OUTPUT]
    python .agents/skills/skill-file-converter/scripts/file_converter.py md-to-pdf INPUT.md [OUTPUT.pdf] [--title TITLE] [--toc-level N] [--no-optimize] [--css CSS_FILE]

Markdown-Konvertierung:
    --no-llm       Lokale Extraktion via file_parsers (PPTX, DOCX, XLSX, PDF, CSV, ...)
                   Schnell, kein LLM noetig, aber ohne semantische Aufbereitung.
    --no-llm-pdf   Nur PDF ohne LLM (pymupdf4llm). PPTX/DOCX/XLSX weiterhin via LLM.
    (ohne Flag)    LLM-basiert via lightrag_test (Docling + Claude).

Exit codes:
    0  Erfolg
    1  Fehler
    2  Format nicht unterstuetzt
    3  Abhaengigkeit fehlt (Office/lightrag_test/markdown-pdf nicht gefunden)
"""

from __future__ import annotations

import argparse
import re
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
# md-to-pdf: Markdown via markdown-pdf
# ---------------------------------------------------------------------------


def _ascii_slug(text: str) -> str:
    """Normalise heading text to an ASCII-only slug (lowercase, hyphens).

    Used for both heading-ID generation (anchors_plugin slug_func) and
    rewriting internal anchor links so that pymupdf can resolve them.
    """
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_text = nfkd.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^\w\s-]", "", ascii_text).strip().lower()
    return re.sub(r"[-\s]+", "-", slug)


def _markdown_to_pdf(input_path: Path, output_path: Path, *,
                     toc_level: int = 2, optimize: bool = True,
                     title: str | None = None, css_path: Path | None = None) -> int:
    if not input_path.is_file():
        print(f"ERROR: Eingabedatei nicht gefunden: {input_path}", file=sys.stderr)
        return 1

    if input_path.suffix.lower() not in {".md", ".markdown"}:
        print("ERROR: md-to-pdf unterstuetzt nur .md und .markdown", file=sys.stderr)
        return 2

    try:
        from markdown_pdf import MarkdownPdf, Section
    except ImportError:
        print("ERROR: md-to-pdf benoetigt markdown-pdf (python -m pip install markdown-pdf)", file=sys.stderr)
        return 3

    try:
        from urllib.parse import unquote
        user_css = css_path.read_text(encoding="utf-8") if css_path else None
        md_text = input_path.read_text(encoding="utf-8")
        # Rewrite internal anchor links to ASCII slugs so they match the
        # heading IDs generated by anchors_plugin(slug_func=_ascii_slug).
        md_text = re.sub(
            r'\]\(#([^)]+)\)',
            lambda m: f'](#{ _ascii_slug(unquote(m.group(1))) })',
            md_text,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)

        pdf = MarkdownPdf(toc_level=toc_level, optimize=optimize)
        try:
            from mdit_py_plugins.anchors import anchors_plugin
            anchors_plugin(pdf.m_d, min_level=1, max_level=6,
                           slug_func=_ascii_slug, permalink=False)
        except ImportError:
            pass
        pdf.add_section(Section(md_text), user_css=user_css)
        if title:
            pdf.meta["title"] = title
        pdf.save(str(output_path))
    except Exception as exc:
        print(f"ERROR: Markdown-PDF-Konvertierung fehlgeschlagen: {exc}", file=sys.stderr)
        return 1

    print(f"PDF erstellt: {output_path}")
    return 0


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

    # md-to-pdf
    md_pdf = sub.add_parser("md-to-pdf", help="Markdown nach PDF konvertieren (markdown-pdf)")
    md_pdf.add_argument("input", type=Path, help="Markdown-Eingabedatei")
    md_pdf.add_argument("output", type=Path, nargs="?", help="Ausgabedatei (default: <stem>.pdf)")
    md_pdf.add_argument("--title", type=str, default=None, help="PDF-Titel-Metadatum")
    md_pdf.add_argument("--toc-level", type=int, default=2, help="Bookmark/TOC-Tiefe (default: 2)")
    md_pdf.add_argument("--no-optimize", action="store_true", help="PDF-Optimierung deaktivieren")
    md_pdf.add_argument("--css", type=Path, default=None, help="CSS-Datei fuer markdown-pdf")

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

    elif args.command == "md-to-pdf":
        input_path = args.input.resolve()
        output_path = (args.output or _default_output(input_path, ".pdf")).resolve()
        css_path = args.css.resolve() if args.css else None
        return _markdown_to_pdf(
            input_path, output_path,
            toc_level=args.toc_level,
            optimize=not args.no_optimize,
            title=args.title,
            css_path=css_path,
        )

    return 1


if __name__ == "__main__":
    sys.exit(main())
