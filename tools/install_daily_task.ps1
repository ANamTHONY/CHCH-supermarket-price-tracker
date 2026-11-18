param(
    [string]$At = '09:15',
    [switch]$DryRun,
    [switch]$ReturnToHibernate
)
$ErrorActionPreference = 'Stop'
$workspace = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$python = Join-Path $workspace '.venv\Scripts\pythonw.exe'
$launcher = Join-Path $workspace 'tools\scheduled_daily.py'
if (-not (Test-Path -LiteralPath $python)) { throw 'Virtual environment pythonw.exe is missing' }
if ((Get-TimeZone).Id -ne 'New Zealand Standard Time') { throw 'Expected New Zealand system time zone' }
$time = [TimeSpan]::ParseExact($At, 'hh\:mm', [Globalization.CultureInfo]::InvariantCulture)
$first = (Get-Date).Date.Add($time)
if ($first -le (Get-Date)) { $first = $first.AddDays(1) }
$arguments = '"{0}" --after {1}' -f $launcher, $At
if ($DryRun) { $arguments += ' --dry-run' }
if (-not $ReturnToHibernate) { $arguments += ' --no-hibernate' }
$action = New-ScheduledTaskAction -Execute $python -Argument $arguments -WorkingDirectory $workspace
$daily = New-ScheduledTaskTrigger -Daily -At $first
$identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -WakeToRun -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 4)
$task = New-ScheduledTask -Action $action -Trigger @($daily) -Principal $principal -Settings $settings `
    -Description 'Daily 09:15 NZ collection. Requires signed-in user. Hibernate after confirmed success only when unattended; keyboard/mouse cancels.'
Register-ScheduledTask -TaskName 'PriceTracker-Daily' -InputObject $task -Force | Out-Null
Get-ScheduledTask -TaskName 'PriceTracker-Daily' | Select-Object TaskName, State,
    @{Name='WakeToRun';Expression={$_.Settings.WakeToRun}},
    @{Name='LogonType';Expression={$_.Principal.LogonType}},
    @{Name='Arguments';Expression={$_.Actions.Arguments}}
Get-ScheduledTaskInfo -TaskName 'PriceTracker-Daily' | Select-Object NextRunTime, LastTaskResult
