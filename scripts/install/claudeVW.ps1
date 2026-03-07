param(
    [string]$ProjectRoot = (Get-Location).Path,
    [string]$Model,
    [string]$AuthUtilsDir,
    [string]$BaseUrl,
    [string]$ApiClientId,
    [string]$ApiKeyHelperCommand,
    [string]$ClaudeConfigDir = (Join-Path $HOME ".claudeVW"),
    [int]$HelperTtlMs = 1500000,
    [switch]$NoLaunch
)

$ErrorActionPreference = "Stop"

function Require-Command {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Befehl nicht gefunden: $Name"
    }
}

function Require-Env {
    param([string]$Name)
    $value = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($value)) {
        throw "Umgebungsvariable fehlt: $Name"
    }
    return $value
}

function Get-DefaultModelMappings {
    param([string[]]$AllowedModels)

    $opusModel = "claude-opus-4.6"
    $sonnetModel = "claude-sonnet-4.6"
    $haikuModel = "claude-haiku-4.5"
    $geminiModel = "gemini-2.5-pro"

    if ($AllowedModels -notcontains $opusModel) {
        throw "Alias-Mapping fuer opus ungueltig. Erwartetes Modell fehlt in allowedModels: $opusModel"
    }
    if ($AllowedModels -notcontains $sonnetModel) {
        throw "Alias-Mapping fuer sonnet ungueltig. Erwartetes Modell fehlt in allowedModels: $sonnetModel"
    }
    if ($AllowedModels -notcontains $haikuModel) {
        throw "Alias-Mapping fuer haiku ungueltig. Erwartetes Modell fehlt in allowedModels: $haikuModel"
    }
    if ($AllowedModels -notcontains $geminiModel) {
        throw "Alias-Mapping fuer gemini ungueltig. Erwartetes Modell fehlt in allowedModels: $geminiModel"
    }

    return [ordered]@{
        Opus = $opusModel
        Sonnet = $sonnetModel
        Haiku = $haikuModel
        Gemini = $geminiModel
    }
}

function Select-ModelInteractive {
    $defaultModel = "claude-opus-4.6"
    $choices = [ordered]@{
        "1" = "claude-sonnet"
        "2" = "claude-haiku"
        "3" = "claude-opus-4.6"
        "4" = "claude-sonnet-4.6"
        "5" = "claude-haiku-4.5"
        "6" = "gemini-2.5-pro"
    }

    Write-Host "Modell auswaehlen:"
    Write-Host "  1) claude-sonnet"
    Write-Host "  2) claude-haiku"
    Write-Host "  3) claude-opus-4.6 (Standard)"
    Write-Host "  4) claude-sonnet-4.6"
    Write-Host "  5) claude-haiku-4.5"
    Write-Host "  6) gemini-2.5-pro"
    $selection = Read-Host "Taste 1-6 druecken oder Enter fuer Standard"

    if ([string]::IsNullOrWhiteSpace($selection)) {
        return $defaultModel
    }
    if ($choices.Contains($selection)) {
        return $choices[$selection]
    }

    throw "Ungueltige Auswahl '$selection'. Erlaubt sind 1-6 oder Enter."
}

$ProjectRoot = (Resolve-Path $ProjectRoot).Path
$ClaudeConfigDir = [System.IO.Path]::GetFullPath($ClaudeConfigDir)
$UseExternalHelper = -not [string]::IsNullOrWhiteSpace($ApiKeyHelperCommand)

$allowedModels = @(
    "claude-sonnet",
    "claude-haiku",
    "claude-opus-4.6",
    "claude-sonnet-4.6",
    "claude-haiku-4.5",
    "gemini-2.5-pro"
)

$aliasMappings = Get-DefaultModelMappings -AllowedModels $allowedModels

if ($PSBoundParameters.ContainsKey("Model") -and -not [string]::IsNullOrWhiteSpace($Model)) {
    if ($allowedModels -notcontains $Model) {
        throw "Unbekanntes Modell '$Model'. Erlaubt: $($allowedModels -join ', ')"
    }
}
else {
    $Model = Select-ModelInteractive
}

$dangerousInput = Read-Host "Dangerous mode (--dangerously-skip-permissions)? [j/N]"
$DangerousMode = $dangerousInput -eq "j"

if (-not $UseExternalHelper -and [string]::IsNullOrWhiteSpace($AuthUtilsDir)) {
    $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    $candidates = @(
        (Join-Path $scriptDir ".claude"),
        (Join-Path $ProjectRoot ".claude"),
        (Join-Path $ProjectRoot "src\\LLMaaS"),
        $ProjectRoot
    )
    $AuthUtilsDir = $candidates | Where-Object { Test-Path (Join-Path $_ "auth_utils.py") } | Select-Object -First 1
}

