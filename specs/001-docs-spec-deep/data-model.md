# Data Model: Deep Research Orchestration Skill

**Date**: 2026-03-19 | **Feature**: 001-docs-spec-deep

> Note: This skill is prompt-based (SKILL.md). The "data model" describes the logical structures the agent maintains in-conversation and writes to markdown output files — not database tables or code classes.
>
> **Language convention**: Internal entity fields (Lead, Evidence Item, Research State) use English identifiers. Output-facing fields in the Tracking Entry and output templates use German, matching the user-facing markdown files.

## Entities

### Research Brief

The structured formulation of the user's research question. Created once at the start of each research task.

| Field | Type | Description |
|-------|------|-------------|
| topic | text | Core subject of the research question |
| goal | text | What the user wants to learn or decide |
| known_start_urls | list[url] | URLs the user provided or that are obvious starting points |
| candidate_systems | list[text] | Portals/systems likely to contain relevant information |
| search_terms | list[text] | Primary search keywords |
| synonyms | list[text] | Alternative spellings, abbreviations, related terms |
| constraints | list[text] | Scope limits, exclusions, time boundaries |
| output_format | text | What format/depth the user expects (summary, detailed report, comparison) |
| depth | enum | shallow / standard / deep — guides how many leads to pursue |

**Identity**: One per research task. No persistence beyond the conversation.

### Research Plan

A prioritized queue of leads to investigate.

| Field | Type | Description |
|-------|------|-------------|
| leads | list[Lead] | Ordered list of investigation targets |
| stop_criteria | list[text] | Conditions under which research should end |

**Lifecycle**: Created after the brief. Updated after each research loop (new leads added, completed leads removed).

### Lead

A pointer to a potential information source.

| Field | Type | Description |
|-------|------|-------------|
| id | integer | Sequential identifier (1, 2, 3...) |
| kind | enum | portal_search, url, document, page, export_path |
| label | text | Human-readable name for the lead |
| source | text | How this lead was discovered (e.g., "derived from Step 3") |
| priority | integer | 1 = highest priority |
| reason | text | Why this lead is worth investigating |
| status | enum | pending → in_progress → done / rejected |

**Identity**: Unique by `id` within a research task.
**State transitions**: `pending` → `in_progress` (when selected for investigation) → `done` (findings recorded) or `rejected` (not useful / inaccessible / duplicate).

**Status mapping (Lead → Tracking Entry)**:
- `in_progress` → `weiterverfolgt`
- `done` → `abgeschlossen`
- `rejected` → `verworfen`
- `pending` leads do not generate tracking entries.

### Evidence Item

A structured record of a relevant finding.

| Field | Type | Description |
|-------|------|-------------|
| id | text | E1, E2, E3... |
| title | text | Short title of the finding |
| url | url | Source page URL |
| source_system | text | Portal/system name (e.g., "Confluence VOBES", "BPLUS-NG") |
| summary | text | 1-3 sentence summary of what was found |
| key_facts | list[text] | Extracted factual statements |
| confidence | enum | A (primary source) / B (official secondary) / C (indirect) / D (weak/unconfirmed) |
| timestamp_hint | text | Date/version visible on the source, if any |
| notes | text | Agent observations about reliability, context |
| contradictions | list[text] | Conflicts with other evidence items (by ID) |

**Identity**: Unique by `id` within a research task.

### Tracking Entry

A numbered step in the search trail, written to `research_tracking.md`.

| Field | Type | Description |
|-------|------|-------------|
| step_no | integer | Sequential step number |
| url | url | Page visited |
| source_system | text | Portal/system name |
| reason_for_visit | text | Why this page was chosen |
| agent_note | text | 1-2 sentence observation about the page |
| actions_taken | list[text] | What the agent did (searched, clicked, read section X) |
| observations | list[text] | What was found or not found |
| relevance | enum | high / medium / low / none |
| confidence | enum | A / B / C / D |
| derived_leads | list[integer] | IDs of new leads discovered from this step |
| status | enum | weiterverfolgt / abgeschlossen / verworfen |

**Identity**: Unique by `step_no` within a research task. Maximum 50 per task.

### Research State (in-conversation)

Aggregate working state maintained by the agent during the research task. Not persisted to file.

| Field | Type | Description |
|-------|------|-------------|
| brief | Research Brief | The current research brief |
| plan | Research Plan | The current research plan |
| visited_urls | set[url] | All URLs already visited (for dedup) |
| visited_queries | set[text] | All search queries already executed (for dedup) |
| evidence_items | list[Evidence Item] | All collected evidence |
| tracking_entries | list[Tracking Entry] | All tracking steps |
| open_questions | list[text] | Questions that emerged during research |
| working_hypotheses | list[text] | Current best guesses being tested |
| step_counter | integer | Current step number (max 50) |

### Interim Update

A status snapshot provided to the user during long research tasks (>10 steps, per FR-017).

| Field | Type | Description |
|-------|------|-------------|
| step_count | integer | Current step number at time of update |
| findings_so_far | list[text] | Key findings collected up to this point |
| open_questions | list[text] | Unresolved questions |
| current_lead | text | Lead currently being pursued |
| next_step | text | Next planned action |

**Trigger**: Automatically generated after every 10th research step. Not persisted to file — delivered inline in the conversation.

## Relationships

```text
Research Brief  ──1:1──▶  Research Plan
Research Plan   ──1:N──▶  Lead
Lead            ──1:N──▶  Tracking Entry (one lead may generate multiple steps)
Tracking Entry  ──0:N──▶  Evidence Item (a step may produce zero or more findings)
Tracking Entry  ──0:N──▶  Lead (a step may derive new leads)
Evidence Item   ──0:N──▶  Evidence Item (contradictions reference other items)
```

## Output File Formats

### research_tracking.md

```markdown
# Deep Research Tracking

## Research Brief
- Thema: {topic}
- Ziel: {goal}
- Startpunkte: {known_start_urls}
- Suchbegriffe: {search_terms}
- Ausschlüsse: {constraints}

## Verlauf

### Schritt 1
- URL: {url}
- Quelle/Portal: {source_system}
- Grund: {reason_for_visit}
- Agenten-Hinweis: {agent_note}
- Aktion: {actions_taken}
- Gefunden: {observations}
- Relevanz: {relevance}
- Vertrauensgrad: {confidence}
- Folgepfade: {derived_leads}
- Status: {status}

### Schritt 2
...
```

### research_report.md

```markdown
# Deep Research Report: {topic}

## Kurzantwort
{1-3 sentence answer}

## Wichtigste Erkenntnisse
- {finding 1}
- {finding 2}

## Evidenz / Fundstellen
- [{confidence}] {title} — {url} — {summary}

## Unsicherheiten / Widersprüche
- {contradiction or uncertainty}

## Offene Punkte
- {open question}

## Tracking-Datei
- Pfad: userdata/research_output/YYYYMMDD_[Title]/research_tracking.md
```
