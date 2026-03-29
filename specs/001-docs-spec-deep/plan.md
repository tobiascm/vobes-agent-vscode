# Implementation Plan: Deep Research Orchestration Skill

**Branch**: `001-docs-spec-deep` | **Date**: 2026-03-19 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-docs-spec-deep/spec.md`

## Summary

Create `skill-deep-research`, a meta-skill that orchestrates multi-step, multi-source research across web pages and internal portals. The skill is implemented as a single `SKILL.md` file that defines a structured research workflow (brief → plan → iterative research loops → evidence collection → final report) and delegates all browser interactions to `skill-browse-intranet`. Research output (tracking file + final report) is written to `userdata/research_output/YYYYMMDD_[Title]/`.

## Technical Context

**Language/Version**: Markdown (SKILL.md skill definition — no application code)
**Primary Dependencies**: `skill-browse-intranet` (Playwright MCP for browser interactions), Crawl4AI (optional crawl backend, V1 functional without it)
**Storage**: Markdown files in `userdata/research_output/YYYYMMDD_[Title]/` per research task
**Testing**: End-to-end skill validation in agent mode (no unit tests — this is a prompt-based skill, not code)
**Target Platform**: VS Code + GitHub Copilot Extension; Claude Code CLI
**Project Type**: Skill definition (`.agents/skills/skill-deep-research/SKILL.md`)
**Performance Goals**: Up to 50 research steps per task, no inter-step throttling
**Constraints**: Read-only by default, no write actions unless user-authorized
**Scale/Scope**: Single user, single research task at a time

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Skill-First Architecture | PASS | New skill at `.agents/skills/skill-deep-research/SKILL.md` with own trigger patterns, MCP dependencies, and execution instructions |
| II. Evidence-Based Responses | PASS | Skill's core purpose is evidence-backed research with graded confidence levels and source tracking |
| III. Mandatory Skill Routing | REQUIRES ACTION | Must add routing entry to `AGENTS.md` use-case dispatch table + mirror in `CLAUDE.md` |
| IV. Computational Integrity | N/A | No numerical computations in this skill |
| V. Simplicity & Minimal Scope | PASS | Single SKILL.md, solves concrete recurring use-case (multi-source research), delegates browser work to existing skill |

**Gate result**: PASS (one action item: AGENTS.md + CLAUDE.md routing update, addressed in tasks)

## Project Structure

### Documentation (this feature)

```text
specs/001-docs-spec-deep/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
.agents/skills/skill-deep-research/
└── SKILL.md             # Skill definition (trigger patterns, workflow, delegation rules, output format)

userdata/research_output/
└── YYYYMMDD_[Title]/    # Per-task output directory (auto-created at runtime)
    ├── research_tracking.md   # Search trail with numbered steps
    └── research_report.md     # Final structured report
```

**Additional files to modify**:
- `AGENTS.md` — add routing entry for deep research trigger patterns
- `CLAUDE.md` — mirror the same routing entry (CLAUDE.md mirrors AGENTS.md for Claude Code compatibility)
- `README.md` — add skill to skills table (per constitution Development Workflow)

**Structure Decision**: Follows the established single-file skill pattern (like `skill-browse-intranet`). No `agents/openai.yaml` needed — this skill is purely prompt-based orchestration with no RAG or custom agent configuration. Output directory uses the existing `userdata/` root which already hosts session data, exports, and caches.

## Complexity Tracking

No constitution violations to justify. Implementation is a single SKILL.md file plus an AGENTS.md/CLAUDE.md routing update.

## Notes (added 2026-03-20)

- `AGENTS.md` and `CLAUDE.md` currently share identical content. `AGENTS.md` is authoritative per the constitution; `CLAUDE.md` is the file Claude Code reads at runtime. Both must be updated in sync.
- The `.claude/skills/` directory is a junction pointing to `.agents/skills/` — no need to create skill files in both locations.
- `userdata/research_output/` does not exist yet and must be auto-created by the skill at runtime (or during implementation setup).
