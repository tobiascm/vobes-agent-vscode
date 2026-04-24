# 5-Folien-POC: builds a corporate deck from a .potx/.pptx template using pptcli batch mode.
#
# Workflow:
#   1. Copy template to drafts/ as .pptx (never modify the original)
#   2. Open a pptcli session
#   3. List available layouts (for later reference / log)
#   4. Create 5 slides (title + agenda + 3 content slides)
#   5. Fill placeholders where present
#   6. Save + close

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$TemplatePath,

    [string]$OutputPath,

    [string]$PptCli = 'C:\Daten\Programme\mcp-server-ppt\src\PptMcp.CLI\bin\Release\net9.0-windows\pptcli.exe',

    [string]$DeckTitle    = 'VOBES 2025 - Proof of Concept',
    [string]$DeckSubtitle = ('Automatisch erzeugt mit pptcli - ' + (Get-Date -Format 'yyyy-MM-dd HH:mm'))
)

$ErrorActionPreference = 'Stop'

function Write-Info([string]$msg) { [Console]::Error.WriteLine("[poc] $msg") }
function Fail([string]$msg) { [Console]::Error.WriteLine("[poc][ERROR] $msg"); exit 1 }

# Derive default OutputPath (cannot be done in param default because $PSScriptRoot stringification is fragile there)
if (-not $OutputPath) {
    $repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..\..')).ProviderPath
    $OutputPath = Join-Path $repoRoot 'userdata\powerpoint\drafts\poc_corporate_deck.pptx'
}

# ---------------------------------------------------------------- sanity checks
if (-not (Test-Path -LiteralPath $TemplatePath)) { Fail "Template not found: $TemplatePath" }
if (-not (Test-Path -LiteralPath $PptCli))       { Fail "pptcli.exe not found: $PptCli" }

# ---------------------------------------------------------------- prepare draft
$outDir = Split-Path -Parent $OutputPath
if (-not (Test-Path -LiteralPath $outDir)) { New-Item -ItemType Directory -Force -Path $outDir | Out-Null }

$ext = [IO.Path]::GetExtension($OutputPath).ToLowerInvariant()
if ($ext -ne '.pptx') { Fail "OutputPath must end with .pptx (got $ext)" }

Write-Info "Instantiating template via PowerPoint COM -> $OutputPath"
# Using PowerPoint COM to open the .potx as a template instance and save as .pptx
# Plain Copy-Item of a .potx to .pptx does not produce a valid .pptx (COM HRESULT error in pptcli).
$pp = $null
$pres = $null
try {
    $pp = New-Object -ComObject PowerPoint.Application
    # Presentations.Open: path, ReadOnly, Untitled (as new presentation), WithWindow
    # msoTrue=-1, msoFalse=0, msoCTrue=1
    $pres = $pp.Presentations.Open((Resolve-Path -LiteralPath $TemplatePath).ProviderPath, 0, -1, 0)
    # ppSaveAsOpenXMLPresentation = 24
    $pres.SaveAs($OutputPath, 24)
    $pres.Close()
}
finally {
    if ($pres) { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($pres) | Out-Null }
    if ($pp)   { $pp.Quit(); [System.Runtime.InteropServices.Marshal]::ReleaseComObject($pp) | Out-Null }
    [GC]::Collect(); [GC]::WaitForPendingFinalizers()
}
if (-not (Test-Path -LiteralPath $OutputPath)) { Fail "SaveAs failed - no output file at $OutputPath" }

# ---------------------------------------------------------------- quick probe
Write-Info "pptcli version:"
& $PptCli --version 2>&1 | ForEach-Object { [Console]::Error.WriteLine("  $_") }

# ---------------------------------------------------------------- open session
Write-Info "Opening session on draft"
$openJson = & $PptCli -q session open $OutputPath 2>$null
if ($LASTEXITCODE -ne 0 -or -not $openJson) { Fail "session open failed (exit=$LASTEXITCODE): $openJson" }

$sessionId = $null
try { $sessionId = ($openJson | ConvertFrom-Json).sessionId } catch {}
if (-not $sessionId) { Fail "Could not parse sessionId from: $openJson" }
Write-Info "sessionId = $sessionId"

