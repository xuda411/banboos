# handoff-sync.ps1 — Codex x Trae Git channel sync helper
# Usage:
#   .\handoff-sync.ps1 status
#   .\handoff-sync.ps1 pull
#   .\handoff-sync.ps1 push  -Task T-005 -Role trae
param(
    [Parameter(Position = 0)]
    [ValidateSet("status", "pull", "push")]
    [string]$Action = "status",
    [string]$Task = "",
    [ValidateSet("trae", "codex")]
    [string]$Role = "trae"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $RepoRoot

function Ensure-Git {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        $machinePath = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
        $userPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
        $env:Path = "$machinePath;$userPath"
    }
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        throw "git not found. Install Git for Windows."
    }
}

function Get-TrackedRemote {
    $remote = git remote 2>$null
    if ($remote -notcontains "origin") { return $null }
    return (git remote get-url origin)
}

Ensure-Git
$branch = git rev-parse --abbrev-ref HEAD

switch ($Action) {
    "status" {
        Write-Host "=== Handoff channel status ==="
        Write-Host "repo   : $RepoRoot"
        Write-Host "branch : $branch"
        $url = Get-TrackedRemote
        if ($url) {
            Write-Host "origin : $url"
            git fetch origin --quiet
            $behind = (git rev-list --count "$branch..origin/$branch" 2>$null)
            $ahead = (git rev-list --count "origin/$branch..$branch" 2>$null)
            Write-Host "ahead  : $ahead"
            Write-Host "behind : $behind"
        } else {
            Write-Host "origin : NOT CONFIGURED"
        }
        Write-Host "--- working tree (first 15) ---"
        git status --short | Select-Object -First 15
    }

    "pull" {
        $url = Get-TrackedRemote
        if (-not $url) { throw "origin remote not configured." }
        $dirty = git status --porcelain
        if ($dirty) {
            throw "Working tree is dirty. Stash/commit before pull. Run: git stash"
        }
        git fetch origin
        $base = git merge-base HEAD "origin/$branch"
        $head = git rev-parse HEAD
        if ($base -eq $head) {
            git merge --ff-only "origin/$branch"
            Write-Host "PULL OK (fast-forward)."
        } else {
            git merge --no-edit "origin/$branch"
            Write-Host "PULL OK (merge commit)."
        }
    }

    "push" {
        if (-not $Task) { throw "push requires -Task, e.g. -Task T-005" }
        $url = Get-TrackedRemote
        if (-not $url) { throw "origin remote not configured." }

        git add -A
        $staged = git diff --cached --name-only
        if (-not $staged) {
            Write-Host "Nothing to commit."
        } else {
            $msg = "[$Task] $Role handoff delivery"
            git commit -m $msg | Out-Null
            Write-Host "Committed as $Task by $Role :"
            $staged | ForEach-Object { Write-Host "  $_" }
        }

        git fetch origin
        $base = git merge-base HEAD "origin/$branch" 2>$null
        $remoteHead = git rev-parse "origin/$branch" 2>$null
        if ($base -ne $remoteHead) {
            git merge --no-edit "origin/$branch"
            Write-Host "Merged remote changes."
        }
        git push origin $branch
        Write-Host "PUSH OK -> $url ($branch)"
    }
}
