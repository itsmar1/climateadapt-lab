<# Fresh-clone verification (P19): prove a judge can clone the repo and run it.
#
#   powershell -ExecutionPolicy Bypass -File scripts/verify_fresh_clone.ps1
#
# Steps: clone into a temp dir -> uv sync -> start backend + frontend in demo
# mode (zero keys) -> probe GET /health and GET /v1/demo/snapshots (+ one
# snapshot) -> stop everything and report PASS/FAIL per step.
#
# -SkipServers runs only the offline steps (clone, sync, snapshot-file
# validation, route import check) for restricted sandboxes that block
# listen()/sockets. Needs git, uv, node 20.19+, npm on PATH.
#>
param(
    [string]$Repo = "",
    [string]$Target = "",
    [switch]$SkipServers
)

$ErrorActionPreference = "Stop"
$script:failures = @()

function Step([string]$name, [scriptblock]$body) {
    Write-Host ""
    Write-Host "=== $name ==="
    try {
        & $body
        Write-Host "PASS: $name"
    } catch {
        Write-Host "FAIL: $name -- $($_.Exception.Message)"
        $script:failures += $name
    }
}

function Need([string]$cmd, [string]$hint) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        throw "missing '$cmd' on PATH ($hint)"
    }
}

function Run-Native([string]$cmd, [string[]]$argv) {
    # Native tools chat on stderr (git "Cloning into...", uv progress); that
    # must never abort us under a Stop preference. Judge by exit code only.
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $out = & $cmd @argv 2>&1
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $prev
    }
    if ($code -ne 0) {
        throw "$cmd failed (exit $code): $($out -join "`n")"
    }
    return $out
}

function Wait-Url([string]$url, [int]$seconds, [string]$what) {
    $deadline = (Get-Date).AddSeconds($seconds)
    $last = $null
    while ((Get-Date) -lt $deadline) {
        try {
            return Invoke-RestMethod -Uri $url -TimeoutSec 10
        } catch {
            $last = $_.Exception.Message
            Start-Sleep -Seconds 3
        }
    }
    throw "$what never answered at $url (last: $last)"
}

$here = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($Repo)) {
    $Repo = ((Run-Native "git" @("-C", $here, "remote", "get-url", "origin") | Out-String)).Trim()
    if ([string]::IsNullOrWhiteSpace($Repo)) { throw "no origin remote; pass -Repo <url-or-path>" }
}
if ([string]::IsNullOrWhiteSpace($Target)) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $Target = Join-Path ([System.IO.Path]::GetTempPath()) "climateadapt-fresh-$stamp"
}
Write-Host "repo:   $Repo"
Write-Host "target: $Target"

Step "prereqs (git, uv)" {
    Need "git" "install git"
    Need "uv" "install uv (astral.sh/uv)"
}

Step "clone" {
    if (Test-Path $Target) { throw "target exists: $Target (remove it first)" }
    Run-Native "git" @("clone", "--depth", "1", $Repo, $Target) | Out-Null
    foreach ($p in @("pyproject.toml", "uv.lock", "corpus/manifest.json",
        "demo/snapshots/reference-morocco.json", "frontend/package.json")) {
        if (-not (Test-Path (Join-Path $Target $p))) { throw "missing in clone: $p" }
    }
}

Step "uv sync" {
    Push-Location $Target
    try {
        # Hermetic even from an activated venv: the clone builds its own .venv.
        Remove-Item Env:\VIRTUAL_ENV -ErrorAction SilentlyContinue
        Run-Native "uv" @("sync", "--extra", "dev", "--locked") | Out-Null
    } finally { Pop-Location }
}

Step "tracked snapshots validate (no server)" {
    Push-Location $Target
    try {
        $code = @"
from pathlib import Path
from climateadapt.api.demo import list_demo_snapshots, load_demo_snapshot
found = {s.key for s in list_demo_snapshots(Path('demo/snapshots'))}
want = {'reference-morocco', 'trondelag-norway', 'atlantic-ocean'}
assert found == want, found
snap = load_demo_snapshot(Path('demo/snapshots'), 'reference-morocco')
assert snap is not None and snap.detail.report.fallback is True
print('snapshots ok:', sorted(found))
"@
        Run-Native "uv" @("run", "--no-sync", "python", "-c", $code) | Out-Null
    } finally { Pop-Location }
}

Step "app imports with zero keys (no server)" {
    Push-Location $Target
    try {
        $env:CLIMATEADAPT_DEMO_MODE = "true"
        $code = @"
from climateadapt.api.main import create_app
paths = sorted({r.path for r in create_app().routes if getattr(r, 'path', '')})
assert '/health' in paths and '/v1/demo/snapshots' in paths, paths
print('routes ok')
"@
        Run-Native "uv" @("run", "--no-sync", "python", "-c", $code) | Out-Null
    } finally {
        Remove-Item Env:\CLIMATEADAPT_DEMO_MODE -ErrorAction SilentlyContinue
        Pop-Location
    }
}

if ($SkipServers) {
    Write-Host ""
    Write-Host "Skipping server steps (-SkipServers)."
} else {
    Step "prereqs (node 20.19+, npm)" {
        Need "node" "install Node 20.19+"
        Need "npm" "install npm with Node"
        $v = (node --version).TrimStart("v").Split(".") | ForEach-Object { [int]$_ }
        if ($v[0] -lt 20 -or ($v[0] -eq 20 -and $v[1] -lt 19)) {
            throw "node $(node --version) is below the required 20.19+"
        }
    }

    $backendJob = $null
    $frontendJob = $null
    try {
        Step "start backend (demo mode, zero keys)" {
            $backendJob = Start-Job -WorkingDirectory $Target -ScriptBlock {
                $env:CLIMATEADAPT_DEMO_MODE = "true"
                uv run --no-sync uvicorn climateadapt.api.main:app --port 8000
            }
            $health = Wait-Url "http://127.0.0.1:8000/health" 120 "backend"
            if ($health.status -ne "ok") { throw "health status: $($health.status)" }
        }

        Step "probe demo endpoints" {
            $list = Invoke-RestMethod -Uri "http://127.0.0.1:8000/v1/demo/snapshots" -TimeoutSec 15
            $keys = @($list.snapshots | ForEach-Object { $_.key })
            foreach ($k in @("reference-morocco", "trondelag-norway", "atlantic-ocean")) {
                if ($keys -notcontains $k) { throw "snapshot key missing: $k" }
            }
            $one = Invoke-RestMethod -Uri "http://127.0.0.1:8000/v1/demo/snapshots/reference-morocco" -TimeoutSec 15
            if ($one.detail.report.fallback -ne $true) { throw "snapshot is not a fallback report" }
            Write-Host "demo keys: $($keys -join ', ')"
        }

        Step "start frontend" {
            Push-Location (Join-Path $Target "frontend")
            try {
                Run-Native "npm" @("install", "--no-audit", "--no-fund") | Out-Null
            } finally { Pop-Location }
            $frontendJob = Start-Job -WorkingDirectory (Join-Path $Target "frontend") -ScriptBlock {
                $env:VITE_API_BASE_URL = "http://127.0.0.1:8000"
                npm run dev -- --port 5173 --strictPort
            }
            Wait-Url "http://localhost:5173/" 180 "frontend" | Out-Null
        }
    } finally {
        foreach ($job in @($backendJob, $frontendJob)) {
            if ($job -ne $null) {
                Stop-Job $job -ErrorAction SilentlyContinue | Out-Null
                Remove-Job $job -Force -ErrorAction SilentlyContinue | Out-Null
            }
        }
    }
}

Write-Host ""
if ($script:failures.Count -eq 0) {
    Write-Host "FRESH-CLONE CHECK: ALL STEPS PASSED"
    exit 0
} else {
    Write-Host "FRESH-CLONE CHECK: FAILED ($($script:failures -join ', '))"
    exit 1
}
