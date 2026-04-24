# Skill-Routing: Redundanz zwischen AGENTS.md und Skills-System

**Datum:** 2026-04-24

## Befund

Die Skill-Pflicht-Regeln in `AGENTS.md` (z.B. `→ PFLICHT: Skill $skill-coding laden und befolgen`) sind **teilweise redundant** mit dem eingebauten Skills-System von VS Code Copilot.

### Was das Skills-System bereits liefert

Das System-Prompt enthält eine generische Blocking-Regel:

> *"BLOCKING REQUIREMENT: When a skill applies to the user's request, you MUST load and read the SKILL.md file IMMEDIATELY as your first action, BEFORE generating any other response."*

Jeder Skill hat eine `<description>` mit Trigger-Keywords, die für das Matching verwendet wird.

### Was AGENTS.md zusätzlich bringt

| Aspekt | Wirkung |
|---|---|
| **Doppelte Verstärkung** | LLMs folgen Anweisungen zuverlässiger bei mehrfacher Erwähnung aus verschiedenen Quellen |
| **Attachment-Gewichtung** | AGENTS.md wird als Attachment geladen → höhere Aufmerksamkeit als generische System-Prompt-Sektionen |
| **Explizitere Trigger** | AGENTS.md kann Trigger auflisten, die in der Skill-Description anders formuliert sind |
| **Skill-Kombinationen** | AGENTS.md kann erzwingen, dass bei einem Trigger *mehrere* Skills geladen werden (z.B. Protokoll + Update-Confluence + Important-Pages) |
| **Fallback/Fehlerfälle** | AGENTS.md enthält Regeln für MCP-Nicht-Verfügbarkeit, Token-Probleme etc., die im Skill-YAML nicht abbildbar sind |

### Was NICHT über das Skill-System abbildbar ist

- Kein `mandatory: true` oder `pflicht: true` Feld im VS Code Skill-YAML-Schema
- Keine Möglichkeit, im YAML Multi-Skill-Ketten zu definieren (z.B. "lade auch Skill X wenn Skill Y aktiv")
- Keine Möglichkeit, Negativ-Regeln zu definieren ("NICHT verwenden für...")
- Keine Fehlerfallbehandlung (Container nicht gestartet, Token abgelaufen)

## Einschätzung

| Skill-Typ | Redundanz | Empfehlung |
|---|---|---|
| Einfache 1:1-Skills (z.B. skill-coding) | ~50% | Könnte entfernt werden, Compliance sinkt aber bei Grenzfällen leicht |
| Multi-Skill-Ketten (z.B. Protokoll → 3 Skills) | ~0% | MUSS in AGENTS.md bleiben, nicht anders abbildbar |
| Skills mit Fehlerfallregeln | ~0% | MUSS in AGENTS.md bleiben |
| Skills mit Negativ-Abgrenzung | ~10% | Besser in AGENTS.md, weil Description dafür schlecht geeignet ist |

## Fazit

Die AGENTS.md-Routing-Tabelle ist **nicht vollständig redundant**. Für einfache 1:1-Skills (ein Trigger → ein Skill) wäre eine Entfernung möglich, aber die Zuverlässigkeit sinkt bei ambigen Anfragen. Für Multi-Skill-Ketten, Fehlerfälle und Negativ-Abgrenzungen ist AGENTS.md **alternativlos**.

**Pragmatischer Ansatz:** Routing-Einträge in AGENTS.md beibehalten, da der Token-Overhead gering ist und die Compliance-Verbesserung den Preis rechtfertigt.
