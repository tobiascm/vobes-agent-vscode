"""Wrapper fuer query_rag_mcp aus dem benachbarten lightrag_test-Repo.

Startet `python -m lightrag_vobes.apps.query_rag_mcp ...` in einem
Unterprozess mit:
- `cwd` = Ziel-Repo (`lightrag_test`)
- `PYTHONPATH` mit `<repo>/src` an erster Stelle

Damit bleibt das aktuelle Arbeitsverzeichnis des aufrufenden Agenten unveraendert.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LIGHTRAG_REPO = WORKSPACE_ROOT.parent / "lightrag_test"
REPO_ENV_VAR = "LIGHTRAG_VOBES_REPO"


def _resolve_repo_dir() -> Path:
    override = os.environ.get(REPO_ENV_VAR, "").strip()
    repo_dir = Path(override) if override else DEFAULT_LIGHTRAG_REPO
    return repo_dir.resolve()


def _build_subprocess_env(repo_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    src_dir = repo_dir / "src"
    existing = env.get("PYTHONPATH", "").strip()
    entries = [str(src_dir)]
    if existing:
        entries.extend(part for part in existing.split(os.pathsep) if part)
    env["PYTHONPATH"] = os.pathsep.join(entries)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


def run_query_rag(argv: list[str]) -> int:
    repo_dir = _resolve_repo_dir()
    env_file = repo_dir / ".env"
    src_dir = repo_dir / "src"

    if not repo_dir.is_dir():
        print(
            f"ERROR: LightRAG-Repo nicht gefunden: {repo_dir} "
            f"(Override via {REPO_ENV_VAR})",
            file=sys.stderr,
        )
        return 1
    if not src_dir.is_dir():
        print(f"ERROR: src-Verzeichnis fehlt: {src_dir}", file=sys.stderr)
        return 1
    if not env_file.is_file():
        print(f"ERROR: .env fehlt: {env_file}", file=sys.stderr)
        return 1
    if not argv:
        print(
            "Usage: python scripts/query_local_rag.py "
            "<chat|list-tools|call ...>",
            file=sys.stderr,
        )
        return 1

    cmd = [sys.executable, "-m", "lightrag_vobes.apps.query_rag_mcp", *argv]
    completed = subprocess.run(
        cmd,
        cwd=repo_dir,
        env=_build_subprocess_env(repo_dir),
        check=False,
    )
    return int(completed.returncode)


def main() -> int:
    return run_query_rag(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
