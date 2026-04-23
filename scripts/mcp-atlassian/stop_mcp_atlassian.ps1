# Stop MCP Atlassian Docker Container

Write-Host "Stopping MCP Atlassian Docker Container..." -ForegroundColor Yellow

# Resolve compose file path relative to this script
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$composeFile = Join-Path $scriptDir "docker-compose.mcp-atlassian.yml"

# Stop container
docker-compose -f $composeFile down

Write-Host "MCP Atlassian stopped." -ForegroundColor Green
