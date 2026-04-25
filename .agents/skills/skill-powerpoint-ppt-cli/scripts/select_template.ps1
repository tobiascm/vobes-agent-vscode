param(
    [int]$Index,
    [string]$Name,
    [switch]$NonInteractive
)

$ErrorActionPreference = "Stop"

$skillRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$templateDir = Join-Path $skillRoot "Vorlagen"

if (-not (Test-Path -LiteralPath $templateDir)) {
    throw "Vorlagen-Ordner nicht gefunden: $templateDir"
}

$templates = @(Get-ChildItem -Path $templateDir -File -Include *.potx, *.pptx -Recurse |
    Sort-Object FullName)

if (-not $templates -or $templates.Count -eq 0) {
    throw "Keine .potx oder .pptx Vorlage gefunden in: $templateDir"
}

$selected = $null

if ($Name) {
    $matches = @($templates | Where-Object { $_.Name -like "*$Name*" -or $_.BaseName -like "*$Name*" })

    if ($matches.Count -eq 1) {
        $selected = $matches[0]
    }
    elseif ($matches.Count -gt 1) {
        $names = ($matches | ForEach-Object { $_.FullName }) -join "`n"
        throw "Name ist nicht eindeutig: $Name`nTreffer:`n$names"
    }
    elseif ($NonInteractive) {
        throw "Keine Vorlage passend zu -Name gefunden: $Name"
    }
}

if (-not $selected -and $PSBoundParameters.ContainsKey("Index")) {
    if ($Index -lt 1 -or $Index -gt $templates.Count) {
        throw "Index ausserhalb des gueltigen Bereichs: $Index. Gueltig: 1-$($templates.Count)"
    }

    $selected = $templates[$Index - 1]
}

if (-not $selected) {
    if ($NonInteractive) {
        throw "Keine eindeutige Vorlage ausgewaehlt. Nutze -Index oder -Name."
    }

    Write-Host ""
    Write-Host "Verfuegbare PowerPoint-Vorlagen:"
    Write-Host ""

    for ($i = 0; $i -lt $templates.Count; $i++) {
        $n = $i + 1
        Write-Host ("[{0}] {1}" -f $n, $templates[$i].FullName)
    }

    Write-Host ""
    $choice = Read-Host "Bitte Vorlage waehlen [1-$($templates.Count)]"

    if (-not ($choice -as [int])) {
        throw "Ungueltige Auswahl: $choice"
    }

    $choiceIndex = [int]$choice
    if ($choiceIndex -lt 1 -or $choiceIndex -gt $templates.Count) {
        throw "Auswahl ausserhalb des gueltigen Bereichs: $choice"
    }

    $selected = $templates[$choiceIndex - 1]
}

Write-Host ""
Write-Host "Gewaehlte Vorlage:"
Write-Host $selected.FullName

# Letzte Zeile bewusst maschinenlesbar: nur Pfad.
$selected.FullName
