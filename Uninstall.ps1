#Requires -Version 5.1
#Requires -RunAsAdministrator
$ErrorActionPreference = 'Stop'
if (![Environment]::Is64BitProcess) { throw 'Use 64-bit Windows PowerShell to uninstall.' }
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$taskName = "Compact Task Manager ($sid)"
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($task) {
    Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}
$installRoot = Join-Path $env:ProgramFiles "CompactTaskManager\$sid"
# Only remove our known files. Preserve config, backups, logs, and unrelated files.
foreach ($name in @('Start-CompactTaskManager.ps1', 'Common.ps1', 'Diagnostics.ps1', 'Diagnose.ps1', 'Uninstall.ps1')) {
    $path = Join-Path $installRoot $name
    if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path }
}
Write-Output 'Startup task removed. Your configuration and Task Manager preferences were retained.'
