<!--
  ============================================================================
  Sync Impact Report
  ============================================================================
  Version change: (none) → 1.0.0
  Modified principles: N/A (initial ratification)
  Added sections:
    - Core Principles (5 principles)
    - Technology Stack & Constraints
    - Development Workflow
    - Governance
  Removed sections: N/A
  Templates requiring updates:
    - .specify/templates/plan-template.md ✅ compatible (Constitution Check
      section references constitution generically)
    - .specify/templates/spec-template.md ✅ compatible (no constitution
      references needed)
    - .specify/templates/tasks-template.md ✅ compatible (no constitution
      references needed)
    - .specify/templates/checklist-template.md ✅ compatible
    - .specify/templates/agent-file-template.md ✅ compatible
  Follow-up TODOs: none
  ============================================================================
-->

# VOBES Agent VS Code Constitution

## Core Principles

### I. Skill-First Architecture

Every domain capability MUST be encapsulated as a self-contained skill
under `.agents/skills/` with its own `SKILL.md`. Domain logic MUST NOT
be inlined in `AGENTS.md`; the steering file dispatches to skills, it
does not implement them.

- Each skill directory MUST contain a `SKILL.md` that defines trigger
  patterns, required MCP servers, and execution instructions.
- Skills MUST be independently loadable — no implicit dependencies on
  other skills unless explicitly declared.
- Naming convention: `skill-{domain}-{capability}`
  (e.g., `skill-budget-bplus-export`, `skill-knowledge-bordnetz-vobes`).

**Rationale**: Self-contained skills enable parallel development,
clear ownership, and safe addition/removal without side effects.

### II. Evidence-Based Responses

All domain answers MUST be backed by verifiable data sources. The agent
MUST NOT produce unbacked generalizations or speculative answers for
factual questions.

- Bordnetz/VOBES context: MUST query `local_rag` before answering.
  Without a RAG result, no domain answer may be given.
- Budget/finance context: MUST run the corresponding report script
  against live data or the local SQLite database.
- External system data (Confluence, Jira, BPLUS-NG): MUST be retrieved
  via the appropriate MCP server or API, not recalled from memory.

**Rationale**: Users rely on agent answers for engineering and budget
decisions; inaccurate or unverifiable information erodes trust.

### III. Mandatory Skill Routing

Before composing any response, the agent MUST check whether a matching
skill exists in the use-case dispatch table (`AGENTS.md`). If a match
is found, the skill MUST be loaded before answering.

- The dispatch table in `AGENTS.md` is authoritative for routing.
- If no skill matches, the agent may answer directly (general topic).
- MCP availability MUST be verified before loading a skill that
  depends on an MCP server. If unavailable (e.g., Plan mode), the
  agent MUST surface a clear error message and abort the task.

**Rationale**: Consistent routing ensures domain expertise is always
applied and prevents the agent from answering outside its competence
without the proper knowledge base.

### IV. Computational Integrity

Numerical calculations, aggregations, sums, and statistical summaries
MUST be computed via code (Python or PowerShell), never estimated or
calculated manually by the agent.

- Budget and finance computations MUST always produce a fresh
  evaluation from current data. Reusing an existing `.md` report
  file as a data source is prohibited.
- Scripts MUST write structured output (JSON, CSV, or formatted
  tables) to enable downstream validation.

**Rationale**: Manual arithmetic by LLMs is error-prone; code
execution provides reproducible, auditable results.

### V. Simplicity & Minimal Scope

Changes to the agent configuration, skills, and scripts MUST be kept
to the minimum necessary to achieve the stated goal. No speculative
features, no premature abstractions, no over-engineering.

- A new skill MUST solve at least one concrete, recurring use-case.
- Configuration changes MUST NOT introduce unused capabilities.
- Prefer editing an existing skill over creating a new one when the
  domain overlap is significant.

**Rationale**: The agent workspace is a shared tool used daily;
unnecessary complexity increases maintenance burden and reduces
reliability.

## Technology Stack & Constraints

- **Skills location**: `.agents/skills/` (mirrored to `.claude/skills`
  via junction for Claude Code compatibility).
- **MCP servers**: `local-rag` (HTTP, localhost:8000), `mcp-atlassian`
  (stdio, Docker), Playwright MCP (Chrome extension).
- **Languages**: Python 3.x (report scripts, data processing),
  PowerShell (system scripts, container management).
- **Data stores**: SQLite (local cache for BPLUS-NG data), BPLUS-NG
  REST API (live budget data).
- **External systems**: Confluence (VOBES, VSUP, EKEK1 spaces), Jira
  (VKON2, SYS-FLOW projects), GroupFind GraphQL API (person search).
- **Runtime**: VS Code with GitHub Copilot Extension; Claude Code CLI.

## Development Workflow

- **Adding a skill**: Create `skill-{domain}-{capability}/SKILL.md`
  under `.agents/skills/`. Register the skill in the use-cases section
  of `AGENTS.md`. Update `README.md` skills table if user-facing.
- **Removing a skill**: Delete the skill directory. Remove entries from
  `AGENTS.md` and `README.md`. Verify no other skill depends on it.
- **Modifying AGENTS.md**: Changes to routing rules, tool priorities,
  or mode-detection logic MUST be reviewed for impact on all registered
  skills.
- **Report scripts**: Scripts under `scripts/` that produce budget or
  data reports MUST write logs and MUST fall back to cached DB data
  with a warning if the live API is unreachable.
- **Testing**: Report scripts MUST have corresponding pytest tests
  under `tests/`. Skill changes SHOULD be validated by exercising the
  skill end-to-end in agent mode.

## Governance

This constitution is the highest-authority document for development
practices in this workspace. It supersedes conflicting guidance in
skill files, scripts, or ad-hoc instructions.

- **Amendments**: Any change to this constitution MUST be documented
  with a version bump, a Sync Impact Report (HTML comment at file
  top), and propagation to dependent templates if affected.
- **Versioning**: MAJOR.MINOR.PATCH — MAJOR for principle
  removals/redefinitions, MINOR for new principles or material
  expansions, PATCH for clarifications and wording fixes.
- **Compliance**: All new skills and script changes SHOULD be reviewed
  against the principles in this document. The Constitution Check
  section in `plan-template.md` enforces this during feature planning.
- **Runtime guidance**: `AGENTS.md` serves as the runtime guidance
  file and MUST remain consistent with this constitution.

**Version**: 1.0.0 | **Ratified**: 2026-03-19 | **Last Amended**: 2026-03-19
