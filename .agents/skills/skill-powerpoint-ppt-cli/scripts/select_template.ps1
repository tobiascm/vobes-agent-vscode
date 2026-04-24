# Lists PowerPoint templates available under the skill's Vorlagen directory.
# Returns JSON on stdout (agent-consumable) and a human-readable table on stderr.

[CmdletBinding()]
param(
    [string]$TemplatesDir = (Join-Path $PSScriptRoot '..' 'Vorlagen')
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $TemplatesDir)) {
    $msg = "Templates directory not found: $TemplatesDir"
    [Console]::Error.WriteLine($msg)
    @{ error = $msg; templates = @() } | ConvertTo-Json -Depth 3
    exit 2
}

$resolvedDir = (Resolve-Path -LiteralPath $TemplatesDir).ProviderPath

$items = Get-ChildItem -LiteralPath $resolvedDir -File |
    Where-Object { $_.Extension -in '.potx', '.pptx', '.pptm' } |
    Sort-Object Name

if (-not $items) {
    $msg = "No .potx/.pptx templates found in $resolvedDir"
    [Console]::Error.WriteLine($msg)
    @{ error = $msg; directory = $resolvedDir; templates = @() } | ConvertTo-Json -Depth 3
    exit 3
}

$rows = @()
$idx = 0
foreach ($f in $items) {
    $idx++
    $rows += [pscustomobject]@{
        index     = $idx
        name      = $f.Name
        full_path = $f.FullName
        size_kb   = [int][math]::Round($f.Length / 1024)
        modified  = $f.LastWriteTime.ToString('s')
    }
}

# Human-readable table on stderr
[Console]::Error.WriteLine("")
[Console]::Error.WriteLine("Verfuegbare Vorlagen in $resolvedDir")
[Console]::Error.WriteLine(('-' * 72))
$rows | Format-Table -AutoSize | Out-String | ForEach-Object { [Console]::Error.Write($_) }
[Console]::Error.WriteLine("Bitte dem Agent die 'index' oder den 'name' der gewuenschten Vorlage nennen.")
[Console]::Error.WriteLine("")

# JSON on stdout
@{
    directory = $resolvedDir
    count     = $rows.Count
    templates = $rows
} | ConvertTo-Json -Depth 4