if (-not $UseExternalHelper -and [string]::IsNullOrWhiteSpace($AuthUtilsDir)) {
    throw "Konnte auth_utils.py nicht finden. Bitte -AuthUtilsDir angeben (z.B. '.\.claude') oder alternativ -ApiKeyHelperCommand verwenden."
}

if (-not $UseExternalHelper) {
    $AuthUtilsDir = (Resolve-Path $AuthUtilsDir).Path
}

Require-Command "python"
Require-Command "claude"

if (-not $UseExternalHelper) {
    # Für euren bestehenden Auth-Flow laut vorhandener Python-Utilities nötig
    Require-Env "LLMAAS_API_CLIENT_ID" | Out-Null
    Require-Env "LLMAAS_CLIENT_ID" | Out-Null
    Require-Env "LLMAAS_CLIENT_SECRET" | Out-Null
}

$projectClaudeDir = Join-Path $ProjectRoot ".claude"
$helperDir = Join-Path $ClaudeConfigDir "llmaas"
$settingsPath = Join-Path $ClaudeConfigDir "settings.json"

$projectSettingsPaths = @(
    (Join-Path $projectClaudeDir "settings.json"),
    (Join-Path $projectClaudeDir "settings.local.json")
) | Where-Object { Test-Path $_ }

if ($projectSettingsPaths.Count -gt 0) {
    Write-Warning "Im Projekt existieren bereits Claude-Settings mit hoeherer Prioritaet als User-Scope-Settings."
    foreach ($p in $projectSettingsPaths) {
        Write-Warning "Gefunden: $p"
    }
}

New-Item -ItemType Directory -Force -Path $ClaudeConfigDir | Out-Null

if ($UseExternalHelper) {
    if ([string]::IsNullOrWhiteSpace($BaseUrl)) {
        throw "Im Modus -ApiKeyHelperCommand ist -BaseUrl erforderlich."
    }
    if ([string]::IsNullOrWhiteSpace($ApiClientId)) {
        throw "Im Modus -ApiKeyHelperCommand ist -ApiClientId erforderlich."
    }

    $EffectiveApiKeyHelper = $ApiKeyHelperCommand
}
else {
    New-Item -ItemType Directory -Force -Path $helperDir | Out-Null
    $probePyPath = Join-Path $helperDir "probe_llmaas_config.py"
    $probePy = @"
import json
import sys
from pathlib import Path

project_root = Path(r"$ProjectRoot")
auth_utils_dir = Path(r"$AuthUtilsDir")
for p in (str(auth_utils_dir), str(project_root)):
    if p not in sys.path:
        sys.path.insert(0, p)

from auth_utils import get_base_url, get_api_client_id

print(json.dumps({
    "base_url": get_base_url(),
    "api_client_id": get_api_client_id(),
}), end="")
"@

    Set-Content -Path $probePyPath -Value $probePy -Encoding UTF8
    $probeJson = & python $probePyPath
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($probeJson)) {
        throw "Konnte base_url / api_client_id nicht aus auth_utils ermitteln."
    }

    $probe = $probeJson | ConvertFrom-Json
    $BaseUrl = [string]$probe.base_url
    $ApiClientId = [string]$probe.api_client_id

    if ([string]::IsNullOrWhiteSpace($BaseUrl)) {
        throw "get_base_url() hat keinen Wert geliefert."
    }
    if ([string]::IsNullOrWhiteSpace($ApiClientId)) {
        throw "get_api_client_id() hat keinen Wert geliefert."
    }
}

