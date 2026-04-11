param(
    [Parameter(Position = 0, Mandatory = $true)]
    [string]$NotificationJson
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms

function Get-TldrOrLastParagraph {
    param([string]$Text)

    if ([string]::IsNullOrWhiteSpace($Text)) {
        return 'Kein TL;DR gefunden.'
    }

    $normalized = $Text -replace "`r`n", "`n"
    $normalized = $normalized.Trim()

    # Nimm den letzten TL;DR-Block bis zum Ende
    $matches = [regex]::Matches($normalized, '(?is)TL;DR:\s*(.+)$')
    if ($matches.Count -gt 0) {
        $value = $matches[$matches.Count - 1].Groups[1].Value.Trim()
        if (-not [string]::IsNullOrWhiteSpace($value)) {
            return $value
        }
    }

    # Fallback: letzter nicht-leerer Absatz
    $paragraphs = @([regex]::Split($normalized, '\n\s*\n') |
        ForEach-Object { $_.Trim() } |
        Where-Object { $_ })

    if ($paragraphs.Count -gt 0) {
        return $paragraphs[$paragraphs.Count - 1]
    }

    # Letzter Fallback: letzte nicht-leere Zeile
    $lines = @($normalized -split '\n' |
        ForEach-Object { $_.Trim() } |
        Where-Object { $_ })

    if ($lines.Count -gt 0) {
        return $lines[$lines.Count - 1]
    }

    return 'Kein TL;DR gefunden.'
}

function Limit-Text {
    param(
        [string]$Text,
        [int]$MaxLen = 700
    )

    if ([string]::IsNullOrWhiteSpace($Text)) {
        return $Text
    }

    $s = [regex]::Replace($Text.Trim(), '\s+', ' ')
    if ($s.Length -le $MaxLen) {
        return $s
    }

    return $s.Substring(0, $MaxLen - 1).TrimEnd() + '…'
}

function New-ShortLabel {
    param(
        [string[]]$InputMessages,
        [string]$Cwd,
        [int]$MaxLen = 80
    )

    $repoName = if ($Cwd) { Split-Path -Leaf $Cwd } else { 'repo' }

    $topic = $null
    if ($InputMessages -and $InputMessages.Count -gt 0) {
        $topic = $InputMessages[$InputMessages.Count - 1]
    }

    if ([string]::IsNullOrWhiteSpace($topic)) {
        return $repoName
    }

    $topic = [regex]::Replace($topic.Trim(), '\s+', ' ')
    if ($topic.Length -gt $MaxLen) {
        $topic = $topic.Substring(0, $MaxLen - 1).TrimEnd() + '…'
    }

    return "$repoName | $topic"
}

$notification = $NotificationJson | ConvertFrom-Json

if ($notification.type -ne 'agent-turn-complete') {
    exit 0
}

$cwd = [string]$notification.'cwd'
$threadId = [string]$notification.'thread-id'
$assistantText = [string]$notification.'last-assistant-message'
$inputMessages = @($notification.'input-messages')

$label = New-ShortLabel -InputMessages $inputMessages -Cwd $cwd
$summary = Get-TldrOrLastParagraph -Text $assistantText
$summary = Limit-Text -Text $summary -MaxLen 700

$title = "Codex – $label"
$text = @"
Thread: $threadId

$summary
"@

# OKCancel => Esc schließt als Cancel
[void][System.Windows.Forms.MessageBox]::Show(
    $text,
    $title,
    [System.Windows.Forms.MessageBoxButtons]::OKCancel,
    [System.Windows.Forms.MessageBoxIcon]::Information
)

exit 0
