# ============================================================
#  Install WeChatAutoLogin as a Task Scheduler "at logon" task.
#
#  Why higher priority than the Startup folder:
#    Startup-folder apps are launched by Explorer AFTER the
#    shell and most logon processing finish. A scheduled task
#    with an AtLogOn trigger is started by the Task Scheduler
#    service much earlier and more reliably, so this helper is
#    already waiting when WeChat opens its login page.
#
#  This script computes the absolute path of wechat_autologin.py
#  from its own location, so the whole folder can live anywhere.
#  Run by double-clicking install_task.bat. Creating the task needs
#  administrator rights on some systems (Group Policy / hardening);
#  install_task.bat requests elevation (UAC) automatically when needed.
# ============================================================
$ErrorActionPreference = 'Stop'

$taskName = 'WeChatAutoLogin'

$scriptRoot = $PSScriptRoot
$script = Join-Path $scriptRoot 'wechat_autologin.py'
if (-not (Test-Path -LiteralPath $script)) {
    Write-Host '[ERROR] wechat_autologin.py not found next to this file.'
    exit 1
}

# Prefer the pythonw.exe next to the python on PATH (falls back to PATH lookup).
$pyw = 'pythonw'
$pyCmd = Get-Command python -ErrorAction SilentlyContinue
if ($pyCmd) {
    $candidate = Join-Path (Split-Path -Parent $pyCmd.Source) 'pythonw.exe'
    if (Test-Path -LiteralPath $candidate) { $pyw = $candidate }
}

# Seconds to wait after logon before running (lets the desktop settle).
# 0 = start immediately at logon.
$delaySec = 5

$action = New-ScheduledTaskAction -Execute $pyw `
    -Argument ('"{0}" --watch' -f $script) -WorkingDirectory $scriptRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn
if ($delaySec -gt 0) {
    $trigger.Delay = 'PT' + $delaySec + 'S'
}
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $taskName -Action $action `
    -Trigger $trigger -Settings $settings -Force | Out-Null

Write-Host "[OK] Task '$taskName' registered:"
Write-Host "     trigger : at logon (delay ${delaySec}s)"
Write-Host "     action  : ""$pyw"" ""$script"" --watch"
Write-Host "     note    : stdout/stderr go to the log file next to the script"
Write-Host "     verify  : schtasks /Query /TN $taskName /V /FO LIST"