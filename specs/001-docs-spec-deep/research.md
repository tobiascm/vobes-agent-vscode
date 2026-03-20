# Research: Deep Research Orchestration Skill

**Date**: 2026-03-19 | **Feature**: 001-docs-spec-deep

## R1: Skill Location Correction

**Decision**: Skill lives at `.agents/skills/skill-deep-research/SKILL.md` (not `.github/skills/` as initially assumed in the spec).

**Rationale**: The constitution (Principle I) mandates `.agents/skills/` as the canonical location. A junction to `.claude/skills/` exists for Claude Code compatibility. All 15 existing skills follow this pattern.

**Alternatives considered**:
- `.github/skills/` — mentioned in spec assumptions, but no skills exist there; contradicts constitution
- `.claude/skills/` — junction target, not the source of truth

## R2: SKILL.md Structure & Format

**Decision**: Follow the established pattern from `skill-browse-intranet`: YAML frontmatter (`name`, `description`) followed by structured markdown sections (when to use, when not to use, workflow, examples).

**Rationale**: All 15 existing skills use this exact format. Consistency ensures the routing logic in `AGENTS.md` and the Copilot/Claude skill loading mechanisms work without changes.

**Alternatives considered**:
- Custom format with embedded YAML/JSON for research state schema — rejected; the skill is prompt-based, not code-based. State is maintained by the agent in-conversation, not in config files.
- Adding `agents/openai.yaml` — only used by `skill-knowledge-bordnetz-vobes` for RAG configuration. Not needed for an orchestration skill.

## R3: Delegation Mechanism to skill-browse-intranet

**Decision**: SKILL.md instructions will reference `skill-browse-intranet` by name and instruct the agent to load it via the standard skill dispatch mechanism before performing any browser interaction. The deep-research SKILL.md will not list Playwright MCP tools directly.

**Rationale**: `skill-browse-intranet` already documents all Playwright MCP tools, workflows, and troubleshooting. Duplicating this would violate Constitution Principle V (simplicity) and create maintenance burden.

**Alternatives considered**:
- Inlining Playwright tool references — rejected; creates duplication and risks drift between the two skill files
- Making browse-intranet a declared dependency in YAML frontmatter — no precedent in existing skills; the dispatch table in AGENTS.md handles this

## R4: Crawl4AI Integration Approach

**Decision**: For V1, Crawl4AI integration is documented as an optional enhancement in the SKILL.md workflow. The skill is fully functional using only `skill-browse-intranet` for all page interactions. Crawl4AI instructions are placed in a clearly marked optional section.

**Rationale**: Crawl4AI requires a separate installation and may not be available in all environments. Making it optional for V1 keeps the skill immediately usable. The spec explicitly states V1 can function without it.

**Alternatives considered**:
- Making Crawl4AI a hard dependency — rejected; would block skill usage in environments where Crawl4AI isn't installed
- Deferring Crawl4AI entirely to V2 — rejected; documenting the integration pattern now (even as optional) guides future implementation

## R5: Output File Naming Convention

**Decision**: Per-task output directory `userdata/research_output/YYYYMMDD_[Title]/` with two files: `research_tracking.md` (search trail) and `research_report.md` (final report). The `[Title]` is a short slug derived from the research topic (e.g., `20260319_supplier-onboarding-process`).

**Rationale**: Date prefix enables chronological sorting. Title slug enables quick identification. Two separate files keep the tracking (verbose, step-by-step) cleanly separated from the report (concise, user-facing), even though the spec says V1 uses a single tracking file — the cost of a second file is negligible and improves usability.

**Alternatives considered**:
- Single combined file — spec originally suggested this for V1, but tracking entries and the final report serve different audiences and purposes; separation is cleaner
- Timestamp with time component (YYYYMMDD_HHMM) — unnecessary granularity for V1; one research task per topic per day is the expected pattern

## R6: AGENTS.md Routing Entry

**Decision**: Add a new use-case entry to the dispatch table in `AGENTS.md` for deep research. Trigger patterns: "deep research", "recherchiere", "untersuche systematisch", "multi-source research", complex research questions requiring multiple portals.

**Rationale**: Constitution Principle III (Mandatory Skill Routing) requires all skills to be registered in the AGENTS.md dispatch table.

**Alternatives considered**:
- No AGENTS.md update — would violate Constitution Principle III
- Overloading the browse-intranet trigger — rejected; deep research is a distinct orchestration layer, not a browsing task

## R7a: AGENTS.md / CLAUDE.md Duality

**Decision**: Both `AGENTS.md` and `CLAUDE.md` must be updated in sync. `AGENTS.md` is authoritative per the constitution. `CLAUDE.md` is a mirror that Claude Code reads at runtime. Both files currently have identical content.

**Rationale**: The constitution declares `AGENTS.md` as the authoritative routing file (Principle III). However, Claude Code loads `CLAUDE.md` (not `AGENTS.md`) as project instructions. If only one is updated, routing breaks for one of the two runtimes (Copilot vs Claude Code).

**Alternatives considered**:
- Making `CLAUDE.md` a symlink/junction to `AGENTS.md` — would be cleaner but `CLAUDE.md` may need Claude Code-specific sections in the future
- Only updating `AGENTS.md` — breaks Claude Code routing
- Only updating `CLAUDE.md` — violates constitution

## R8: User Checkpoint Before Research

**Decision**: After generating the research brief and plan, the skill must present both to the user and wait for confirmation before visiting any page. The user may adjust leads, priorities, or depth.

**Rationale**: A research task can consume up to 50 autonomous steps. Without a checkpoint, the user has no opportunity to correct a misunderstood question or adjust scope before significant effort is spent.

**Alternatives considered**:
- No checkpoint (fully autonomous) — rejected; too much autonomous action without verification for a first version
- Checkpoint after every step — rejected; defeats the purpose of autonomous research

## R7: Research State Management

**Decision**: The agent maintains research state (brief, plan, leads, evidence, visited URLs) in its conversation context. No external state file or database is used in V1. The tracking markdown file is the persistent artifact.

**Rationale**: The skill is prompt-based — the agent's context window is the natural place for working state. Persistence/resume is explicitly out of scope for V1 per the spec assumptions. The tracking file provides enough persistence for post-hoc review.

**Alternatives considered**:
- JSON state file updated after each step — over-engineering for V1; adds complexity without benefit since resume isn't supported
- SQLite database — far too heavy for a prompt-based skill's first version
