# Stop MCP Atlassian Docker Container

Write-Host "Stopping MCP Atlassian Docker Container..." -ForegroundColor Yellow

# Navigate to project root
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent (Split-Path -Parent $scriptDir)
Set-Location $projectRoot

# Stop container
docker-compose -f docker-compose.mcp-atlassian.yml down

Write-Host "MCP Atlassian stopped." -ForegroundColor Green
