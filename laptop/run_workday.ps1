param(
    [string]$WatcherDir = (Split-Path $PSScriptRoot -Parent),
    [string]$ResultsDir = (Join-Path (Split-Path $PSScriptRoot -Parent) '..\internship-watcher-workday')
)
$ErrorActionPreference = 'Stop'
# Gaming mode: while VALORANT (or another listed game) runs, fetch one company at a
# time at idle priority; otherwise fetch 3 companies in parallel at below-normal priority.
$games = @('VALORANT-Win64-Shipping', 'VALORANT')
$gaming = [bool](Get-Process -Name $games -ErrorAction SilentlyContinue)
$workers = if ($gaming) { 1 } else { 3 }
(Get-Process -Id $PID).PriorityClass = if ($gaming) { 'Idle' } else { 'BelowNormal' }
$log = Join-Path $PSScriptRoot 'workday.log'
if ((Test-Path $log) -and (Get-Item $log).Length -ge 1MB) {
    for ($i = 4; $i -ge 1; $i--) {
        $old = "$log.$i"
        if (Test-Path $old) { Move-Item -Force $old "$log.$($i + 1)" }
    }
    Move-Item -Force $log "$log.1"
}
try {
    "$(Get-Date -Format o) Starting" | Out-File -Append $log
    & git -C $WatcherDir pull --ff-only *>> $log
    if ($LASTEXITCODE -ne 0) { throw 'Watcher git pull failed' }
    "$(Get-Date -Format o) Gaming mode: $gaming (workers $workers)" | Out-File -Append $log
    & py -3.12 (Join-Path $WatcherDir 'workday_fetch.py') --push $ResultsDir --workers $workers *>> $log
    if ($LASTEXITCODE -ne 0) { throw 'Workday fetch or push failed' }
    "$(Get-Date -Format o) Finished" | Out-File -Append $log
} catch {
    "$(Get-Date -Format o) ERROR: $_" | Out-File -Append $log
    exit 1
}
