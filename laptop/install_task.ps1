param(
    [string]$WatcherDir = (Split-Path $PSScriptRoot -Parent),
    [string]$ResultsDir = (Join-Path (Split-Path $PSScriptRoot -Parent) '..\internship-watcher-workday'),
    [string]$TaskName = 'InternshipWatcherWorkday',
    [ValidateRange(10, 60)][int]$IntervalMinutes = 30
)
$ErrorActionPreference = 'Stop'
$script = Join-Path $WatcherDir 'laptop\run_workday.ps1'
$arguments = "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$script`" -WatcherDir `"$WatcherDir`" -ResultsDir `"$ResultsDir`""
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arguments
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -MultipleInstances IgnoreNew
# Remove the finite repetition duration so the trigger repeats indefinitely.
$trigger.Repetition.Duration = $null
$credential = Get-Credential -UserName "$env:USERDOMAIN\$env:USERNAME" -Message 'Enter the Windows account password for the scheduled task'
Register-ScheduledTask -Password $credential.GetNetworkCredential().Password -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -User $credential.UserName -RunLevel Limited -Force
