$ErrorActionPreference = "Stop"

$skillRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$targetDir = Join-Path $skillRoot "references\pptmcp-upstream"

New-Item -ItemType Directory -Path $targetDir -Force | Out-Null

$base = "https://raw.githubusercontent.com/trsdn/mcp-server-ppt/main"

$files = @(
    @{
        Url = "$base/skills/ppt-cli/SKILL.md"
        Name = "ppt-cli.SKILL.md"
    },
    @{
        Url = "$base/skills/ppt-mcp/SKILL.md"
        Name = "ppt-mcp.SKILL.md"
    },
    @{
        Url = "$base/skills/shared/behavioral-rules.md"
        Name = "behavioral-rules.md"
    },
    @{
        Url = "$base/skills/shared/generation-pipeline.md"
        Name = "generation-pipeline.md"
    },
    @{
        Url = "$base/skills/shared/ppt_agent_mode.md"
        Name = "ppt_agent_mode.md"
    },
    @{
        Url = "$base/skills/shared/slide-design-principles.md"
        Name = "slide-design-principles.md"
    },
    @{
        Url = "$base/skills/shared/slide-design-review.md"
        Name = "slide-design-review.md"
    },
    @{
        Url = "$base/src/PptMcp.Agent/README.md"
        Name = "PptMcp.Agent.README.md"
    },
    @{
        Url = "$base/docs/AGENT-CLIENT.md"
        Name = "AGENT-CLIENT.md"
    },
    @{
        Url = "$base/LICENSE"
        Name = "LICENSE"
    }
)

foreach ($file in $files) {
    $outPath = Join-Path $targetDir $file.Name
    $tmpPath = "$outPath.tmp"

    Write-Host "Downloading $($file.Name)..."

    if (Test-Path -LiteralPath $tmpPath) {
        Remove-Item -LiteralPath $tmpPath -Force
    }

    Invoke-WebRequest -Uri $file.Url -OutFile $tmpPath -UseBasicParsing

    $tmpItem = Get-Item -LiteralPath $tmpPath -ErrorAction Stop
    if ($tmpItem.Length -le 0) {
        throw "Download war leer: $($file.Url)"
    }

    Move-Item -LiteralPath $tmpPath -Destination $outPath -Force

    $item = Get-Item -LiteralPath $outPath -ErrorAction Stop
    if ($item.Length -le 0) {
        throw "Zieldatei ist leer: $outPath"
    }
}

$summary = foreach ($file in $files) {
    $path = Join-Path $targetDir $file.Name
    $item = Get-Item -LiteralPath $path -ErrorAction SilentlyContinue
    [pscustomobject]@{
        File    = $file.Name
        Exists  = [bool]$item
        SizeKB  = if ($item) { [math]::Round($item.Length / 1KB, 1) } else { $null }
    }
}

$summary | Format-Table -AutoSize

$missing = $summary | Where-Object { -not $_.Exists -or -not $_.SizeKB -or $_.SizeKB -le 0 }
if ($missing) {
    throw "Missing or empty upstream reference files: $($missing.File -join ', ')"
}

Write-Host "Upstream references updated: $targetDir"