if (-not $UseExternalHelper) {
    $helperPyPath = Join-Path $helperDir "get_llmaas_token.py"
    New-Item -ItemType Directory -Force -Path $helperDir | Out-Null

    $helperPy = @"
import sys
from pathlib import Path

project_root = Path(r"$ProjectRoot")
auth_utils_dir = Path(r"$AuthUtilsDir")
for p in (str(auth_utils_dir), str(project_root)):
    if p not in sys.path:
        sys.path.insert(0, p)

from auth_utils import get_token

token = get_token().strip()
if token.lower().startswith("bearer "):
    token = token[7:]

sys.stdout.write(token)
"@

    Set-Content -Path $helperPyPath -Value $helperPy -Encoding UTF8
    $EffectiveApiKeyHelper = "python `"$helperPyPath`""
}

$settings = [ordered]@{
    '$schema' = 'https://json.schemastore.org/claude-code-settings.json'
    availableModels = @("opus", "sonnet", "haiku", "gemini")
    apiKeyHelper = $EffectiveApiKeyHelper
    env = [ordered]@{
        ANTHROPIC_BASE_URL = $BaseUrl
        ANTHROPIC_MODEL = $Model
        ANTHROPIC_DEFAULT_OPUS_MODEL = $aliasMappings.Opus
        ANTHROPIC_DEFAULT_SONNET_MODEL = $aliasMappings.Sonnet
        ANTHROPIC_DEFAULT_HAIKU_MODEL = $aliasMappings.Haiku
        ANTHROPIC_DEFAULT_GEMINI_MODEL = $aliasMappings.Gemini
        ANTHROPIC_CUSTOM_HEADERS = "x-llm-api-client-id: Bearer $ApiClientId"
        CLAUDE_CODE_API_KEY_HELPER_TTL_MS = [string]$HelperTtlMs
        CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS = "1"
    }
}

$settingsJson = $settings | ConvertTo-Json -Depth 10
Set-Content -Path $settingsPath -Value $settingsJson -Encoding UTF8

Write-Host "Projekt:             $ProjectRoot"
Write-Host "ClaudeConfigDir:     $ClaudeConfigDir"
if ($UseExternalHelper) {
    Write-Host "Auth-Modus:          externer apiKeyHelper"
    Write-Host "apiKeyHelper:        $EffectiveApiKeyHelper"
}
else {
    Write-Host "Auth-Modus:          auth_utils.py"
    Write-Host "AuthUtilsDir:        $AuthUtilsDir"
    Write-Host "Helper:              $helperPyPath"
}
Write-Host "ANTHROPIC_BASE_URL:  $BaseUrl"
Write-Host "ANTHROPIC_MODEL:     $Model"
Write-Host "Alias opus ->        $($aliasMappings.Opus)"
Write-Host "Alias sonnet ->      $($aliasMappings.Sonnet)"
Write-Host "Alias haiku ->       $($aliasMappings.Haiku)"
Write-Host "Alias gemini ->      $($aliasMappings.Gemini)"
Write-Host "availableModels:     opus, sonnet, haiku, gemini"
Write-Host "Custom Header:       x-llm-api-client-id: Bearer $ApiClientId"
Write-Host "Settings:            $settingsPath"
Write-Host "Helper TTL (ms):     $HelperTtlMs"
Write-Host "MCP Tools:           aktiviert"

if ($NoLaunch) {
    Write-Host "Claude Code wurde nicht gestartet (-NoLaunch)."
    Write-Host "Manueller Start in einer Shell:"
    Write-Host "  `$env:CLAUDE_CONFIG_DIR = `"$ClaudeConfigDir`""
    Write-Host "  claude --model $Model$(if ($DangerousMode) { ' --dangerously-skip-permissions' })"
    exit 0
}

$previousClaudeConfigDir = [Environment]::GetEnvironmentVariable("CLAUDE_CONFIG_DIR", "Process")
$previousAnthropicAuthToken = [Environment]::GetEnvironmentVariable("ANTHROPIC_AUTH_TOKEN", "Process")
$previousAnthropicApiKey = [Environment]::GetEnvironmentVariable("ANTHROPIC_API_KEY", "Process")

Push-Location $ProjectRoot
try {
    $env:CLAUDE_CONFIG_DIR = $ClaudeConfigDir

    # apiKeyHelper hat niedrigere Prioritaet als ANTHROPIC_AUTH_TOKEN / ANTHROPIC_API_KEY.
    # Daher nur fuer diesen Claude-Start session-lokal entfernen.
    Remove-Item Env:ANTHROPIC_AUTH_TOKEN -ErrorAction SilentlyContinue
    Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue

    if ($DangerousMode) {
        & claude --model $Model --dangerously-skip-permissions
    } else {
        & claude --model $Model
    }
}
finally {
    if ([string]::IsNullOrWhiteSpace($previousClaudeConfigDir)) {
        Remove-Item Env:CLAUDE_CONFIG_DIR -ErrorAction SilentlyContinue
    }
    else {
        $env:CLAUDE_CONFIG_DIR = $previousClaudeConfigDir
    }

    if ([string]::IsNullOrWhiteSpace($previousAnthropicAuthToken)) {
        Remove-Item Env:ANTHROPIC_AUTH_TOKEN -ErrorAction SilentlyContinue
    }
    else {
        $env:ANTHROPIC_AUTH_TOKEN = $previousAnthropicAuthToken
    }

    if ([string]::IsNullOrWhiteSpace($previousAnthropicApiKey)) {
        Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue
    }
    else {
        $env:ANTHROPIC_API_KEY = $previousAnthropicApiKey
    }

    Pop-Location
}
