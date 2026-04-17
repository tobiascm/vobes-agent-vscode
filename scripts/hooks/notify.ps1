param(
    [ValidateSet('done', 'failed')]
    [string]$Status = 'done',

    [string]$Message = '',

    [string]$SummaryFile = '.\.copilot\tldr.txt',

    [string]$Title = 'Copilot Agent',

    [switch]$NoPopup,

    # Blockiert und wartet auf Antwort; Exit-Code 0 = OK, 1 = Cancel
    [switch]$AskUser
)

$summary = $null

# 1. Direkt uebergebene Message hat Vorrang
if ($Message) {
    $summary = $Message.Trim()
}

# 2. Fallback: Summary-Datei lesen
if (-not $summary -and (Test-Path $SummaryFile)) {
    $raw = Get-Content -Path $SummaryFile -Raw -ErrorAction SilentlyContinue
    if ($raw) {
        $paragraphs = ($raw -split '(\r?\n){2,}') | Where-Object { $_.Trim() }
        if ($paragraphs) {
            $summary = ($paragraphs | Select-Object -Last 1).Trim()
        }
    }
}

# 3. Letzter Fallback
if (-not $summary) {
    $summary = '(Kein Summary verfuegbar)'
}

$text = if ($Status -eq 'failed') {
    "Fehlgeschlagen`r`n`r`n$summary"
} else {
    "Fertig`r`n`r`n$summary"
}

if ($NoPopup) {
    [pscustomobject]@{
        status  = $Status
        title   = $Title
        summary = $summary
        text    = $text
    } | ConvertTo-Json -Compress
    exit 0
}

if ($AskUser) {
    Add-Type -AssemblyName System.Windows.Forms
    $icon = if ($Status -eq 'failed') {
        [System.Windows.Forms.MessageBoxIcon]::Error
    } else {
        [System.Windows.Forms.MessageBoxIcon]::Question
    }
    $result = [System.Windows.Forms.MessageBox]::Show(
        $text,
        $Title,
        [System.Windows.Forms.MessageBoxButtons]::OKCancel,
        $icon
    )
    exit $(if ($result -eq [System.Windows.Forms.DialogResult]::OK) { 0 } else { 1 })
}

# Default: Non-blocking via wscript.exe (kein Konsolenfenster)
$iconCode = if ($Status -eq 'failed') { 16 } else { 64 }
$vbs      = [System.IO.Path]::GetTempFileName() + '.vbs'
# Zeilenumbrüche und Anführungszeichen für VBScript aufbereiten
$vbsText  = ($text  -replace '"', '') -replace '\r?\n', '" & Chr(13) & Chr(10) & "'
$vbsTitle = $Title -replace '"', ''
$vbsContent = @"
Dim wsh : Set wsh = CreateObject("WScript.Shell")
wsh.Popup "$vbsText", 15, "$vbsTitle", $iconCode
CreateObject("Scripting.FileSystemObject").DeleteFile WScript.ScriptFullName
"@
[System.IO.File]::WriteAllText($vbs, $vbsContent, (New-Object System.Text.UTF8Encoding $false))
Start-Process wscript.exe -ArgumentList "`"$vbs`""
exit 0
