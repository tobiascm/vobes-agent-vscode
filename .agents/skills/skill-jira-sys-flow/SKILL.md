---
name: skill-jira-sys-flow
description: Informationen aus dem Jira-Projekt und -Board SYS-FLOW zu SYS-AEMs in Systemschaltplänen abrufen. Nutze diesen Skill bei Fragen zu SYS-FLOW Tickets, Epics, Sprints, Board-Status oder Projektfortschritt. 
---

# Skill: Jira SYS-FLOW

Dieser Skill liefert Informationen aus dem Jira-Projekt **SYS-FLOW** (Projekt und Board).
SYS-FLOW nenne wir das Jira-Projekt, in dem wir die Systemschaltpläne (SYS-AEMs) verwalten. Hier werden alle Tickets, Epics, Stories und Tasks rund um die Entwicklung und Pflege der SYS-AEMs angelegt und bearbeitet.

## Wann verwenden?
- Der User fragt nach Tickets, Epics, Stories oder Tasks aus dem Projekt SYS-FLOW
- Der User moechte den Status des SYS-FLOW Boards sehen


TODO!

## Vorgehen
1. `mcp-atlassian` Jira-Tools verwenden:
   - `jira_search` mit JQL z.B. `project = "SYS-FLOW"` fuer Ticket-Suchen
   - `jira_get_issue` fuer einzelne Tickets
   - `jira_get_agile_boards` um das Board zu finden
   - `jira_get_board_issues` / `jira_get_sprint_issues` fuer Board-/Sprint-Uebersichten
2. Ergebnisse strukturiert und uebersichtlich praesentieren.

## Beispiel-JQL-Abfragen
- Alle offenen Issues: `project = "SYS-FLOW" AND status != Done`
- Aktuelle Sprint-Issues: `project = "SYS-FLOW" AND sprint in openSprints()`
- Bestimmtes Epic: `project = "SYS-FLOW" AND issuetype = Epic`