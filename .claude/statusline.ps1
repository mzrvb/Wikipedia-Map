$ErrorActionPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# Claude Code reports cost in USD only. Static conversion rate - update as needed.
$USD_TO_CAD = 1.37

# Claude Code pipes session info as JSON on stdin
$raw = [Console]::In.ReadToEnd()
$data = $raw | ConvertFrom-Json

# Glyphs by code point so this file stays pure ASCII (avoids encoding mangling)
$sep = [char]0x2502   # vertical bar
$dot = [char]0x25CF   # filled circle

$e = [char]27
$reset = "$e[0m"; $dim = "$e[90m"
$cyan = "$e[36m"; $green = "$e[32m"; $yellow = "$e[33m"; $red = "$e[31m"

$parts = @()

# --- model ---
$model = $data.model.display_name
if ($model) { $parts += "$cyan$model$reset" }

# --- git branch + dirty marker (one git call gets both) ---
$dir = $data.workspace.current_dir
if (-not $dir) { $dir = $data.cwd }
if ($dir) {
    $status = @(& git -C "$dir" status --porcelain --branch 2>$null)
    if ($status.Count -gt 0) {
        $branch = ($status[0] -replace '^## ', '' -split '\.\.\.')[0]
        if ($branch -like 'HEAD*') { $branch = 'detached' }
        $seg = "$green$branch$reset"
        # line 0 is the branch header; anything after it is a change
        if ($status.Count -gt 1) { $seg += " $yellow$dot$reset" }
        $parts += $seg
    }
}

# --- context window used ---
$ctx = $data.context_window.used_percentage
if ($null -ne $ctx) {
    $pct = [int][math]::Round($ctx)
    $c = if ($pct -lt 50) { $green } elseif ($pct -le 80) { $yellow } else { $red }
    $parts += "$c$pct% ctx$reset"
}

# --- 5-hour rate limit used ---
$rl = $data.rate_limits.five_hour.used_percentage
if ($null -ne $rl) {
    $parts += "$dim$([int][math]::Round($rl))% 5h$reset"
}

# --- session cost, converted to CAD ---
$usd = $data.cost.total_cost_usd
if ($null -ne $usd) {
    $cost = 'C$' + ('{0:N2}' -f ($usd * $USD_TO_CAD))
    $parts += "$dim$cost$reset"
}

Write-Host ($parts -join " $dim$sep$reset ") -NoNewline
