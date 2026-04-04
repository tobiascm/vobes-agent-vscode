# Windows GUI for scheduling a one-time hibernate at a specific time.

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$taskName = "PlannedHibernate"
$shutdownExe = Join-Path $env:WINDIR "System32\shutdown.exe"
$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

function Get-NextRunTime {
    param(
        [datetime]$SelectedTime
    )

    $now = Get-Date
    $scheduled = Get-Date -Hour $SelectedTime.Hour -Minute $SelectedTime.Minute -Second 0

    if ($scheduled -le $now.AddMinutes(1)) {
        $scheduled = $scheduled.AddDays(1)
    }

    return $scheduled
}

function Set-PlannedHibernate {
    param(
        [datetime]$SelectedTime
    )

    $scheduled = Get-NextRunTime -SelectedTime $SelectedTime
    $action = New-ScheduledTaskAction -Execute $shutdownExe -Argument "/h"
    $trigger = New-ScheduledTaskTrigger -Once -At $scheduled
    $principal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType Interactive -RunLevel Limited

    Register-ScheduledTask `
        -TaskName $taskName `
        -Action $action `
        -Trigger $trigger `
        -Principal $principal `
        -Description "Versetzt den Rechner zu einem geplanten Zeitpunkt in den Ruhezustand." `
        -Force | Out-Null

    return $scheduled
}

function Remove-PlannedHibernate {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
}

function Get-ExistingHibernateInfo {
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if (-not $task) {
        return $null
    }

    $info = Get-ScheduledTaskInfo -TaskName $taskName -ErrorAction SilentlyContinue
    if (-not $info) {
        return $null
    }

    return $info.NextRunTime
}

$form = New-Object System.Windows.Forms.Form
$form.Text = "Geplanten Hibernate setzen"
$form.Size = New-Object System.Drawing.Size(430, 220)
$form.StartPosition = "CenterScreen"
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false
$form.TopMost = $true

$descriptionLabel = New-Object System.Windows.Forms.Label
$descriptionLabel.Location = New-Object System.Drawing.Point(20, 20)
$descriptionLabel.Size = New-Object System.Drawing.Size(380, 40)
$descriptionLabel.Text = "Waehl eine Uhrzeit aus. Falls sie heute schon vorbei ist, wird der Hibernate fuer morgen geplant."
$form.Controls.Add($descriptionLabel)

$timeLabel = New-Object System.Windows.Forms.Label
$timeLabel.Location = New-Object System.Drawing.Point(20, 72)
$timeLabel.Size = New-Object System.Drawing.Size(120, 24)
$timeLabel.Text = "Uhrzeit:"
$form.Controls.Add($timeLabel)

$timePicker = New-Object System.Windows.Forms.DateTimePicker
$timePicker.Location = New-Object System.Drawing.Point(150, 68)
$timePicker.Size = New-Object System.Drawing.Size(120, 24)
$timePicker.Format = [System.Windows.Forms.DateTimePickerFormat]::Time
$timePicker.ShowUpDown = $true
$timePicker.Value = (Get-Date).AddHours(1)
$form.Controls.Add($timePicker)

$scheduleButton = New-Object System.Windows.Forms.Button
$scheduleButton.Location = New-Object System.Drawing.Point(20, 110)
$scheduleButton.Size = New-Object System.Drawing.Size(180, 32)
$scheduleButton.Text = "Hibernate planen"
$form.Controls.Add($scheduleButton)

$removeButton = New-Object System.Windows.Forms.Button
$removeButton.Location = New-Object System.Drawing.Point(220, 110)
$removeButton.Size = New-Object System.Drawing.Size(180, 32)
$removeButton.Text = "Planung loeschen"
$form.Controls.Add($removeButton)

$statusLabel = New-Object System.Windows.Forms.Label
$statusLabel.Location = New-Object System.Drawing.Point(20, 152)
$statusLabel.Size = New-Object System.Drawing.Size(380, 30)
$statusLabel.ForeColor = [System.Drawing.Color]::DarkGreen
$form.Controls.Add($statusLabel)

$refreshStatus = {
    $nextRunTime = Get-ExistingHibernateInfo
    if ($nextRunTime -and $nextRunTime -gt [datetime]::MinValue) {
        $statusLabel.ForeColor = [System.Drawing.Color]::DarkGreen
        $statusLabel.Text = "Aktive Planung: $($nextRunTime.ToString('dd.MM.yyyy HH:mm'))"
    } else {
        $statusLabel.ForeColor = [System.Drawing.Color]::DimGray
        $statusLabel.Text = "Keine aktive Planung vorhanden."
    }
}

$scheduleButton.Add_Click({
    try {
        $scheduled = Set-PlannedHibernate -SelectedTime $timePicker.Value
        $statusLabel.ForeColor = [System.Drawing.Color]::DarkGreen
        $statusLabel.Text = "Geplant fuer $($scheduled.ToString('dd.MM.yyyy HH:mm'))"
    } catch {
        $statusLabel.ForeColor = [System.Drawing.Color]::DarkRed
        $statusLabel.Text = "Fehler: $($_.Exception.Message)"
    }
})

$removeButton.Add_Click({
    try {
        Remove-PlannedHibernate
        & $refreshStatus
    } catch {
        $statusLabel.ForeColor = [System.Drawing.Color]::DarkRed
        $statusLabel.Text = "Fehler: $($_.Exception.Message)"
    }
})

& $refreshStatus
[void]$form.ShowDialog()
