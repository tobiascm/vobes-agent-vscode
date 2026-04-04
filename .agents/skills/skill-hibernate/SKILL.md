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

## GUI-Variante

Im Workspace liegt ein GUI-Script fuer interaktive Nutzung:

```powershell
powershell -ExecutionPolicy Bypass -File "<WORKSPACE>\.agents\skills\skill-hibernate\hibernate_scheduler.ps1"
```

Alternativ als VS Code Task: **"Windows: Hibernate Scheduler"**

## CLI-Befehle (fuer Agent)

### Hibernate planen

```powershell
$taskName = "PlannedHibernate"
$shutdownExe = Join-Path $env:WINDIR "System32\shutdown.exe"
$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$scheduled = Get-Date -Hour {STUNDE} -Minute {MINUTE} -Second 0
if ($scheduled -le (Get-Date).AddMinutes(1)) { $scheduled = $scheduled.AddDays(1) }
$action = New-ScheduledTaskAction -Execute $shutdownExe -Argument "/h"
$trigger = New-ScheduledTaskTrigger -Once -At $scheduled
$principal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Description "Versetzt den Rechner zu einem geplanten Zeitpunkt in den Ruhezustand." -Force | Format-List TaskName, State
Write-Host "Hibernate geplant fuer: $($scheduled.ToString('dd.MM.yyyy HH:mm'))"
```

> `{STUNDE}` und `{MINUTE}` durch die gewuenschte Uhrzeit ersetzen (z.B. `3` und `0` fuer 03:00 Uhr).

### Status pruefen

```powershell
$task = Get-ScheduledTask -TaskName "PlannedHibernate" -ErrorAction SilentlyContinue
if ($task) {
    $info = Get-ScheduledTaskInfo -TaskName "PlannedHibernate"
    Write-Host "Naechster Lauf: $($info.NextRunTime.ToString('dd.MM.yyyy HH:mm'))"
} else {
    Write-Host "Kein Hibernate geplant."
}
```

### Planung loeschen

```powershell
Unregister-ScheduledTask -TaskName "PlannedHibernate" -Confirm:$false -ErrorAction SilentlyContinue
Write-Host "Hibernate-Planung geloescht."
```
