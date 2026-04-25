param(
    [Parameter(Mandatory = $true)]
    [string]$Task,

    [Parameter(Mandatory = $true)]
    [string]$TemplatePath,

    [Parameter(Mandatory = $true)]
    [string]$OutputPath,

    [switch]$Overwrite,
    [switch]$Show,
    [string]$Model,
    [ValidateSet("codex", "copilot")]
    [string]$Provider = "codex",
    [string]$PlanFile,
    [switch]$SkipVerify,
    [string]$McpServer
)

$ErrorActionPreference = "Stop"

if (-not $Model) {
    $Model = if ($Provider -eq "codex") { "gpt-5.4" } else { "opus-4.6" }
}

# Hinweis:
# TemplatePath wird aktuell als Corporate-Template-Guidance an PptMcp.Agent uebergeben.
# Dieses Wrapper-Script garantiert noch keine COM-Instanziierung des Templates als Output-PPTX.
# Bestehende PPTX-Umbauten laufen ueber den Modify-Workflow mit `pptcli session open`.

function Resolve-FullPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if ([System.IO.Path]::IsPathRooted($Path)) {
        return [System.IO.Path]::GetFullPath($Path)
    }

    return [System.IO.Path]::GetFullPath((Join-Path (Get-Location).ProviderPath $Path))
}

function Get-PptxSlideCountFromZip {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PptxPath
    )

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [System.IO.Compression.ZipFile]::OpenRead($PptxPath)
    try {
        return ($zip.Entries | Where-Object { $_.FullName -match '^ppt/slides/slide\d+\.xml$' }).Count
    }
    finally {
        $zip.Dispose()
    }
}

function Get-PlanSlideCount {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PlanPath
    )

    $planObj = Get-Content -LiteralPath $PlanPath -Raw | ConvertFrom-Json -Depth 100
    if ($null -eq $planObj) {
        return $null
    }

    if ($planObj.PSObject.Properties.Name -contains "slides" -and $null -ne $planObj.slides) {
        return @($planObj.slides).Count
    }

    return $null
}

function Write-DeterministicRunSummary {
    param(
        [Parameter(Mandatory = $true)]
        [int]$AgentExitCode,

        [Parameter(Mandatory = $true)]
        [string]$TaskText,

        [Parameter(Mandatory = $true)]
        [string]$ModelName,

        [Parameter(Mandatory = $true)]
        [string]$ProviderName,

        [Parameter(Mandatory = $true)]
        [string]$OutputPath,

        [Parameter(Mandatory = $true)]
        [string]$PlanPath,

        [Parameter(Mandatory = $true)]
        [string]$ArtifactsDir,

        [Parameter(Mandatory = $true)]
        [bool]$SkipVerifyFlag
    )

    New-Item -ItemType Directory -Path $ArtifactsDir -Force | Out-Null
    $summaryPath = Join-Path $ArtifactsDir "run-summary.json"

    $rawExecutionSummary = $null
    $rawRepairSummary = $null
    $rawVerificationSummary = $null

    if (Test-Path -LiteralPath $summaryPath) {
        try {
            $existing = Get-Content -LiteralPath $summaryPath -Raw | ConvertFrom-Json -Depth 100
            if ($null -ne $existing) {
                if ($existing.PSObject.Properties.Name -contains "executionSummary") {
                    $rawExecutionSummary = $existing.executionSummary
                }
                if ($existing.PSObject.Properties.Name -contains "repairSummary") {
                    $rawRepairSummary = $existing.repairSummary
                }
                if ($existing.PSObject.Properties.Name -contains "verificationSummary") {
                    $rawVerificationSummary = $existing.verificationSummary
                }
            }
        }
        catch {
            $rawExecutionSummary = "Existing run-summary.json could not be parsed: $($_.Exception.Message)"
        }
    }

    $outputExists = Test-Path -LiteralPath $OutputPath
    $planExists = Test-Path -LiteralPath $PlanPath
    $artifactsDirExists = Test-Path -LiteralPath $ArtifactsDir

    $slideCountActual = $null
    if ($outputExists) {
        try {
            $slideCountActual = Get-PptxSlideCountFromZip -PptxPath $OutputPath
        }
        catch {
            $slideCountActual = $null
        }
    }

    $slideCountPlanned = $null
    if ($planExists) {
        try {
            $slideCountPlanned = Get-PlanSlideCount -PlanPath $PlanPath
        }
        catch {
            $slideCountPlanned = $null
        }
    }

    $slideCountMatch = $null
    if ($null -ne $slideCountActual -and $null -ne $slideCountPlanned) {
        $slideCountMatch = ($slideCountActual -eq $slideCountPlanned)
    }

    $verification = "unknown"
    if ($SkipVerifyFlag) {
        $verification = "skipped"
    }
    elseif ($AgentExitCode -ne 0 -or -not $outputExists -or $slideCountMatch -eq $false) {
        $verification = "failed"
    }
    elseif ($slideCountMatch -eq $true) {
        $verification = "passed"
    }

    $isSuccess = (
        $AgentExitCode -eq 0 -and
        $outputExists -and
        ($null -eq $slideCountPlanned -or $slideCountMatch -eq $true)
    )

    $sanitizedSummary = [ordered]@{
        status             = if ($isSuccess) { "success" } else { "failed" }
        verification       = $verification
        generatedAtUtc     = (Get-Date).ToUniversalTime().ToString("o")
        agentExitCode      = $AgentExitCode
        outputExists       = $outputExists
        planExists         = $planExists
        artifactsDirExists = $artifactsDirExists
        slideCountActual   = $slideCountActual
        slideCountPlanned  = $slideCountPlanned
        slideCountMatch    = $slideCountMatch
        task               = $TaskText
        model              = $ModelName
        provider           = $ProviderName
        outputPath         = $OutputPath
        planPath           = $PlanPath
        artifactsDir       = $ArtifactsDir
        raw                = [ordered]@{
            executionSummary    = $rawExecutionSummary
            repairSummary       = $rawRepairSummary
            verificationSummary = $rawVerificationSummary
        }
    }

    $sanitizedSummary | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $summaryPath -Encoding UTF8
    return $summaryPath
}

