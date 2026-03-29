# Feature Specification: Deep Research Orchestration Skill

**Feature Branch**: `001-docs-spec-deep`
**Created**: 2026-03-19
**Status**: Draft
**Input**: User description: "Create skill-deep-research — a meta-skill that orchestrates multi-step, multi-source research across web pages and internal portals, producing evidence-backed answers with a transparent search trail."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Complex Research Question (Priority: P1)

A user asks a complex question that cannot be answered from a single source — e.g., "Which VW internal portals document the approval process for new supplier onboarding?" The skill structures the question into a research brief, generates a research plan with prioritized leads, iteratively visits multiple portals/pages, collects evidence from each, and delivers a final report with sources, confidence levels, and a tracking file documenting every step.

**Why this priority**: This is the core value proposition — turning an open-ended question into a structured, evidence-backed answer across multiple sources. Without this, the skill has no reason to exist.

**Independent Test**: Can be fully tested by posing a multi-source research question and verifying that the skill produces a research brief, visits at least 3 different sources, collects evidence items, writes a tracking markdown file, and delivers a structured final report.

**Acceptance Scenarios**:

1. **Given** a user asks a research question requiring information from multiple portals, **When** the skill is triggered, **Then** it produces a structured research brief containing the question, goal, search terms, synonyms, and candidate systems before visiting any page.
2. **Given** a research brief exists, **When** the skill begins research, **Then** it generates a prioritized research plan with at least 2 leads ranked by expected relevance.
3. **Given** a research plan exists, **When** the skill executes research loops, **Then** it visits multiple sources, extracts findings, and records each step in a tracking markdown file.
4. **Given** evidence has been collected from multiple sources, **When** the research concludes, **Then** the skill produces a final report containing a short answer, key findings, evidence with confidence grades (A/B/C/D), uncertainties, and open questions.

---

### User Story 2 - Transparent Search Trail (Priority: P1)

A user wants to understand how the agent arrived at its conclusions. After the research completes, the user opens the tracking markdown file and can follow the exact search path: which pages were visited, why, what was found, and what follow-up actions were derived.

**Why this priority**: Transparency is a core requirement — without it, the user cannot trust or verify the research results. This is equally critical to the research itself.

**Independent Test**: Can be tested by running any research task and then reviewing the tracking file for completeness — every visited page must have a reason, agent note, findings, relevance assessment, and status.

**Acceptance Scenarios**:

1. **Given** the skill has completed a research task, **When** the user opens the tracking markdown file, **Then** each visited page has a numbered step entry with URL, source system, reason for visit, agent note, actions taken, observations, relevance, confidence grade, derived leads, and status.
2. **Given** a tracking file exists, **When** the user reads the agent notes, **Then** each note is a concise, work-related observation about the page (e.g., "This appears to be an overview page, not the primary source") — not verbose free-text.

---

### User Story 3 - Delegation to Browse-Intranet Skill (Priority: P2)

The deep research skill needs to open a specific portal page, search within it, and extract content. Instead of implementing browser interaction logic itself, it delegates these concrete actions to the existing `skill-browse-intranet` skill.

**Why this priority**: Clean delegation avoids code duplication and ensures that browser-level improvements in `skill-browse-intranet` automatically benefit deep research. Important for maintainability but secondary to the core research flow.

**Independent Test**: Can be tested by verifying that the deep research skill's definition contains no browser-specific instructions (no Playwright commands, no DOM selectors) and that all page interactions are performed via `skill-browse-intranet`.

**Acceptance Scenarios**:

1. **Given** the skill needs to interact with a web page, **When** it performs navigation, clicking, searching, or content extraction, **Then** it delegates these actions to `skill-browse-intranet` rather than defining its own browser instructions.
2. **Given** the skill definition file, **When** reviewed for browser-specific logic, **Then** no Playwright tool calls, DOM selectors, or JavaScript execution instructions are found within the deep research skill itself.

---

### User Story 4 - Broad Discovery via Crawl Backend (Priority: P3)

