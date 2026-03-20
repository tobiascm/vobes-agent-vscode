# Tasks: Deep Research Orchestration Skill

**Input**: Design documents from `/specs/001-docs-spec-deep/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, quickstart.md

**Tests**: No automated tests — this is a prompt-based skill (SKILL.md). Validation is end-to-end in agent mode.

**Organization**: Tasks are grouped by user story to enable incremental implementation of SKILL.md sections. Each user story adds specific sections to the single file `.agents/skills/skill-deep-research/SKILL.md`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Skill definition**: `.agents/skills/skill-deep-research/SKILL.md`
- **Routing files**: `AGENTS.md`, `CLAUDE.md` (mirror)
- **Output directory**: `userdata/research_output/YYYYMMDD_[Title]/` (auto-created at runtime)

---

## Phase 1: Setup

**Purpose**: Create skill directory and SKILL.md skeleton

- [x] T001 Create skill directory `.agents/skills/skill-deep-research/`
- [x] T002 Create SKILL.md with YAML frontmatter (`name: skill-deep-research`, `description: ...`) and empty section headers following the pattern from `skill-browse-intranet/SKILL.md`. Sections: Wann verwenden, Wann NICHT verwenden, Voraussetzungen, Workflow, Ausgabeformat, Sicherheitsregeln. File: `.agents/skills/skill-deep-research/SKILL.md`

---

## Phase 2: Foundational (Trigger & Routing Skeleton)

**Purpose**: Define when the skill is triggered and when it is NOT used. MUST complete before user story work.

- [x] T003 Write "Wann verwenden?" section with trigger patterns from spec.md Trigger Differentiation: open-ended research questions ("Recherchiere...", "Untersuche systematisch...", "Deep research:..."), multi-source investigation, evidence-backed answer requests. File: `.agents/skills/skill-deep-research/SKILL.md`
- [x] T004 Write "Wann NICHT verwenden?" section with delegation table: single-page access → `skill-browse-intranet`, Confluence/Jira → `mcp-atlassian`, known-URL navigation → `skill-browse-intranet`. Include the decision rule from spec.md: multiple unknown sources → deep-research; specific page/action → browse-intranet. File: `.agents/skills/skill-deep-research/SKILL.md`
- [x] T005 Write "Voraussetzungen" section: Playwright MCP must be active, `skill-browse-intranet` must be available, `userdata/` directory must exist. File: `.agents/skills/skill-deep-research/SKILL.md`

**Checkpoint**: Skill skeleton with trigger logic is in place. `.claude/skills/` junction makes it visible to Claude Code automatically.

---

## Phase 3: User Story 1 — Complex Research Question (Priority: P1) 🎯 MVP

**Goal**: The core research workflow: user question → research brief → research plan → user checkpoint → iterative research loops → evidence collection → final report.

**Independent Test**: Pose a multi-source research question in agent mode. Verify: (1) structured brief is generated with all fields, (2) plan with 2+ leads is presented for confirmation, (3) after approval, sources are visited iteratively, (4) evidence items are collected with confidence grades, (5) final report is structured with short answer, findings, evidence, contradictions, and open questions.

### Implementation for User Story 1

- [x] T006 [US1] Write "Phase A: Research Brief" workflow section covering FR-001 and FR-001a. Define how the agent structures the user's question into a brief with all data-model fields: topic, goal, known_start_urls, candidate_systems, search_terms, synonyms, constraints, output_format, depth. Include depth semantics: `shallow` = max 10 steps / known URLs only; `standard` = max 25 steps / new lead discovery (default); `deep` = max 50 steps / broad discovery including Crawl4AI. File: `.agents/skills/skill-deep-research/SKILL.md`
- [x] T007 [US1] Write "Phase B: Rechercheplan" workflow section covering FR-002 and FR-002a. Define plan generation: 2–15 leads with priority ranking, lead kinds (portal_search, url, document, page, export_path), stop criteria. Include USER CHECKPOINT: present brief + plan to user, wait for confirmation before visiting any page. User may modify leads, adjust priorities, or change depth. File: `.agents/skills/skill-deep-research/SKILL.md`
- [x] T008 [US1] Write "Phase C: Iterativer Research Loop" workflow section covering FR-003, FR-003a, FR-008, FR-009. Define loop: (1) select highest-priority pending lead, (2) delegate page visit to `skill-browse-intranet`, (3) extract content, (4) assess relevance, (5) derive follow-up leads, (6) update research state. Include dedup (visited_urls, visited_queries), stop criteria (question answered / no high-value leads / redundancy / step cap per depth), and mid-research user interaction rules (accept inline corrections, new URLs, direction changes per FR-003a — incorporate as high-priority leads without restarting). File: `.agents/skills/skill-deep-research/SKILL.md`
- [x] T009 [US1] Write "Phase D: Evidenzkonsolidierung" section covering FR-004, FR-012, FR-013, FR-014. Define evidence item structure (id, title, url, source_system, summary, key_facts, confidence A/B/C/D, timestamp_hint, notes, contradictions). Include lead prioritization rules (primary source, topical relevance, new info, multi-source corroboration) and demotion rules (redundant, weak/outdated, generic overview). Include contradiction flagging logic. File: `.agents/skills/skill-deep-research/SKILL.md`
- [x] T010 [US1] Write "Phase E: Abschlussbericht" section covering FR-006. Define report template: Kurzantwort (1-3 sentences), Wichtigste Erkenntnisse, Evidenz/Fundstellen with confidence grades, Unsicherheiten/Widersprueche, Offene Punkte, Tracking-Datei reference. Report written to `userdata/research_output/YYYYMMDD_[Title]/research_report.md`. File: `.agents/skills/skill-deep-research/SKILL.md`
- [x] T011 [US1] Write "Zwischenstand" section covering FR-017. Define interim status update format delivered inline every 10 research steps: findings so far, open questions, current lead being pursued, next planned step. Reference Interim Update entity from data-model. File: `.agents/skills/skill-deep-research/SKILL.md`

**Checkpoint**: Core research workflow is complete in SKILL.md. Skill can execute a full research cycle (brief → plan → loops → evidence → report) using `skill-browse-intranet` for page visits.

---

## Phase 4: User Story 2 — Transparent Search Trail (Priority: P1)

**Goal**: Every research step is documented in a tracking markdown file that allows users to follow the exact search path.

**Independent Test**: Run any research task, then open `userdata/research_output/YYYYMMDD_[Title]/research_tracking.md`. Verify: every visited page has a numbered step entry with URL, source system, reason, agent note, actions, observations, relevance, confidence, derived leads, and status. No gaps in numbering.

### Implementation for User Story 2

- [x] T012 [US2] Write tracking file format section defining the full "Schritt" template. Each step must include all Tracking Entry fields from data-model: step_no, URL, Quelle/Portal, Grund, Agenten-Hinweis, Aktion, Gefunden, Relevanz (high/medium/low/none), Vertrauensgrad (A/B/C/D), Folgepfade, Status (weiterverfolgt/abgeschlossen/verworfen). Include Lead→Tracking status mapping. File: `.agents/skills/skill-deep-research/SKILL.md`
- [x] T013 [US2] Write agent note guidelines: 1-2 sentences, work-related observations only (e.g., "Diese Seite wirkt wie eine Uebersichtsseite, nicht wie die Primaerquelle"), no verbose chain-of-thought. Reference examples from spec.md. File: `.agents/skills/skill-deep-research/SKILL.md`
- [x] T014 [P] [US2] Write output file section defining both output files and the directory convention. Tracking file header template (from data-model: Thema, Ziel, Startpunkte, Suchbegriffe, Ausschluesse) + report file template. Directory: `userdata/research_output/YYYYMMDD_[Title]/` with auto-creation. Include file naming examples (e.g., `20260319_supplier-onboarding-process/`). File: `.agents/skills/skill-deep-research/SKILL.md`

**Checkpoint**: Tracking format is fully defined. Research tasks produce both `research_tracking.md` and `research_report.md` with complete search trails.

---

## Phase 5: User Story 3 — Delegation to Browse-Intranet (Priority: P2)

**Goal**: All browser interactions are delegated to `skill-browse-intranet`. No Playwright commands, DOM selectors, or JavaScript execution in the deep research SKILL.md.

**Independent Test**: Review SKILL.md for zero occurrences of Playwright tool names (`mcp_playwright_*`), DOM selectors, JavaScript execution, or browser-specific instructions. All page interactions must reference `skill-browse-intranet` by name.

### Implementation for User Story 3

- [x] T015 [US3] Write "Delegation an skill-browse-intranet" section covering FR-007. Define: (1) which actions are delegated (navigate, click, search, read, extract, screenshot), (2) how to load the skill (via standard skill dispatch), (3) explicit prohibition: SKILL.md MUST NOT contain Playwright tool calls, DOM selectors, CSS selectors, JavaScript execution, or browser-specific instructions. All browser work MUST go through `skill-browse-intranet`. File: `.agents/skills/skill-deep-research/SKILL.md`
- [x] T016 [US3] Write MCP availability check section covering FR-016. Before starting any research task: verify Playwright MCP tools are available. If unavailable, display error message naming the missing prerequisite and abort without partial execution. Include the error message template from CLAUDE.md Plan-Modus pattern. File: `.agents/skills/skill-deep-research/SKILL.md`

**Checkpoint**: Delegation rules are explicit. SKILL.md contains zero browser-level logic.

---

## Phase 6: User Story 5 — Read-Only Safety Default (Priority: P2)

**Goal**: Skill operates in read-only mode by default. No write actions unless explicitly authorized by the user.

**Independent Test**: Review SKILL.md for explicit read-only default. Run a standard research question and verify no form submissions, exports, or data modifications occur.

### Implementation for User Story 5

- [x] T017 [US5] Write "Sicherheits- und Betriebsregeln" section covering FR-010 and FR-015. Define: (1) default mode = read-only (read, search, navigate, extract only), (2) forbidden actions (delete, approve, modify master data, mass send), (3) exception rules for explicit write requests (action must be named, scoped to minimum), (4) graceful failure handling for inaccessible pages (log failure in tracking, note inaccessible source, continue with remaining leads). File: `.agents/skills/skill-deep-research/SKILL.md`

**Checkpoint**: Safety guardrails are defined. Skill cannot accidentally perform write actions.

---

## Phase 7: User Story 4 — Broad Discovery via Crawl Backend (Priority: P3)

**Goal**: Optional Crawl4AI integration for broad portal scanning, returning candidate URLs for selective investigation.

**Independent Test**: Issue a "deep" research question. Verify: if Crawl4AI is available, the skill invokes it for initial discovery and only investigates top-ranked candidates interactively. If Crawl4AI is unavailable, skill falls back to browse-intranet without error.

### Implementation for User Story 4

- [x] T018 [US4] Write optional "Crawl4AI Integration" section covering FR-011. Mark clearly as OPTIONAL (skill fully functional without it). Define: (1) when to use — depth=deep or broad portal scanning needed, (2) seed-URL crawling workflow, (3) candidate prioritization from crawl results, (4) selective detailed investigation via browse-intranet for top candidates only, (5) failure handling — pause on crawl failure, ask user to retry or fall back to interactive browsing. File: `.agents/skills/skill-deep-research/SKILL.md`

**Checkpoint**: Crawl4AI section is present as optional enhancement. Core skill works without it.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Edge cases, routing registration, README update, and final validation.

- [x] T019 Write edge case handling section covering all 10 edge cases from spec.md: exhausted leads, auth errors, contradictions, vague questions, early completion, duplicate URLs, Crawl4AI failure, MCP unavailability, mid-research plan changes, ad-hoc URL additions. File: `.agents/skills/skill-deep-research/SKILL.md`
- [x] T020 [P] Add routing entry for `skill-deep-research` to `AGENTS.md`. Use-case pattern: "Deep Research | Recherchiere systematisch | Untersuche mehrere Quellen | Multi-Source-Recherche | evidence-backed research across portals". Include trigger: `$skill-deep-research`. File: `AGENTS.md`
- [x] T021 [P] Mirror identical routing entry in `CLAUDE.md`. Must stay in sync with AGENTS.md per research.md R7a. File: `CLAUDE.md`
- [x] T022 [P] Update README.md skills table to include `skill-deep-research` with short description per constitution Development Workflow. File: `README.md`
- [x] T023 Validate SKILL.md completeness against spec.md: verify all 20 FRs (FR-001 through FR-017 including FR-001a, FR-002a, and FR-003a) are addressed, zero Playwright/DOM/JS instructions present (SC-005), all 6 data-model entities referenced, both output file templates included, and all 10 edge cases covered. File: `.agents/skills/skill-deep-research/SKILL.md`
- [ ] T024 Run quickstart.md end-to-end validation: trigger skill with a sample research question, verify skill loads from AGENTS.md dispatch, brief+plan generated and presented for confirmation, at least 3 sources visited, tracking file written to `userdata/research_output/`, final report produced with evidence grades.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup (T001, T002 must be complete)
- **US1 (Phase 3)**: Depends on Foundational — core workflow sections
- **US2 (Phase 4)**: Depends on US1 (tracking format builds on workflow) — but T014 can run in parallel
- **US3 (Phase 5)**: Depends on Foundational — can run in parallel with US1/US2
- **US5 (Phase 6)**: Depends on Foundational — can run in parallel with US1/US2/US3
- **US4 (Phase 7)**: Depends on US1 (extends the research loop with Crawl4AI)
- **Polish (Phase 8)**: Depends on all user stories being complete

### User Story Dependencies

- **US1 (P1)**: Can start after Foundational (Phase 2) — No dependencies on other stories
- **US2 (P1)**: Tightly coupled with US1 (tracking documents the research workflow) — best implemented immediately after US1
- **US3 (P2)**: Independent of US1/US2 — defines constraints, not workflow
- **US5 (P2)**: Independent of US1/US2/US3 — defines safety rules
- **US4 (P3)**: Depends on US1 (extends the research loop) — implement last

### Within Each User Story

- SKILL.md sections are additive — each task appends/inserts a section
- Earlier sections provide context for later sections
- No test-first approach (prompt-based skill, not code)

### Parallel Opportunities

- T003, T004, T005 are sequential (same file, additive sections)
- T020 + T021 + T022 can run in parallel (different files)
- US3 (Phase 5) and US5 (Phase 6) can run in parallel with US1/US2 if desired
- T014 (output files) can run in parallel with T012/T013 (tracking format)

---

## Parallel Example: User Story 1

```text
# Sequential within US1 (sections build on each other):
T006: Research Brief section
T007: Rechercheplan section (references brief)
T008: Research Loop section (references plan)
T009: Evidenzkonsolidierung section (references loop)
T010: Abschlussbericht section (references evidence)
T011: Zwischenstand section (references loop)
```

## Parallel Example: Polish Phase

```text
# These three modify different files — run in parallel:
T020: Add routing to AGENTS.md
T021: Mirror routing in CLAUDE.md
T022: Update README.md skills table
```

---

## Implementation Strategy

### MVP First (User Story 1 + 2 Only)

1. Complete Phase 1: Setup (T001–T002)
2. Complete Phase 2: Foundational (T003–T005)
3. Complete Phase 3: US1 — Core Research Workflow (T006–T011)
4. Complete Phase 4: US2 — Tracking Format (T012–T014)
5. **STOP and VALIDATE**: Test with a sample research question in agent mode
6. If MVP works → proceed to remaining stories

### Incremental Delivery

1. Setup + Foundational → Skill skeleton ready
2. Add US1 + US2 → Core research with tracking (MVP!)
3. Add US3 → Clean delegation enforced
4. Add US5 → Safety guardrails in place
5. Add US4 → Crawl4AI for broad discovery
6. Polish → Routing, README, final validation

### Single-Developer Strategy (recommended)

Since all tasks modify a single file (SKILL.md) plus 3 routing updates:

1. Build SKILL.md incrementally: Phase 1 → 2 → 3 → 4 → 5 → 6 → 7
2. After Phase 4 checkpoint: validate MVP end-to-end
3. After Phase 7: add routing (T020–T022) in parallel
4. Final validation (T023–T024)

---

## Notes

- All user story tasks target the same file: `.agents/skills/skill-deep-research/SKILL.md`
- [P] tasks within a phase = different sections, can be written in parallel
- [Story] label maps each task to its user story for traceability
- The `.claude/skills/` junction auto-exposes the skill to Claude Code — no separate copy needed
- Commit after each phase checkpoint for clean rollback points
- `userdata/research_output/` is auto-created at runtime by the skill — no setup task needed
