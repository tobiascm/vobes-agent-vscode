"""E2E tests for skill-file-converter – real COM + LLM conversion, no mocking."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

WORKSPACE = Path(__file__).resolve().parents[1]
CONVERTER_SCRIPT = (
    WORKSPACE
    / ".agents"
    / "skills"
    / "skill-file-converter"
    / "scripts"
    / "file_converter.py"
)
TEST_DATA = Path(__file__).resolve().parent

TIMEOUT_SECONDS = 600  # 10 min – COM + LLM brauchen Zeit


def _run_converter(*args: str) -> subprocess.CompletedProcess[str]:
    """Run file_converter.py as a real subprocess (no mocking)."""
    return subprocess.run(
        [sys.executable, str(CONVERTER_SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=TIMEOUT_SECONDS,
    )


# ---------------------------------------------------------------------------
# to-markdown  (4 Dateien, echte LLM-Pipeline)
# ---------------------------------------------------------------------------

_MD_CASES = [
    ("TestPDF.pdf", "TestPDF"),
    ("TestPNG.png", "Bildinfo 456"),
    ("TestPPTX.pptx", "Bildinfo 123"),
    ("TestXLSX-lang.xlsx", "Test Excel"),
]


@pytest.mark.e2e
@pytest.mark.parametrize(
    "filename, expected_text",
    _MD_CASES,
    ids=[c[0] for c in _MD_CASES],
)
def test_to_markdown(filename: str, expected_text: str, tmp_path: Path) -> None:
    input_file = TEST_DATA / filename
    output_file = tmp_path / f"{Path(filename).stem}.md"

    result = _run_converter("to-markdown", str(input_file), str(output_file))

    assert result.returncode == 0, (
        f"to-markdown failed for {filename}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert output_file.exists(), f"Output {output_file} not created"
    content = output_file.read_text(encoding="utf-8")
    assert len(content.strip()) > 0, f"Output {output_file} is empty"
    assert expected_text.lower() in content.lower(), (
        f"Expected '{expected_text}' not found in {filename} markdown output.\n"
        f"Content (first 500 chars): {content[:500]}"
    )


# ---------------------------------------------------------------------------
# to-pdf  (nur PPTX + XLSX – COM-Automation)
# ---------------------------------------------------------------------------

_PDF_CASES = [
    "TestPPTX.pptx",
    "TestXLSX-lang.xlsx",
]


@pytest.mark.e2e
@pytest.mark.parametrize("filename", _PDF_CASES, ids=_PDF_CASES)
def test_to_pdf(filename: str, tmp_path: Path) -> None:
    input_file = TEST_DATA / filename
    output_file = tmp_path / f"{Path(filename).stem}.pdf"

    result = _run_converter("to-pdf", str(input_file), str(output_file))

    assert result.returncode == 0, (
        f"to-pdf failed for {filename}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert output_file.exists(), f"Output {output_file} not created"
    assert output_file.stat().st_size > 0, f"Output PDF {output_file} is empty"
