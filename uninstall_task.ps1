# ============================================================
#  Remove the WeChatAutoLogin scheduled task.
# ============================================================
$ErrorActionPreference = 'Stop'
$taskName = 'WeChatAutoLogin'
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($task) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "[OK] Scheduled task '$taskName' removed."
} else {
    Write-Host "Scheduled task '$taskName' does not exist."
}