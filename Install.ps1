#Requires -Version 5.1
#Requires -RunAsAdministrator
[CmdletBinding()]
param([switch]$StartNow)
$ErrorActionPreference = 'Stop'
if (![Environment]::Is64BitProcess) { throw 'Use 64-bit Windows PowerShell to install.' }
if ([Environment]::OSVersion.Version.Build -lt 22621) { throw 'Windows 11 22H2 or newer is required.' }
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$taskName = "Compact Task Manager ($sid)"
$installRoot = Join-Path $env:ProgramFiles "CompactTaskManager\$sid"
$dataRoot = Join-Path $env:USERPROFILE 'CompactTaskManager'
# Program Files protects the elevated scripts from modification by ordinary processes.
# Refuse existing directories writable by non-administrators or redirected elsewhere.
foreach ($directory in @((Join-Path $env:ProgramFiles 'CompactTaskManager'), $installRoot)) {
    if (Test-Path -LiteralPath $directory) {
        $item = Get-Item -LiteralPath $directory
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Refusing redirected directory: $directory" }
        foreach ($rule in (Get-Acl -LiteralPath $directory).Access) {
            $ruleSid = $rule.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value
            $writeMask = [Security.AccessControl.FileSystemRights]'WriteData,AppendData,WriteAttributes,WriteExtendedAttributes,Delete,DeleteSubdirectoriesAndFiles,ChangePermissions,TakeOwnership'
            if ($rule.AccessControlType -eq 'Allow' -and ($rule.FileSystemRights -band $writeMask) -ne 0 -and
                $ruleSid -notin @('S-1-5-18', 'S-1-5-32-544', 'S-1-3-0', 'S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464')) {
                throw "Installation directory has an unexpected writable ACL: $directory"
            }
        }
    }
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    $acl = New-Object Security.AccessControl.DirectorySecurity
    $acl.SetAccessRuleProtection($true, $false)
    $acl.SetOwner((New-Object Security.Principal.SecurityIdentifier('S-1-5-32-544')))
    foreach ($entry in @(@('S-1-5-18', 'FullControl'), @('S-1-5-32-544', 'FullControl'), @('S-1-5-32-545', 'ReadAndExecute'))) {
        $identity = New-Object Security.Principal.SecurityIdentifier($entry[0])
        $rule = New-Object Security.AccessControl.FileSystemAccessRule($identity, $entry[1], 'ContainerInherit,ObjectInherit', 'None', 'Allow')
        $acl.AddAccessRule($rule)
    }
    Set-Acl -LiteralPath $directory -AclObject $acl
}
New-Item -ItemType Directory -Path $dataRoot -Force | Out-Null
foreach ($file in @('Start-CompactTaskManager.ps1', 'Common.ps1')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot "src\$file") -Destination (Join-Path $installRoot $file) -Force
}
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'Uninstall.ps1') -Destination (Join-Path $installRoot 'Uninstall.ps1') -Force
if (!(Test-Path -LiteralPath (Join-Path $dataRoot 'config.json'))) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'config.example.json') -Destination (Join-Path $dataRoot 'config.json')
}
. (Join-Path $installRoot 'Common.ps1')
$null = Read-CompactConfig (Join-Path $dataRoot 'config.json')
$scriptPath = Join-Path $installRoot 'Start-CompactTaskManager.ps1'
$action = New-ScheduledTaskAction -Execute "$env:WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe" -Argument ('-NoProfile -NonInteractive -WindowStyle Hidden -File "' + $scriptPath + '" -RestartTaskManager') -WorkingDirectory $installRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $sid
$trigger.Delay = 'PT15S'
$principal = New-ScheduledTaskPrincipal -UserId $sid -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 2)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Open Windows Task Manager in dark compact Performance Summary view at sign-in.' -Force | Out-Null
if ($StartNow) { Start-ScheduledTask -TaskName $taskName }
Write-Output "Installed: $taskName"
Write-Output "Configuration: $dataRoot\config.json"
Write-Output "Uninstaller: $installRoot\Uninstall.ps1"
