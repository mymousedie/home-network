<#
Registers a daily Windows scheduled task that runs the OPNsense config backup.
Run once from this folder in a normal (non-admin) PowerShell:

    .\register_task.ps1                 # daily at 03:00
    .\register_task.ps1 -Time 22:30
    .\register_task.ps1 -Remove         # unregister

The task runs as you, only while you are logged on, so credentials in
backup.json stay readable only by your account. StartWhenAvailable means a
missed run (PC off at 03:00) happens at next boot/login.
#>
param(
    [string]$Time = "03:00",
    [string]$TaskName = "OPNsense Config Backup",
    [switch]$Remove
)
$ErrorActionPreference = "Stop"

if ($Remove) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed '$TaskName'."
    return
}

$here   = Split-Path -Parent $MyInvocation.MyCommand.Path
$script = Join-Path $here "opnsense_backup.py"
$config = Join-Path $here "backup.json"
if (-not (Test-Path $config)) { throw "backup.json not found. Copy backup.example.json and fill it in first." }
$python = (Get-Command python).Source

Write-Host "Testing the backup once before scheduling..."
& $python $script --config $config --check
if ($LASTEXITCODE -ne 0) { throw "Test run failed; fix the error above, then re-run this script." }

$action   = New-ScheduledTaskAction -Execute $python -Argument "`"$script`" --config `"$config`"" -WorkingDirectory $here
$trigger  = New-ScheduledTaskTrigger -Daily -At $Time
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable `
            -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Description "Daily OPNsense config.xml backup (see backup/README.md)" -Force | Out-Null
Write-Host "Registered '$TaskName' daily at $Time. Run it now with:  Start-ScheduledTask -TaskName '$TaskName'"
