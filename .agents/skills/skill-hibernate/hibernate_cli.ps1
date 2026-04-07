# CLI script for scheduling a one-time hibernate via Windows Scheduled Task.
# Usage:
#   hibernate_cli.ps1 -Hour 2 -Minute 0       # Plan hibernate at 02:00
#   hibernate_cli.ps1 -Status                  # Show current plan
#   hibernate_cli.ps1 -Delete                  # Remove planned hibernate

param(
    [int]$Hour = -1,
    [int]$Minute = 0,
    [switch]$Status,
    [switch]$Delete
)

$taskName = "PlannedHibernate"
$shutdownExe = Join-Path $env:WINDIR "System32\shutdown.exe"
$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

if ($Delete) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Hibernate-Planung geloescht."
    exit 0
}

if ($Status) {
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($task) {
        $info = Get-ScheduledTaskInfo -TaskName $taskName
        Write-Host "Naechster Lauf: $($info.NextRunTime.ToString('dd.MM.yyyy HH:mm'))"
    } else {
        Write-Host "Kein Hibernate geplant."
    }
    exit 0
}

if ($Hour -lt 0 -or $Hour -gt 23) {
    Write-Host "Fehler: -Hour muss zwischen 0 und 23 liegen."
    exit 1
}

$scheduled = Get-Date -Hour $Hour -Minute $Minute -Second 0
if ($scheduled -le (Get-Date).AddMinutes(1)) {
    $scheduled = $scheduled.AddDays(1)
}

$action  = New-ScheduledTaskAction -Execute $shutdownExe -Argument "/h"
$trigger = New-ScheduledTaskTrigger -Once -At $scheduled
$principal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal `
    -Description "Versetzt den Rechner zu einem geplanten Zeitpunkt in den Ruhezustand." `
    -Force | Format-List TaskName, State

Write-Host "Hibernate geplant fuer: $($scheduled.ToString('dd.MM.yyyy HH:mm'))"
