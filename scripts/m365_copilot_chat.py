"""M365 Copilot Chat — Stub (Workflow laeuft komplett ueber Playwright MCP).

Die M365-Copilot-Web-App nutzt intern Teams Trouter WebSocket statt eines
REST-Endpoints. Deshalb laeuft der gesamte Chat-Workflow ueber Playwright
DOM-Interaktion (type → submit → wait → snapshot). Dieses Script wird
aktuell nicht benoetigt — der Skill orchestriert alles ueber MCP-Tools.

Siehe: .agents/skills/skill-m365-copilot-chat/SKILL.md
"""

from __future__ import annotations