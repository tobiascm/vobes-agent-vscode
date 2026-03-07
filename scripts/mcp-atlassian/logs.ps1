# Show MCP Atlassian Docker Container Logs

Write-Host "Showing MCP Atlassian logs (Press Ctrl+C to exit)..." -ForegroundColor Cyan
Write-Host ""

docker logs mcp-atlassian -f --tail 100
