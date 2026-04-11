# HowTo für Notifys bei abschluss eines Agent-Chats

## Was geht nicht

In VS Code sind Hooks für Copilot Unternehmensseitig deaktiviert. No Way das hinzubekommen.

## Was geht

Man kann in der Agents.md oder im Memory eine Passage hinzufügen, dass bei jeder Fertigstellung IMMER ein notify.ps1 aufgerufen wird.

### Passage in Agents.md 

- Benachrichtigung: Bei Stop, Fehler, Userfrage oder wenn fertig IMMER `scripts/hooks/notify.ps1` ausfuehren. Parameter: `-Status done` (fertig/Userfrage) oder `-Status failed` (Fehler), `-Message "Kurze Zusammenfassung"`. Aufruf: `powershell -ExecutionPolicy Bypass -File C:\Daten\Python\vobes_agent_vscode\scripts\hooks\notify.ps1 -Status done|failed -Message "Was gemacht wurde"`

### Erfahrung damit 

Es funktioniert, allerding sbenötigt das Ausführen von Notify vom Agent Zeit, es müllt den Context/Chat zu und ist unzuverlässig. Bei FOlgefragen wird das vom Agent gerne vergessen.

## Codex

In CODEX sind hooks möglich. Sie müssen in .codex/config.toml angewiesen werden:

> notify = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "scripts\\hooks\\codex-notify.ps1"]

Das kann im Projekt sein oder in ~USER