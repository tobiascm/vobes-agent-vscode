---
name: skill-coding
description: "Code analysieren, implementieren, refactoren, reviewen, debuggen. Gilt fuer alle Programmier- und Architekturaufgaben: neue Features, Bugfixes, Code-Reduktion, Skill-Entwicklung, Script-Erstellung. Sprachen: Python, PowerShell, allgemein. Trigger: implementiere, programmiere, code schreiben, refactore, analysiere Code, Code Review, Architekturvorschlag, Bugfix, neues Script, Skill erstellen, Skill aendern, Feature implementieren, Funktion schreiben, Code optimieren, Code reduzieren, debuggen."
---


# Coding

- Git Commit IMMER ueber Skill `$git-commit` ausfuehren, NIEMALS manuell `git commit` aufrufen.
- Git Push IMMER ueber Skill `$git-push` ausfuehren, NIEMALS manuell `git push` aufrufen.
- Dateiverschiebungen und Umbenennungen IMMER mit `git mv` ausfuehren, NIEMALS per `mv`, `Move-Item` oder manuelles Loeschen + Neuerstellen, außer datei ist unversioniert.

## Goals

- As less code as possible!
- If you habe a solution, always think again about the option with the least code!
- Produce an elegant, lean solution with a sound architecture.
- Provide **three alternative approaches**, then recommend one with a concise trade-off summary.
- Minimize code: prefer the smallest possible change and the fewest lines of code that achieve the goal; reduce existing code where safe. I want ultra slim code!
- I want maximum code reduction.
- Optimize for code reduction: delete/merge code when possible; avoid adding new abstractions unless they reduce total complexity.

## Evaluation criteria

- **Architecture**: clarity, separation of concerns, extensibility
- **Code quality**: prioritize **YAGNI**, **SOLID**, **KISS**
- **Effort**: implementation complexity / time

## Architecture & design

- Before implementing, propose 3 architecture variants. Don't prpose a varaiant that make no sense. For each variant, show a minimal “before → after” code snippet illustrating the change (keep it compact), list pros/cons, and rate YAGNI, SOLID, KISS, HC/LC, Effort. Finish with a comparison table using 1–5 stars per criterion. Use ★/☆ (1–5) for ratings in the final table. For Effort use 5 Stars for less effort and 0 Stars for high effort.
- Avoid over-engineering; implement only what is needed for the current task (YAGNI).
- Prefer simple composition over inheritance unless inheritance is clearly warranted.
- Keep functions small and single-purpose; avoid deep nesting by extracting helpers.
- Preserve public APIs unless explicitly asked to change them.
- Separate domain/business logic from I/O (database, network, UI) (light Clean Architecture).
- HC/LC (High cohesion, low coupling)