For research questions that require scanning many pages (e.g., finding all mentions of a topic across a portal), the skill uses Crawl4AI as a discovery backend to efficiently crawl seed URLs and return candidate pages, which are then prioritized and selectively investigated in detail.

**Why this priority**: This is a performance optimization for large-scale research. The core skill works without it (using only interactive browsing), but Crawl4AI enables significantly broader coverage with less time.

**Independent Test**: Can be tested by issuing a broad research question, verifying that the skill invokes a crawl backend for initial discovery, and that only the most relevant candidate pages are then investigated interactively.

**Acceptance Scenarios**:

1. **Given** a research plan includes broad portal scanning, **When** the skill executes discovery, **Then** it uses the crawl backend to collect candidate pages from seed URLs rather than visiting each page interactively.
2. **Given** a crawl returns many candidate pages, **When** the skill prioritizes them, **Then** only the top-ranked candidates are investigated in detail via `skill-browse-intranet`.

---

### User Story 5 - Read-Only Safety Default (Priority: P2)

The skill operates in read-only mode by default. It reads, searches, navigates, and extracts — but does not submit forms, trigger exports, or modify data unless the user's research question explicitly requires and authorizes such an action.

**Why this priority**: Safety guardrails are essential for an autonomous research agent operating across internal portals. Prevents accidental side effects.

**Independent Test**: Can be tested by reviewing the skill definition for explicit read-only defaults and by running a research task and verifying no write actions occur unless explicitly requested.

**Acceptance Scenarios**:

1. **Given** a standard research question, **When** the skill executes research, **Then** it only performs read/navigate/search/extract actions — no form submissions, no exports, no data modifications.
2. **Given** a research question that explicitly requires triggering an export, **When** the skill encounters the export step, **Then** it clearly names the action and limits it to the minimum necessary scope.

---

### Edge Cases

