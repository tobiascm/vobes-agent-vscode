from __future__ import annotations

import subprocess
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

import file_llm_converter as mod  # noqa: E402


class _Result:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_to_markdown_suppresses_success_stdout_without_debug(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(mod, "LIGHTRAG_REPO", tmp_path)
    script_path = tmp_path / "scripts" / "convert_to_markdown.py"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text("# fake", encoding="utf-8")
    monkeypatch.setattr(mod, "LIGHTRAG_SCRIPT", script_path)

    input_path = tmp_path / "input.png"
    output_path = tmp_path / "output.md"
    input_path.write_bytes(b"fake")

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: _Result(
            0,
            stdout="Converting: image001.png\nMarkdown saved: output.md\n",
            stderr="",
        ),
    )

    rc = mod._to_markdown(input_path, output_path, debug=False)

    captured = capsys.readouterr()
    assert rc == 0
    assert captured.out == ""
    assert captured.err == ""


def test_to_markdown_shows_success_stdout_with_debug(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(mod, "LIGHTRAG_REPO", tmp_path)
    script_path = tmp_path / "scripts" / "convert_to_markdown.py"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text("# fake", encoding="utf-8")
    monkeypatch.setattr(mod, "LIGHTRAG_SCRIPT", script_path)

    input_path = tmp_path / "input.png"
    output_path = tmp_path / "output.md"
    input_path.write_bytes(b"fake")

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: _Result(
            0,
            stdout="Converting: image001.png\nMarkdown saved: output.md\n",
            stderr="warning\n",
        ),
    )

    rc = mod._to_markdown(input_path, output_path, debug=True)

    captured = capsys.readouterr()
    assert rc == 0
    assert "Converting: image001.png" in captured.out
    assert "Markdown saved: output.md" in captured.out
    assert "warning" in captured.err
