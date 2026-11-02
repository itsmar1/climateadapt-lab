<# Fresh-clone verification (P19, fixed P25): prove a judge can clone the repo and run it.
#
#   powershell -ExecutionPolicy Bypass -File scripts/verify_fresh_clone.ps1
#
# Steps: clone into a temp dir -> uv sync -> start backend + frontend in demo
# mode (zero keys) -> probe GET /health and GET /v1/demo/snapshots (+ one
# snapshot) -> stop everything and report PASS/FAIL per step.
#
# Works on Windows PowerShell 5.1 and PowerShell 7: server jobs are started
# with Start-Job plus Set-Location inside the job (Start-Job has no
# -WorkingDirectory parameter on 5.1), and no PS7-only syntax is used.
# Ports 8000/5173 are checked before anything starts; a busy port stops its
# step with a message naming the port (a leftover backend without demo mode
# answers 404 for /v1/demo/*). Node below 20.19 skips the frontend steps
# without failing the backend checks. Started jobs are always stopped.
#
# -SkipServers runs only the offline steps (clone, sync, snapshot-file
# validation, route import check) for restricted sandboxes that block
# listen()/sockets. Needs git, uv on PATH; node 20.19+ and npm only for the
# frontend steps (otherwise skipped with a pointer to Docker).
#>
param(
    [string]$Repo = "",
    [string]$Target = "",
    [switch]$SkipServers
)

$ErrorActionPreference = "Stop"
$script:failures = @()
$script:skipFrontend = $false
$script:skipReason = ""
$script:backendUp = $false
$script:backendJob = $null
$script:frontendJob = $null

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