- What happens when all leads are exhausted without finding a satisfactory answer? The skill must still produce a final report documenting what was searched, what was not found, and suggesting alternative approaches.
- What happens when a visited page requires authentication or returns an error? The skill must log the failure in the tracking file, note the inaccessible source, and continue with remaining leads.
- What happens when contradictory evidence is found across sources? The skill must flag contradictions explicitly in the evidence collection and highlight them in the final report.
- What happens when the research question is too vague to generate meaningful search terms? The skill must ask the user for clarification before beginning research, rather than executing unfocused searches.
- What happens when a single source contains the complete answer early in the research? The skill should recognize sufficient evidence and conclude early via stop criteria, rather than exhausting all planned leads.
- What happens when the same URL appears as a lead from multiple sources? The skill must detect duplicates via visited-URL tracking and skip redundant visits.
- What happens when Crawl4AI fails or times out during broad discovery? The skill must pause, inform the user of the failure, and ask whether to retry the crawl or fall back to interactive browsing for the affected leads.
- What happens when Playwright MCP tools are not available (e.g., Plan mode, no Chrome extension)? The skill must verify MCP availability before starting research, display a clear error message naming the missing prerequisite, and abort the task.
- What happens when the user wants to modify the research plan mid-execution (e.g., add a URL, change direction)? The skill must accept inline corrections, update the research plan accordingly, and continue from the adjusted state without restarting.
- What happens when the user provides additional context or URLs after research has started? The skill must incorporate them as new high-priority leads in the current plan.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST generate a structured research brief from the user's question, containing at minimum: topic, goal, known start URLs, candidate systems, search terms, synonyms, constraints, output format, and research depth (shallow/standard/deep) to guide how many leads to pursue.
- **FR-001a**: Research depth MUST influence the scope of investigation: `shallow` limits the plan to known start URLs and max 10 research steps; `standard` allows discovery of new leads up to 25 steps; `deep` enables broad discovery (including Crawl4AI if available) up to the hard cap of 50 steps. Default depth is `standard`.
- **FR-002**: System MUST produce a prioritized research plan before beginning any page visits, listing leads ranked by expected relevance with reasons for each priority. The initial plan MUST contain between 2 and 15 leads.
- **FR-002a**: After generating the research brief and plan, the system MUST present them to the user and wait for confirmation before beginning any page visits. The user may modify the brief, add/remove leads, or adjust priorities before approving.
- **FR-003**: System MUST execute research in iterative loops, where each loop selects the next lead, visits the source, extracts content, assesses relevance, derives follow-up leads, and updates the research state.
- **FR-003a**: System MUST accept inline user corrections during active research (e.g., new URLs, changed direction, additional context). Corrections MUST be incorporated as high-priority leads or plan adjustments without restarting the research task.
- **FR-004**: System MUST record each relevant finding as a structured evidence item containing: title, URL, source system, summary, key facts, confidence grade (A/B/C/D), timestamp hint, notes, and contradictions.
- **FR-005**: System MUST maintain a tracking markdown file that documents the complete search path with numbered steps, each containing: URL, source system, reason for visit, agent note, actions taken, observations, relevance assessment, confidence grade, derived leads, and status. The tracking file and all research output MUST be stored in `userdata/research_output/YYYYMMDD_[Title]/` relative to the repo root, with the directory auto-created per research task.
- **FR-006**: System MUST produce a structured final report containing: short answer, key findings, evidence with confidence grades, uncertainties/contradictions, open questions, and a reference to the tracking file.
- **FR-007**: System MUST delegate all concrete browser interactions (navigation, clicking, searching, content extraction, screenshots) to `skill-browse-intranet` and not duplicate browser-level logic.
- **FR-008**: System MUST track visited URLs and executed search queries to prevent redundant visits and avoid infinite loops.
- **FR-009**: System MUST apply stop criteria to end research when: the question is sufficiently answered, no high-value leads remain, further steps would only produce redundancy, or the step cap for the selected depth is reached (see FR-001a).
- **FR-010**: System MUST operate in read-only mode by default, performing only read/navigate/search/extract actions unless the user explicitly requires and authorizes write actions.
- **FR-011**: System MUST support integration with a crawl backend (Crawl4AI) for broad discovery across many pages, returning candidate URLs for selective detailed investigation. If the crawl backend fails (timeout, crash, connection error), the system MUST pause and ask the user whether to retry the crawl or fall back to interactive browsing via `skill-browse-intranet` for the affected leads.
- **FR-012**: System MUST apply lead prioritization logic, favoring leads that point to primary sources, have high topical relevance, promise new information, or are corroborated by multiple sources.
- **FR-013**: System MUST demote leads that are redundant, yield only weak/outdated hints, bring no new information, or lead only to generic overview pages.
- **FR-014**: System MUST flag contradictory evidence explicitly and include contradictions in the final report.
- **FR-015**: System MUST handle inaccessible pages gracefully by logging the failure and continuing with remaining leads.
- **FR-016**: System MUST verify Playwright MCP tool availability before starting any research task. If MCP tools are unavailable, the system MUST display a clear error message naming the missing prerequisite and abort the task without partial execution.
- **FR-017**: System MUST provide interim status updates to the user during research tasks that exceed 10 steps. Each interim update MUST contain: findings so far, open questions, current lead being pursued, and next planned step.

### Key Entities

