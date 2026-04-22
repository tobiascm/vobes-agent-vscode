from __future__ import annotations

import builtins
import sys
from pathlib import Path


WORKSPACE = Path(__file__).resolve().parents[1]
sys.path.insert(
    0,
    str(
        WORKSPACE
        / ".agents"
        / "skills"
        / "skill-file-converter"
        / "scripts"
    ),
)

import file_converter as mod  # noqa: E402


def test_md_to_pdf_missing_input_returns_1(tmp_path, capsys):
    rc = mod._markdown_to_pdf(tmp_path / "missing.md", tmp_path / "out.pdf")

    captured = capsys.readouterr()
    assert rc == 1
    assert "Eingabedatei nicht gefunden" in captured.err


def test_md_to_pdf_rejects_non_markdown_input(tmp_path, capsys):
    input_path = tmp_path / "input.txt"
    input_path.write_text("# Titel", encoding="utf-8")

    rc = mod._markdown_to_pdf(input_path, tmp_path / "out.pdf")

    captured = capsys.readouterr()
    assert rc == 2
    assert "nur .md und .markdown" in captured.err


def test_md_to_pdf_missing_dependency_returns_3(tmp_path, monkeypatch, capsys):
    input_path = tmp_path / "input.md"
    input_path.write_text("# Titel", encoding="utf-8")
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "markdown_pdf":
            raise ImportError("missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    rc = mod._markdown_to_pdf(input_path, tmp_path / "out.pdf")

    captured = capsys.readouterr()
    assert rc == 3
    assert "markdown-pdf" in captured.err
