param(
    [ValidateSet('done', 'failed')]
    [string]$Status = 'done',

    [string]$Message = '',

    [string]$SummaryFile = '.\.copilot\tldr.txt',

    [string]$Title = 'Copilot Agent',

    [switch]$NoPopup
)

Add-Type -AssemblyName System.Windows.Forms

$summary = $null

# 1. Direkt uebergebene Message hat Vorrang
if ($Message) {
    $summary = $Message.Trim()
}

# 2. Fallback: Summary-Datei lesen
if (-not $summary -and (Test-Path $SummaryFile)) {
    $raw = Get-Content -Path $SummaryFile -Raw -ErrorAction SilentlyContinue
    if ($raw) {
        # Letzten nicht-leeren Absatz extrahieren
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

$icon = if ($Status -eq 'failed') {
    [System.Windows.Forms.MessageBoxIcon]::Error
} else {
    [System.Windows.Forms.MessageBoxIcon]::Information
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

# OKCancel => Esc schließt als Cancel
[void][System.Windows.Forms.MessageBox]::Show(
    $text,
    $Title,
    [System.Windows.Forms.MessageBoxButtons]::OKCancel,
    $icon
)