- **Research Brief**: The structured formulation of the user's research question, including topic, goal, search terms, synonyms, candidate systems, constraints, and output format. Drives the entire research process.
- **Research Plan**: A prioritized list of leads to investigate, generated before research begins and updated as new leads emerge. Each lead has a type, target, priority, reason, and status.
- **Lead**: A pointer to a potential information source (portal search, URL, document, page, export path). Has a lifecycle: pending → in_progress → done/rejected. Carries priority and reason.
- **Evidence Item**: A structured record of a relevant finding from a specific source. Includes title, URL, source system, summary, key facts, confidence grade (A-D), timestamp hint, notes, and any contradictions.
- **Tracking Entry**: A numbered step in the search trail documenting a single research action — URL visited, reason, agent note, what was done, what was found, relevance, confidence, derived follow-ups, and status.
- **Research State**: The aggregate state of an ongoing research task — visited URLs, executed queries, pending/completed/rejected leads, evidence items, open questions, working hypotheses, and tracking entries.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For a research question spanning 3+ sources, the skill produces a final report with evidence from at least 3 distinct sources, each graded by confidence level.
- **SC-002**: The tracking markdown file contains a numbered entry for every page visited during research, with no gaps in the search trail.
- **SC-003**: 90% of research tasks complete without the user needing to manually guide the agent to specific pages — the skill autonomously discovers and follows relevant leads.
- **SC-004**: Research tasks that previously required 10+ manual browse-intranet invocations can be completed with a single deep-research invocation.
- **SC-005**: No browser-level logic (Playwright commands, DOM selectors, JavaScript execution) exists in the deep research skill definition — 100% delegation to browse-intranet.
- **SC-006**: The final report explicitly identifies contradictions or uncertainties found during research in at least 80% of cases where conflicting information exists.
- **SC-007**: Duplicate URL visits occur in fewer than 5% of research tasks, demonstrating effective redundancy avoidance.
- **SC-008**: The skill produces a usable research brief and plan within the first 2 interactions, before any page is visited.

## Trigger Differentiation

**`skill-deep-research`** is triggered when the user's request implies multi-source investigation:
- Open-ended research questions ("Recherchiere...", "Untersuche systematisch...", "Deep research:...")
- Questions that cannot be answered from a single page or portal
- Requests for evidence-backed answers with source comparison

**`skill-browse-intranet`** remains the correct choice for:
- Direct page access ("Öffne...", "Geh auf...")
- Single-page interactions (fill form, click, extract specific data)
- Known-URL navigation without research context

When in doubt: if the user's intent requires visiting **multiple unknown sources** to build an answer, route to `skill-deep-research`. If the user names a **specific page or action**, route to `skill-browse-intranet`.

## Clarifications

### Session 2026-03-19

- Q: What is the maximum number of research steps per task? → A: Hard cap of 50 research steps. Stop criteria still apply and may end tasks earlier.
- Q: Where are tracking and output files stored? → A: Under `userdata/research_output/YYYYMMDD_[Title]/` relative to repo root. Directory is auto-created per research task with date prefix and a short title slug.
- Q: Should page visits be throttled to avoid triggering portal rate limits? → A: No throttling. Execute at full speed without delays between page visits.
- Q: What is the canonical skill name? → A: `skill-deep-research` (hyphens), consistent with existing project conventions (`skill-browse-intranet`, `skill-knowledge-bordnetz-vobes`). Note: This deviates from the constitution's `skill-{domain}-{capability}` pattern (no domain segment), following the same precedent as `skill-browse-intranet` and `skill-hibernate`.
- Q: What happens when Crawl4AI fails mid-research? → A: Pause and ask the user whether to retry the crawl or fall back to interactive browsing for those leads.

## Assumptions

- The existing `skill-browse-intranet` skill is stable and supports all necessary browser interactions (navigate, search, click, read, extract, screenshot).
- Crawl4AI is available or can be made available as an installable dependency for the crawl backend. For V1, the skill can function without Crawl4AI by relying solely on interactive browsing via `skill-browse-intranet`.
- The skill operates within the user's existing browser session/authentication context — it does not handle login flows independently.
- For V1, two output files per research task: `research_tracking.md` (step-by-step search trail) and `research_report.md` (final structured report). Both are stored in the same output directory.
- Tracking granularity for V1 is one entry per meaningful research step / analyzed page, not per individual click.
- Persistence and resume capabilities are out of scope for V1 but the design should not preclude them.
- Agent notes in the tracking file are short, work-related observations (1-2 sentences) — not verbose chain-of-thought dumps.
- No throttling or rate limiting between page visits. The skill executes at full speed. If portals enforce their own rate limits, the skill handles resulting errors via FR-015 (graceful failure logging).
- The skill is defined as a SKILL.md file at `.agents/skills/skill-deep-research/SKILL.md`, following the constitution-mandated location and naming convention (hyphens, not underscores). A junction to `.claude/skills/` provides Claude Code compatibility.
