param([string]$TaskName = 'InternshipWatcherWorkday')
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