try {
    # ------------------------------------------------------------ layouts
    Write-Info "Listing layouts on master 1"
    $layoutsJson = & $PptCli -q master list-layouts --session $sessionId --master-index 1 2>$null
    [Console]::Error.WriteLine("  layouts: $layoutsJson")

    $layoutNames = @()
    try {
        $parsed = $layoutsJson | ConvertFrom-Json
        if ($parsed.layouts) {
            $layoutNames = @($parsed.layouts | ForEach-Object { $_.name })
        } elseif ($parsed -is [System.Array]) {
            $layoutNames = @($parsed | ForEach-Object { $_.name })
        }
    } catch {}

    function Get-Layout([string[]]$candidates, [string[]]$available) {
        foreach ($c in $candidates) { if ($available -contains $c) { return $c } }
        if ($available.Count -gt 0) { return $available[0] }
        return 'Blank'
    }

    $lTitle   = Get-Layout @('Title Slide','Titelfolie','Title')                              $layoutNames
    $lContent = Get-Layout @('Title and Content','Titel und Inhalt','Inhalt','Content')       $layoutNames
    $lSection = Get-Layout @('Section Header','Abschnittsueberschrift','Section')             $layoutNames
    $lBlank   = Get-Layout @('Blank','Leer')                                                  $layoutNames

    Write-Info ("Layout-Auswahl: title='{0}' content='{1}' section='{2}' blank='{3}'" -f $lTitle,$lContent,$lSection,$lBlank)

    # ------------------------------------------------------------ build 5 slides
    $slides = @(
        @{ layout = $lTitle;   title = $DeckTitle;                             body = $DeckSubtitle },
        @{ layout = $lSection; title = 'Agenda';                               body = "1. Zielbild`n2. Aktueller Stand`n3. Naechste Schritte" },
        @{ layout = $lContent; title = 'Zielbild';                             body = "* Reproduzierbare Deck-Erzeugung`n* Corporate-Template als Single Source`n* Keine manuelle XML-Bearbeitung" },
        @{ layout = $lContent; title = 'Aktueller Stand';                      body = "* pptcli lokal gebaut`n* Skill angelegt`n* POC in Arbeit" },
        @{ layout = $lContent; title = 'Naechste Schritte';                    body = "* Layout-Namen auf Corporate-Template validieren`n* Echte Inhalte einsetzen`n* PDF-Export" }
    )

    for ($i = 0; $i -lt $slides.Count; $i++) {
        $s     = $slides[$i]
        $index = $i + 1

        if ($i -eq 0) {
            Write-Info "Slide 1: apply-layout + fill placeholders (existing first slide)"
            & $PptCli -q slide apply-layout --session $sessionId --slide-index 1 --layout-name $s.layout 2>$null | Out-Null
        } else {
            Write-Info ("Slide {0}: create with layout '{1}'" -f $index, $s.layout)
            & $PptCli -q slide create --session $sessionId --position $index --layout-name $s.layout 2>$null | Out-Null
        }

        # Placeholder 1 = usually title; Placeholder 2 = usually body/subtitle
        & $PptCli -q placeholder set-text --session $sessionId --slide-index $index --placeholder-index 1 --text $s.title 2>$null | Out-Null
        & $PptCli -q placeholder set-text --session $sessionId --slide-index $index --placeholder-index 2 --text $s.body  2>$null | Out-Null
    }

    # ------------------------------------------------------------ save
    Write-Info "Closing session (--save)"
    & $PptCli -q session close --session $sessionId --save 2>$null | Out-Null

    @{
        success     = $true
        output_path = (Resolve-Path -LiteralPath $OutputPath).ProviderPath
        session_id  = $sessionId
        layouts     = $layoutNames
        slide_count = $slides.Count
    } | ConvertTo-Json -Depth 4
}
catch {
    Write-Info "Error during POC build: $_"
    try { & $PptCli -q session close --session $sessionId 2>$null | Out-Null } catch {}
    throw
}
