param(
    [string]$InitialPrompt = "",
    [string]$AzureOpenAIEndpoint = "https://bordnetzgpt-sw.openai.azure.com/",
    [string]$AzureOpenAIDeployment = "gpt-5.3-codex"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-NormalizedOpenAIBaseUrl {
    param(
        [Parameter(Mandatory = $true)]
        [string]$AzureEndpoint
    )

    $endpoint = $AzureEndpoint.Trim().TrimEnd('/')

    if ($endpoint -match '/openai/v1$') {
        return $endpoint
    }

    if ($endpoint -match '/openai$') {
        return "$endpoint/v1"
    }

    return "$endpoint/openai/v1"
}

function Restore-EnvVar {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [AllowNull()]
        [string]$PreviousValue
    )

    if ($null -eq $PreviousValue) {
        Remove-Item "Env:$Name" -ErrorAction SilentlyContinue
    }
    else {
        Set-Item "Env:$Name" $PreviousValue
    }
}

function Get-EnvVarValue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $value = [Environment]::GetEnvironmentVariable($Name, "Process")
    if (-not [string]::IsNullOrWhiteSpace($value)) {
        return $value
    }

    $value = [Environment]::GetEnvironmentVariable($Name, "User")
    if (-not [string]::IsNullOrWhiteSpace($value)) {
        return $value
    }

    return [Environment]::GetEnvironmentVariable($Name, "Machine")
}

# --- Vorbedingungen prüfen ---
Get-Command codex | Out-Null

$requiredEnvVars = @(
    "AZURE_OPENAI_API_KEY"
)

$missingEnvVars = @(
    $requiredEnvVars | Where-Object {
        [string]::IsNullOrWhiteSpace((Get-EnvVarValue -Name $_))
    }
)

if ($missingEnvVars.Length -gt 0) {
    throw "Fehlende Umgebungsvariablen: $($missingEnvVars -join ', ')"
}

# Hinweis:
# AZURE_OPENAI_API_VERSION wird hier absichtlich NICHT verwendet,
# weil wir für Option 3 den v1-Endpunkt /openai/v1 verwenden.

$projectPath = (Get-Location).Path
$sessionCodexHome = Join-Path $HOME ".codexVW"

$azureEndpoint = $AzureOpenAIEndpoint
$azureApiKey = Get-EnvVarValue -Name "AZURE_OPENAI_API_KEY"
$modelName = $AzureOpenAIDeployment

$openaiBaseUrl = Get-NormalizedOpenAIBaseUrl -AzureEndpoint $azureEndpoint

# Bisherige Session-Werte sichern, damit wir am Ende sauber zurücksetzen
$previousEnv = @{
    CODEX_HOME      = $env:CODEX_HOME
    OPENAI_BASE_URL = $env:OPENAI_BASE_URL
    OPENAI_API_KEY  = $env:OPENAI_API_KEY
}

try {
    # Isolierte Codex-Session im Projekt
    New-Item -ItemType Directory -Path $sessionCodexHome -Force | Out-Null

    $env:CODEX_HOME = $sessionCodexHome
    $env:OPENAI_BASE_URL = $openaiBaseUrl
    $env:OPENAI_API_KEY = $azureApiKey

    # Firmen-config.toml anlegen, falls nicht vorhanden
    $configFile = Join-Path $env:CODEX_HOME "config.toml"
    if (-not (Test-Path $configFile)) {
        $configContent = @'
cli_auth_credentials_store = "file"
profile = "vw"

[profiles.vw]
model_provider = "openai"
model = "gpt-5.3-codex"
approval_policy = "on-request"
sandbox_mode = "workspace-write"
'@
        New-Item -ItemType Directory -Path $env:CODEX_HOME -Force | Out-Null
        Set-Content -Path $configFile -Value $configContent -Encoding UTF8
    }

    Write-Host ""
    Write-Host "=== Firmen-Codex-Session ==="
    Write-Host "Firmen-CODEX_HOME   : $env:CODEX_HOME"
    Write-Host "OPENAI_BASE_URL     : $env:OPENAI_BASE_URL"
    Write-Host "Auth-Quelle         : AZURE_OPENAI_API_KEY -> OPENAI_API_KEY (nur temporär in diesem Prozess)"
    Write-Host "Hinweis             : Privater Codex bleibt unter ~/.codex"
    Write-Host "                    : Skills verfügbar unter ~/.agents/skills"
    Write-Host ""

    # Login-Check: nur neu authentifizieren, wenn noch kein Login vorhanden ist
    Write-Host ""
    Write-Host "=== Authentifizierung ==="
    $previousErrorAction = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    $loginCheckOutput = codex login status 2>&1
    $loginExitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousErrorAction

    if ($loginExitCode -ne 0 -or $loginCheckOutput -like "*Not logged in*") {
        Write-Host "Starte API-Key-basiertes Login..."
        $env:OPENAI_API_KEY | codex login --with-api-key
    }
    else {
        Write-Host "Bereits authentifiziert:"
        Write-Host $loginCheckOutput
    }
    Write-Host ""

    $dangerousInput = Read-Host "Dangerous mode (--dangerously-bypass-approvals-and-sandbox)? [j/N]"
    $DangerousMode = $dangerousInput -eq "j"

    $extraArgs = @()
    if ($DangerousMode) { $extraArgs += "--dangerously-bypass-approvals-and-sandbox" }

    if ([string]::IsNullOrWhiteSpace($InitialPrompt)) {
        codex --profile vw @extraArgs
    }
    else {
        codex --profile vw @extraArgs $InitialPrompt
    }
}
finally {
    Write-Host ""
    Write-Host "=== Cleanup ==="

    Restore-EnvVar -Name "CODEX_HOME" -PreviousValue $previousEnv.CODEX_HOME
    Restore-EnvVar -Name "OPENAI_BASE_URL" -PreviousValue $previousEnv.OPENAI_BASE_URL
    Restore-EnvVar -Name "OPENAI_API_KEY" -PreviousValue $previousEnv.OPENAI_API_KEY

    Write-Host "Session-Umgebungsvariablen wurden zurückgesetzt."
    Write-Host "Firmen-Daten (config, auth, history, logs) bleiben unter $sessionCodexHome erhalten."
    Write-Host ""
}