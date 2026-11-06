# Deploy Sentinel to the local Docker Compose stack.
#
# Fixed and argument-free on purpose: the agent may ask for a deploy, it may not
# compose one. Run it from the repository root. The script refuses a checkout it
# cannot trust, pulls `main` fast-forward only, rebuilds, and waits for the API
# to answer.
#
# Exit codes
#   0  deployed, healthz answered
#   1  not a Sentinel checkout
#   2  working tree is dirty
#   3  git pull --ff-only failed
#   4  HEAD is not origin/main
#   5  docker compose up failed
#   6  healthz did not answer within 120 s

$ErrorActionPreference = 'Stop'
$root = (Get-Location).Path

function Exit-With([int]$Code, [string]$Message) {
    [Console]::Error.WriteLine($Message)
    exit $Code
}

if (-not (Test-Path (Join-Path $root '.git')) -or
    -not (Test-Path (Join-Path $root 'docker-compose.yml'))) {
    Exit-With 1 "not a Sentinel checkout: $root"
}

Push-Location $root
try {
    $dirty = @(git status --porcelain)
    if ($LASTEXITCODE -ne 0) { Exit-With 1 "git status failed in $root" }
    if ($dirty.Count -gt 0) {
        Exit-With 2 "refusing to deploy: $($dirty.Count) uncommitted path(s) in $root"
    }

    git pull --ff-only
    if ($LASTEXITCODE -ne 0) { Exit-With 3 'refusing to deploy: git pull --ff-only failed' }

    $head = (git rev-parse HEAD).Trim()
    $remote = (git rev-parse 'origin/main').Trim()
    if ($head -ne $remote) {
        Exit-With 4 "refusing to deploy: HEAD $head is not origin/main $remote"
    }

    Write-Output "building $head"
    docker compose -f docker-compose.yml up -d --build
    if ($LASTEXITCODE -ne 0) { Exit-With 5 'docker compose up failed' }

    $started = Get-Date
    $deadline = $started.AddSeconds(120)
    while ((Get-Date) -lt $deadline) {
        try {
            $health = Invoke-WebRequest -Uri 'http://localhost:8001/healthz' -TimeoutSec 5 -UseBasicParsing
            if ($health.StatusCode -eq 200) {
                $elapsed = [int]((Get-Date) - $started).TotalSeconds
                Write-Output "deployed $head, healthz ok after ${elapsed}s"
                exit 0
            }
        } catch {
            # The container is still starting; the loop owns the timeout.
        }
        Start-Sleep -Seconds 2
    }
    Exit-With 6 'healthz did not answer within 120 s'
}
finally {
    Pop-Location
}
