#Requires -Version 5.1
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$supportRoot = $PSScriptRoot
if(Test-Path -LiteralPath (Join-Path $supportRoot 'src\Diagnostics.ps1')){$supportRoot=Join-Path $supportRoot 'src'}
. (Join-Path $supportRoot 'Diagnostics.ps1')
. (Join-Path $supportRoot 'Common.ps1')
$errors = New-Object 'System.Collections.Generic.List[string]'
$o = [pscustomobject]@{
    Platform=[string][Environment]::OSVersion.Platform; Build=[Environment]::OSVersion.Version.Build
    Architecture=$env:PROCESSOR_ARCHITECTURE; ClientOS=$null
    NativePowerShell=([Environment]::Is64BitProcess -and $PSVersionTable.PSEdition -eq 'Desktop' -and $PSVersionTable.PSVersion.Major -eq 5 -and $PSVersionTable.PSVersion.Minor -eq 1)
    Elevated=$false; Errors=$errors; TaskPresent=$false; LegacyTaskPresent=$false; TaskState=$null
    FilesPresent=$false; FilesComplete=$false; ActionMatches=$false; StartupEnabled=$false; ConfigValid=$true
    HasRun=$false; LastTaskResult=$null; LogMatchesRun=$false; LogOutcome='missing'
}
if($env:PROCESSOR_ARCHITEW6432){$o.Architecture=$env:PROCESSOR_ARCHITEW6432}
$taskName=$null; $lastRunTime=$null; $configExists=$false
if($o.Platform -eq 'Win32NT') {
    try {
        $os=Get-CimInstance Win32_OperatingSystem -ErrorAction Stop
        $o.Build=[int]$os.BuildNumber; $o.ClientOS=($os.ProductType -eq 1)
    } catch {$errors.Add('os_query_failed')}
    try {
        $identity=[Security.Principal.WindowsIdentity]::GetCurrent()
        $sid=$identity.User.Value
        $principal=New-Object Security.Principal.WindowsPrincipal($identity)
        $o.Elevated=$principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
        $taskName="Compact Task Manager ($sid)"
        $programRoot=$env:ProgramFiles; if($env:ProgramW6432){$programRoot=$env:ProgramW6432}
        $installRoot=Join-Path $programRoot "CompactTaskManager\$sid"
        $dataRoot=Join-Path $env:USERPROFILE 'CompactTaskManager'
        $required=@('Start-CompactTaskManager.ps1','Common.ps1','Uninstall.ps1')
        $present=@($required | Where-Object {Test-Path -LiteralPath (Join-Path $installRoot $_) -PathType Leaf})
        $o.FilesPresent=($present.Count -gt 0); $o.FilesComplete=($present.Count -eq $required.Count)
        $configPath=Join-Path $dataRoot 'config.json'
        $configExists=Test-Path -LiteralPath $configPath -PathType Leaf
        try {$null=Read-CompactConfig $configPath} catch {$o.ConfigValid=$false}
        try {
            $tasks=@(Get-ScheduledTask -ErrorAction Stop)
            $task=$tasks | Where-Object {$_.TaskName -eq $taskName -and $_.TaskPath -eq '\'} | Select-Object -First 1
            $o.LegacyTaskPresent=(@($tasks | Where-Object {$_.TaskName -eq 'Task Manager - Compact Performance'}).Count -gt 0)
            if($task) {
                $o.TaskPresent=$true; $o.TaskState=[string]$task.State
                $info=$task | Get-ScheduledTaskInfo -ErrorAction Stop
                $lastRunTime=$info.LastRunTime
                $o.HasRun=($lastRunTime.Year -gt 2000)
                $o.LastTaskResult=[long]$info.LastTaskResult
                $expectedArgs='-NoProfile -NonInteractive -WindowStyle Hidden -File "'+(Join-Path $installRoot 'Start-CompactTaskManager.ps1')+'" -RestartTaskManager'
                $actions=@($task.Actions)
                $o.ActionMatches=($actions.Count -eq 1 -and $actions[0].Execute -ieq "$env:WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe" -and $actions[0].Arguments -ceq $expectedArgs -and [string]$task.Principal.RunLevel -eq 'Highest' -and [string]$task.Principal.LogonType -eq 'Interactive')
                function Resolve-AccountSid($Account) {
                    if($Account -match '^S-1-'){return $Account}
                    return (New-Object Security.Principal.NTAccount($Account)).Translate([Security.Principal.SecurityIdentifier]).Value
                }
                $o.ActionMatches=($o.ActionMatches -and (Resolve-AccountSid $task.Principal.UserId) -eq $sid)
                $o.StartupEnabled=(@($task.Triggers | Where-Object {$_.CimClass.CimClassName -eq 'MSFT_TaskLogonTrigger' -and $_.Enabled -and $_.UserId -and (Resolve-AccountSid $_.UserId) -eq $sid}).Count -gt 0)
            }
        } catch {$errors.Add('task_query_failed')}
        $logPath=Join-Path $dataRoot 'last-run.log'
        if(Test-Path -LiteralPath $logPath -PathType Leaf) {
            try {
                $evidence=Get-CompactRunEvidence -Lines @(Get-Content -LiteralPath $logPath) -LastRunTime $lastRunTime
                $o.LogOutcome=$evidence.outcome; $o.LogMatchesRun=$evidence.matchesRun
            } catch {$errors.Add('log_read_failed')}
        }
    } catch {$errors.Add('installation_query_failed')}
}
$decision=Get-CompactDiagnosis $o
[pscustomobject]@{
    schemaVersion=1
    checkedAt=[DateTimeOffset]::UtcNow.ToString('o')
    status=$decision.status
    compatibility=[pscustomobject]@{platform=$o.Platform; build=$o.Build; architecture=$o.Architecture; clientOS=$o.ClientOS; nativeWindowsPowerShell=$o.NativePowerShell; elevated=$o.Elevated}
    installation=[pscustomobject]@{taskPresent=$o.TaskPresent; legacyTaskPresent=$o.LegacyTaskPresent; requiredFilesPresent=$o.FilesComplete; taskActionMatches=$o.ActionMatches; startupTriggerEnabled=$o.StartupEnabled; configurationPresent=$configExists; configurationValid=$o.ConfigValid; taskState=$o.TaskState}
    lastRun=[pscustomobject]@{hasRun=$o.HasRun; time=$(if($o.HasRun){$lastRunTime.ToUniversalTime().ToString('o')}else{$null}); result=$o.LastTaskResult; logOutcome=$o.LogOutcome; logMatchesRun=$o.LogMatchesRun}
    visualVerification='not_performed'
    errors=@($errors.ToArray())
    nextAction=$decision.nextAction
} | ConvertTo-Json -Depth 6
# Nonzero exit means the diagnostic command itself could not complete its checks,
# not simply that the application is absent or needs attention.
if($errors.Count -gt 0){exit 1}
exit 0