function Test-PortOpen([int]$port) {
    # True when something already answers on 127.0.0.1:$port. Pure .NET so it
    # behaves the same on Windows PowerShell 5.1 and PowerShell 7.
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $iar = $client.BeginConnect("127.0.0.1", $port, $null, $null)
        if (-not $iar.AsyncWaitHandle.WaitOne(1500)) { return $false }
        try {
            $client.EndConnect($iar)
        } catch {
            return $false
        }
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Show-JobLog($job, [string]$what) {
    # Best-effort tail of a failed job's output for diagnosis; never throws.
    if ($job -eq $null) { return }
    try {
        $text = (Receive-Job $job -Keep -ErrorAction SilentlyContinue 2>&1 | Out-String)
        if ([string]::IsNullOrWhiteSpace($text)) { return }
        $tail = ($text -split "`n" | Select-Object -Last 20) -join "`n"
        Write-Host "$what job log (last lines):"
        Write-Host $tail
    } catch { }
}

function Invoke-DemoGet([string]$url, [string]$what) {
    # GET a demo endpoint; on failure print the raw body and the typed error
    # code (e.g. demo_mode_disabled) instead of a bare 404.
    try {
        return Invoke-RestMethod -Uri $url -TimeoutSec 15
    } catch {
        $raw = $_.ErrorDetails.Message
        if ([string]::IsNullOrWhiteSpace($raw)) { $raw = $_.Exception.Message }
        $type = "(no typed code in response)"
        try {
            $parsed = ConvertFrom-Json $raw
            # Property lookup is case-insensitive: matches "Detail"/"Detail".
            if ($parsed.Detail -ne $null -and $parsed.Detail.Count -gt 0) {
                $type = $parsed.Detail[0].type
            }
        } catch { $type = "(body is not JSON)" }
        Write-Host "$what raw response: $raw"
        throw "$what failed (type=$type). If type=demo_mode_disabled, the server on :8000 runs without CLIMATEADAPT_DEMO_MODE=true (a leftover backend?)."
    }
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
        "demo/snapshots/reference-morocco.json",
        "demo/snapshots/reference-morocco-ai.json", "frontend/package.json")) {
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
want = {'reference-morocco', 'reference-morocco-ai', 'trondelag-norway', 'atlantic-ocean'}
assert found == want, found
snap = load_demo_snapshot(Path('demo/snapshots'), 'reference-morocco')
assert snap is not None and snap.detail.report.fallback is True
ai = load_demo_snapshot(Path('demo/snapshots'), 'reference-morocco-ai')
assert ai is not None and ai.detail.report.fallback is False
assert ai.detail.report.acceptance == 'ai-accepted', ai.detail.report.acceptance
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
        $script:skipFrontend = $false
        $script:skipReason = ""
        $node = Get-Command "node" -ErrorAction SilentlyContinue
        $npm = Get-Command "npm" -ErrorAction SilentlyContinue
        if ($node -eq $null -or $npm -eq $null) {
            $script:skipFrontend = $true
            $script:skipReason = "node/npm not on PATH"
            Write-Host "Install Node 22 LTS or use ``docker compose up --build``, which builds the frontend with Node 22"
            Write-Host "SKIP: frontend steps (node or npm missing); backend checks continue."
            return
        }
        $parts = (node --version).TrimStart("v").Split(".")
        $major = [int]$parts[0]
        $minor = 0
        if ($parts.Count -gt 1) { $minor = [int]$parts[1] }
        if ($major -lt 20 -or ($major -eq 20 -and $minor -lt 19)) {
            $script:skipFrontend = $true
            $script:skipReason = "node $(node --version) is below 20.19"
            Write-Host "Install Node 22 LTS or use ``docker compose up --build``, which builds the frontend with Node 22"
            Write-Host "SKIP: frontend steps (node $(node --version) is below the required 20.19+); backend checks continue."
            return
        }
        Write-Host "node $(node --version) ok"
    }

    try {
        Step "start backend (demo mode, zero keys)" {
            if (Test-PortOpen 8000) {
                throw "Port 8000 is already in use. Stop the leftover process first (a leftover backend without demo mode answers 404 for /v1/demo/*)."
            }
            # No -WorkingDirectory here: that Start-Job parameter exists only
            # in PS 7. Set-Location inside the job works on 5.1 and 7.
            $script:backendJob = Start-Job -ScriptBlock {
                param($dir)
                Set-Location $dir
                $env:CLIMATEADAPT_DEMO_MODE = "true"
                uv run --no-sync uvicorn climateadapt.api.main:app --port 8000
            } -ArgumentList $Target
            try {
                $health = Wait-Url "http://127.0.0.1:8000/health" 120 "backend"
            } catch {
                Show-JobLog $script:backendJob "backend"
                throw
            }
            if ($health.status -ne "ok") { throw "health status: $($health.status)" }
            $script:backendUp = $true
        }

        Step "probe demo endpoints" {
            if (-not $script:backendUp) {
                Write-Host "SKIP: backend did not start; nothing to probe."
                return
            }
            $list = Invoke-DemoGet "http://127.0.0.1:8000/v1/demo/snapshots" "GET /v1/demo/snapshots"
            $keys = @($list.snapshots | ForEach-Object { $_.key })
            foreach ($k in @("reference-morocco", "reference-morocco-ai", "trondelag-norway", "atlantic-ocean")) {
                if ($keys -notcontains $k) { throw "snapshot key missing: $k" }
            }
            $one = Invoke-DemoGet "http://127.0.0.1:8000/v1/demo/snapshots/reference-morocco" "GET one snapshot"
            if ($one.detail.report.fallback -ne $true) { throw "snapshot is not a fallback report" }
            Write-Host "demo keys: $($keys -join ', ')"
        }

        Step "start frontend" {
            if ($script:skipFrontend) {
                Write-Host "SKIP: frontend steps skipped ($script:skipReason). Backend checks above still count."
                return
            }
            if (Test-PortOpen 5173) {
                throw "Port 5173 is already in use. Stop the leftover process first."
            }
            Push-Location (Join-Path $Target "frontend")
            try {
                Run-Native "npm" @("install", "--no-audit", "--no-fund") | Out-Null
            } finally { Pop-Location }
            $script:frontendJob = Start-Job -ScriptBlock {
                param($dir)
                Set-Location $dir
                $env:VITE_API_BASE_URL = "http://127.0.0.1:8000"
                npm run dev -- --port 5173 --strictPort
            } -ArgumentList (Join-Path $Target "frontend")
            try {
                Wait-Url "http://localhost:5173/" 180 "frontend" | Out-Null
            } catch {
                Show-JobLog $script:frontendJob "frontend"
                throw
            }
        }
    } finally {
        # Script-scoped job handles (Step bodies run in a child scope, so
        # plain assignment inside them would never reach this cleanup).
        foreach ($job in @($script:backendJob, $script:frontendJob)) {
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