$workspace = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..\..\..")).ProviderPath

$agentDir = "C:\Daten\Programme\mcp-server-ppt\src\PptMcp.Agent"
$agentCli = Join-Path $agentDir "src\cli.mjs"
$defaultMcpServer = "C:\Daten\Programme\mcp-server-ppt\src\PptMcp.McpServer\bin\Release\net9.0-windows\PptMcp.McpServer.exe"

$templateFull = (Resolve-Path -LiteralPath $TemplatePath).ProviderPath
if (-not (Test-Path -LiteralPath $templateFull)) {
    throw "TemplatePath nicht gefunden: $templateFull"
}

if (-not (Test-Path -LiteralPath $agentCli)) {
    throw "PptMcp.Agent CLI nicht gefunden: $agentCli"
}

if (-not $McpServer) {
    $McpServer = $defaultMcpServer
}
$mcpServerFull = Resolve-FullPath $McpServer

if (-not (Test-Path -LiteralPath $mcpServerFull)) {
    throw "MCP Server Binary nicht gefunden: $mcpServerFull"
}

$outputFull = Resolve-FullPath $OutputPath
$outputDir = Split-Path -Parent $outputFull
New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
$outputBaseName = [System.IO.Path]::GetFileNameWithoutExtension($outputFull)
$planPath = Join-Path $outputDir "$outputBaseName.plan.json"
$artifactsDir = Join-Path $outputDir "$outputBaseName-artifacts"

if ((Test-Path -LiteralPath $outputFull) -and -not $Overwrite) {
    throw "Output existiert bereits. Nutze -Overwrite oder waehle einen anderen Pfad: $outputFull"
}

$taskWithTemplate = @"
$Task

Corporate template/profile:
- Use this template as the corporate design/profile source: $templateFull
- Preserve corporate layouts, colors, fonts and placeholders.
- Do not modify the template file itself.
- Write only to output file: $outputFull
"@

$nodeArgs = @(
    ".\src\cli.mjs",
    "run",
    "--task", $taskWithTemplate,
    "--output", $outputFull,
    "--provider", $Provider,
    "--mcp-server", $mcpServerFull
)

if ($Overwrite) {
    $nodeArgs += "--overwrite"
}

if ($Show) {
    $nodeArgs += "--show"
}

if ($SkipVerify) {
    $nodeArgs += "--skip-verify"
}

$nodeArgs += @("--model", $Model)

if ($PlanFile) {
    $planFileFull = (Resolve-Path -LiteralPath $PlanFile).ProviderPath
    if (-not (Test-Path -LiteralPath $planFileFull)) {
        throw "PlanFile nicht gefunden: $planFileFull"
    }
    $nodeArgs += @("--plan-file", $planFileFull)
}

Write-Host "Starte PptMcp.Agent..."
Write-Host "Workspace: $workspace"
Write-Host "AgentDir: $agentDir"
Write-Host "Template: $templateFull"
Write-Host "Output: $outputFull"
Write-Host "MCP Server: $mcpServerFull"
Write-Host "Model: $Model"
Write-Host "Provider: $Provider"

Push-Location $agentDir
$exit = 1
try {
    & node @nodeArgs
    $exit = $LASTEXITCODE
}
finally {
    Pop-Location
}

$deterministicSummaryPath = Write-DeterministicRunSummary `
    -AgentExitCode $exit `
    -TaskText $Task `
    -ModelName $Model `
    -ProviderName $Provider `
    -OutputPath $outputFull `
    -PlanPath $planPath `
    -ArtifactsDir $artifactsDir `
    -SkipVerifyFlag ([bool]$SkipVerify)

Write-Host "Run Summary: $deterministicSummaryPath"

if ($exit -ne 0) {
    throw "PptMcp.Agent ist mit Exitcode $exit fehlgeschlagen."
}

Write-Host ""
Write-Host "Fertig:"
Write-Host $outputFull
