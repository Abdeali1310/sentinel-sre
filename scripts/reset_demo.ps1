# scripts/reset_demo.ps1
# Resets the demo environment to a clean state.

Write-Host "Stopping containers..." -ForegroundColor Cyan
docker compose down

Write-Host "Rebuilding and starting containers..." -ForegroundColor Cyan
docker compose up -d --build

Write-Host "Waiting for services to become healthy..." -ForegroundColor Cyan
Start-Sleep -Seconds 10

Write-Host "Checking health endpoints..." -ForegroundColor Cyan
try {
    $response = Invoke-RestMethod -Uri "http://localhost:8001/healthz" -Method Get
    Write-Host "Health check: $($response.status)" -ForegroundColor Green
} catch {
    Write-Host "Health check failed: $_" -ForegroundColor Red
}

Write-Host "Resetting chaos state..." -ForegroundColor Cyan
try {
    Invoke-RestMethod -Uri "http://localhost:8001/admin/chaos" -Method Delete -Headers @{ "X-Chaos-Token" = $env:CHAOS_TOKEN } | Out-Null
    Write-Host "Chaos state cleared." -ForegroundColor Green
} catch {
    Write-Host "Chaos reset skipped (may not be active)." -ForegroundColor Yellow
}

Write-Host "Demo reset complete." -ForegroundColor Green