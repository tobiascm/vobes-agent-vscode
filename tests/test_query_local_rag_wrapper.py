from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import query_local_rag as mod  # noqa: E402


def test_run_query_rag_executes_in_target_repo(monkeypatch, tmp_path):
    repo_dir = tmp_path / "lightrag_test"
    src_dir = repo_dir / "src"
    src_dir.mkdir(parents=True)
    (repo_dir / ".env").write_text("X=1\n", encoding="utf-8")
    monkeypatch.setenv(mod.REPO_ENV_VAR, str(repo_dir))

    calls: list[dict[str, object]] = []

    def fake_run(cmd, cwd, env, check):
        calls.append({"cmd": cmd, "cwd": cwd, "env": env, "check": check})
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(mod.subprocess, "run", fake_run)

    code = mod.run_query_rag(["list-tools"])

    assert code == 0
    assert len(calls) == 1
    assert calls[0]["cmd"] == [
        sys.executable,
        "-m",
        "lightrag_vobes.apps.query_rag_mcp",
        "list-tools",
    ]
    assert calls[0]["cwd"] == repo_dir.resolve()
    assert calls[0]["check"] is False
    pythonpath = calls[0]["env"]["PYTHONPATH"]
    assert pythonpath.split(os.pathsep)[0] == str(src_dir.resolve())


def test_run_query_rag_fails_when_env_missing(monkeypatch, tmp_path, capsys):
    repo_dir = tmp_path / "lightrag_test"
    (repo_dir / "src").mkdir(parents=True)
    monkeypatch.setenv(mod.REPO_ENV_VAR, str(repo_dir))

    code = mod.run_query_rag(["list-tools"])

    captured = capsys.readouterr()
    assert code == 1
    assert "ERROR: .env fehlt" in captured.err
