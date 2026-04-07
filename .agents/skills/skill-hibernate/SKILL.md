---
name: skill-hibernate
description: Rechner zu einer bestimmten Uhrzeit in den Ruhezustand (Hibernate) versetzen. Nutze diesen Skill wenn der User den Rechner zeitgesteuert herunterfahren oder in Hibernate schicken moechte.
---

# Skill: Geplanter Hibernate

Plant einen Windows Scheduled Task, der den Rechner zu einer bestimmten Uhrzeit in den **Ruhezustand (Hibernate)** versetzt.

## Wann verwenden?

- Der User moechte den Rechner zu einer bestimmten Uhrzeit **herunterfahren** oder **in Hibernate** schicken
- Der User erwaehnt **Ruhezustand**, **Hibernate**, **Rechner ausschalten** oder **Feierabend**
- Der User moechte eine bestehende Planung **pruefen** oder **loeschen**

## Technische Details

- **Task-Name:** `PlannedHibernate`
- **Befehl:** `shutdown.exe /h` (Hibernate)
- **Trigger:** Einmalig (`-Once`) zur gewaehlten Uhrzeit
- Falls die Uhrzeit heute schon vorbei ist, wird automatisch der naechste Tag genommen

## CLI-Script (fuer Agent)

Alle Aktionen laufen ueber ein einziges Script mit Parametern — **ein Einzeiler-Aufruf genuegt**:

```
<WORKSPACE>\.agents\skills\skill-hibernate\hibernate_cli.ps1
```

### Hibernate planen

```powershell
powershell -ExecutionPolicy Bypass -File "<WORKSPACE>\.agents\skills\skill-hibernate\hibernate_cli.ps1" -Hour {STUNDE} -Minute {MINUTE}
```

> `{STUNDE}` und `{MINUTE}` durch die gewuenschte Uhrzeit ersetzen (z.B. `-Hour 2 -Minute 0` fuer 02:00 Uhr).

### Status pruefen

```powershell
powershell -ExecutionPolicy Bypass -File "<WORKSPACE>\.agents\skills\skill-hibernate\hibernate_cli.ps1" -Status
```

### Planung loeschen

```powershell
powershell -ExecutionPolicy Bypass -File "<WORKSPACE>\.agents\skills\skill-hibernate\hibernate_cli.ps1" -Delete
```

## GUI-Variante

Im Workspace liegt ein GUI-Script fuer interaktive Nutzung:

```powershell
powershell -ExecutionPolicy Bypass -File "<WORKSPACE>\.agents\skills\skill-hibernate\hibernate_scheduler.ps1"
```

Alternativ als VS Code Task: **"Windows: Hibernate Scheduler"**
