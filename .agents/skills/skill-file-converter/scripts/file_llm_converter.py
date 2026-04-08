"""File LLM Converter: Markdown-Konvertierung via lightrag LLM-Pipeline + PDF via COM.

Wird von file_converter.py als Backend fuer LLM-basierte Konvertierung aufgerufen.
Nicht direkt als CLI verwenden — stattdessen file_converter.py nutzen.

Exit codes:
    0  Erfolg
    1  Fehler
    2  Format nicht unterstuetzt
    3  Abhaengigkeit fehlt (Office/lightrag_test nicht gefunden)
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from threading import get_ident

# Windows UTF-8
if sys.platform == "win32":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

LIGHTRAG_REPO = Path(r"C:\Daten\Python\lightrag_test")
LIGHTRAG_SCRIPT = LIGHTRAG_REPO / "scripts" / "convert_to_markdown.py"

COM_TIMEOUT_SECONDS = 10 * 60  # 10 min

PDF_HANDLERS: dict[str, str] = {
    ".pptx": "powerpoint", ".ppt": "powerpoint",
    ".docx": "word", ".doc": "word",
    ".xlsx": "excel", ".xls": "excel", ".xlsm": "excel",
    ".xltx": "excel", ".xltm": "excel",
}

# ---------------------------------------------------------------------------
# to-markdown: delegiert an lightrag_test (wie pipeline.py Zeile 632-665)
# ---------------------------------------------------------------------------


def _to_markdown(input_path: Path, output_path: Path, *, no_llm_pdf: bool = False, all_sheets: bool = False, debug: bool = False) -> int:
    if not LIGHTRAG_REPO.is_dir():
        print(f"ERROR: lightrag_test Repo nicht gefunden: {LIGHTRAG_REPO}", file=sys.stderr)
        return 3
    if not LIGHTRAG_SCRIPT.is_file():
        print(f"ERROR: convert_to_markdown.py nicht gefunden: {LIGHTRAG_SCRIPT}", file=sys.stderr)
        return 3
    if not input_path.is_file():
        print(f"ERROR: Eingabedatei nicht gefunden: {input_path}", file=sys.stderr)
        return 1

    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [sys.executable, str(LIGHTRAG_SCRIPT), str(input_path), str(output_path)]
    if no_llm_pdf:
        cmd.append("--no-llm-pdf")
    if all_sheets:
        cmd.append("--all-sheets")

    env = {**os.environ, "POSTGRES_TIMEOUT_SECONDS": "5"}
    if debug:
        env.update({"DEBUG_RAG": "true", "DEBUG_LLM": "true", "LOG_LEVEL": "DEBUG", "VERBOSE": "true"})
    try:
        result = subprocess.run(
            cmd,
            cwd=str(LIGHTRAG_REPO),
            capture_output=True,
            text=True,
            timeout=COM_TIMEOUT_SECONDS,
            env=env,
        )
    except subprocess.TimeoutExpired:
        print(f"ERROR: Markdown-Konvertierung Timeout nach {COM_TIMEOUT_SECONDS}s", file=sys.stderr)
        return 1

    if result.stdout and (result.returncode != 0 or debug):
        print(result.stdout, end="")
    if result.stderr and (result.returncode != 0 or debug):
        print(result.stderr, end="", file=sys.stderr)
    return result.returncode


# ---------------------------------------------------------------------------
# to-pdf: COM-Automation (Muster aus office_local_converter.py)
# ---------------------------------------------------------------------------


def _com_to_pdf(input_path: Path, pdf_path: Path, app_type: str) -> None:
    """Direkte COM-Konvertierung — wird im Subprocess aufgerufen."""
    import pythoncom
    import win32com.client

    input_path = input_path.resolve()
    pdf_path = pdf_path.resolve()
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    pythoncom.CoInitialize()
    try:
        if app_type == "powerpoint":
            app = win32com.client.DispatchEx("PowerPoint.Application")
            app.DisplayAlerts = 0
            doc = app.Presentations.Open(str(input_path), ReadOnly=1, Untitled=0, WithWindow=0)
            try:
                doc.SaveAs(str(pdf_path), 32)  # 32 = ppSaveAsPDF
            finally:
                doc.Close()
            app.Quit()

        elif app_type == "word":
            app = win32com.client.DispatchEx("Word.Application")
            app.DisplayAlerts = 0
            app.Visible = False
            doc = app.Documents.Open(str(input_path), ReadOnly=True)
            try:
                doc.SaveAs2(str(pdf_path), FileFormat=17)  # 17 = wdFormatPDF
            finally:
                doc.Close(False)
            app.Quit()

        elif app_type == "excel":
            app = win32com.client.DispatchEx("Excel.Application")
            app.DisplayAlerts = False
            app.Visible = False
            wb = app.Workbooks.Open(str(input_path), ReadOnly=True)
            try:
                wb.ExportAsFixedFormat(0, str(pdf_path))  # 0 = xlTypePDF
            finally:
                wb.Close(False)
            app.Quit()

        else:
            raise ValueError(f"Unbekannter app_type: {app_type}")
    finally:
        pythoncom.CoUninitialize()


_PROCESS_NAMES = {
    "powerpoint": "POWERPNT.EXE",
    "word": "WINWORD.EXE",
    "excel": "EXCEL.EXE",
}


def _to_pdf_subprocess(input_path: Path, pdf_path: Path, app_type: str) -> None:
    """COM-Konvertierung in isoliertem Subprocess (wie office_local_converter.py)."""
    cmd = [
        sys.executable, "-c",
        (
            "import sys; sys.path.insert(0, r'" + str(Path(__file__).resolve().parent) + "');"
            "from file_llm_converter import _com_to_pdf;"
            "from pathlib import Path;"
            f"_com_to_pdf(Path(r'''{input_path}'''), Path(r'''{pdf_path}'''), '''{app_type}''')"
        ),
    ]
    try:
        subprocess.run(cmd, check=True, timeout=COM_TIMEOUT_SECONDS, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if exc.stderr else "unbekannter Fehler"
        raise RuntimeError(f"COM-Konvertierung fehlgeschlagen: {stderr}") from exc
    except subprocess.TimeoutExpired:
        process_name = _PROCESS_NAMES.get(app_type)
        if process_name and sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/T", "/IM", process_name],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        raise TimeoutError(
            f"{app_type} COM-Konvertierung Timeout nach {COM_TIMEOUT_SECONDS}s "
            f"(pid={os.getpid()} tid={get_ident()})"
        )


def _to_pdf(input_path: Path, output_path: Path) -> int:
    if sys.platform != "win32":
        print("ERROR: PDF-Konvertierung via COM benoetigt Windows", file=sys.stderr)
        return 3

    if not input_path.is_file():
        print(f"ERROR: Eingabedatei nicht gefunden: {input_path}", file=sys.stderr)
        return 1

    ext = input_path.suffix.lower()
    app_type = PDF_HANDLERS.get(ext)
    if not app_type:
        supported = ", ".join(sorted(PDF_HANDLERS.keys()))
        print(f"ERROR: Format '{ext}' nicht unterstuetzt fuer PDF. Unterstuetzt: {supported}", file=sys.stderr)
        return 2

    try:
        _to_pdf_subprocess(input_path.resolve(), output_path.resolve(), app_type)
    except (RuntimeError, TimeoutError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"PDF erstellt: {output_path}")
    return 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _default_output(input_path: Path, new_suffix: str) -> Path:
    return input_path.with_suffix(new_suffix)
