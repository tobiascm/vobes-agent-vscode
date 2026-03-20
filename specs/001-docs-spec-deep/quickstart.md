# Quickstart: Deep Research Orchestration Skill

**Date**: 2026-03-19 | **Feature**: 001-docs-spec-deep

## What This Skill Does

`skill-deep-research` turns open-ended research questions into structured, evidence-backed answers by systematically investigating multiple web pages and internal portals. It produces a transparent search trail and a final report with graded confidence levels.

## Prerequisites

- `skill-browse-intranet` must be available and functional (Playwright MCP)
- `userdata/` directory must exist at repo root (already present)
- Agent must have access to Playwright MCP tools for browser interaction

## How to Trigger

Ask a research question that requires information from multiple sources:

- "Recherchiere systematisch, welche internen Portale den Freigabeprozess fuer neue Lieferanten dokumentieren"
- "Untersuche, welche Regelwerke und Prozessstandards fuer die Bordnetzentwicklung gelten"
- "Deep research: What are the current approval workflows for AWS changes across BPLUS and Confluence?"

The agent loads `skill-deep-research` from the AGENTS.md dispatch table.

## What Happens

1. **Research Brief** — The agent structures your question into a formal brief with search terms, candidate systems, and constraints
2. **Research Plan** — A prioritized list of leads (2–15 entries) to investigate, with depth control (shallow/standard/deep)
3. **User Checkpoint** — The agent presents brief + plan and waits for your confirmation before visiting any page. You can modify leads, adjust priorities, or change depth.
4. **Iterative Research** — The agent visits sources one by one, extracts findings, and derives follow-up leads. All browser work is delegated to `skill-browse-intranet`. Interim updates every 10 steps.
5. **Evidence Collection** — Each finding is graded (A/B/C/D confidence) and recorded
6. **Final Report** — Structured answer with evidence, contradictions, and open questions

## Output Files

After completion, find the results at:

```
userdata/research_output/YYYYMMDD_[Title]/
├── research_tracking.md   # Step-by-step search trail
└── research_report.md     # Final structured report
```

## Key Constraints

- **Read-only by default** — no form submissions or data modifications unless explicitly requested
- **Depth control** — `shallow` (max 10 steps, known URLs only), `standard` (max 25 steps, default), `deep` (max 50 steps, includes Crawl4AI if available)
- **No throttling** between page visits
- **User can steer mid-research** — add URLs, change direction, adjust plan inline
- **Crawl4AI** (optional) — for broad discovery across many pages; skill works without it

## Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `.agents/skills/skill-deep-research/SKILL.md` | Create | Skill definition with workflow, triggers, delegation rules |
| `AGENTS.md` | Modify | Add routing entry for deep research trigger patterns |
| `CLAUDE.md` | Modify | Mirror routing entry (CLAUDE.md mirrors AGENTS.md for Claude Code) |
| `README.md` | Modify | Add skill to skills table (per constitution Development Workflow) |
