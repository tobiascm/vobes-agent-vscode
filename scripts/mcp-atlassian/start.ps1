# Start MCP Atlassian Docker Container
# Requires: Docker Desktop, JIRA_PAT and CONFLUENCE_PAT environment variables

Write-Host "Starting MCP Atlassian Docker Container..." -ForegroundColor Green

# Check if environment variables are set
if (-not $env:JIRA_PAT) {
    Write-Host "ERROR: JIRA_PAT environment variable not set!" -ForegroundColor Red
    exit 1
}

if (-not $env:CONFLUENCE_PAT) {
    Write-Host "ERROR: CONFLUENCE_PAT environment variable not set!" -ForegroundColor Red
    exit 1
}

# Navigate to project root
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent (Split-Path -Parent $scriptDir)
Set-Location $projectRoot

# Pull latest image
Write-Host "Pulling latest MCP Atlassian image..." -ForegroundColor Cyan
docker pull ghcr.io/sooperset/mcp-atlassian:0.21

# Start container
Write-Host "Starting container..." -ForegroundColor Cyan
docker-compose -f docker-compose.mcp-atlassian.yml up -d

# Wait for container to be ready
Write-Host "Waiting for container to be ready..." -ForegroundColor Cyan
Start-Sleep -Seconds 5

# Check container status
$status = docker ps --filter "name=mcp-atlassian" --format "{{.Status}}"
if ($status -like "*Up*") {
    Write-Host "MCP Atlassian is running!" -ForegroundColor Green
    Write-Host "Container Status: $status" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Configuration:" -ForegroundColor Yellow
    Write-Host "  - Host: 127.0.0.1" -ForegroundColor Gray
    Write-Host "  - Port: 8100" -ForegroundColor Gray
    Write-Host "  - Jira: https://devstack.vwgroup.com/jira" -ForegroundColor Gray
    Write-Host "  - Confluence: https://devstack.vwgroup.com/confluence" -ForegroundColor Gray
    Write-Host ""
    Write-Host "View logs: docker logs mcp-atlassian -f" -ForegroundColor Yellow
} else {
    Write-Host "ERROR: Container failed to start!" -ForegroundColor Red
    Write-Host "Check logs: docker logs mcp-atlassian" -ForegroundColor Yellow
    exit 1
}
