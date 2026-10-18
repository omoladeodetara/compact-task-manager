# Pure decision logic: no OS calls or changes. Also used by fixture-based tests.
function Get-CompactRunEvidence {
    param([string[]]$Lines, $LastRunTime)
    $started=$null; $ended=$null; $outcome='missing'; $matchesRun=$false
    foreach($line in $Lines) {
        if($line -match '^(\S+) Starting$') {$started=[DateTimeOffset]::Parse($Matches[1]); $ended=$null; $outcome='incomplete'}
        elseif($line -match '^(\S+) (SUCCESS:|ERROR:)') {
            $ended=[DateTimeOffset]::Parse($Matches[1])
            if($Matches[2] -eq 'SUCCESS:'){$outcome='success'}else{$outcome='error'}
        }
    }
    if($LastRunTime -and $started -and $ended) {
        $runUtc=$LastRunTime.ToUniversalTime()
        $matchesRun=([Math]::Abs(($started.UtcDateTime-$runUtc).TotalSeconds) -le 5 -and $ended -ge $started -and ($ended-$started).TotalSeconds -le 130)
    }
    return [pscustomobject]@{outcome=$outcome; matchesRun=$matchesRun}
}

function Get-CompactDiagnosis {
    param($Observation)
    $o = $Observation
    $status = 'unknown'; $code = 'inspect_diagnostic_errors'
    $message = 'Some checks could not be completed. Review the reported check errors.'
    $requiresElevation = $false
    if ($o.Platform -ne 'Win32NT') {
        $status='unsupported'; $code='use_supported_windows'; $message='This release targets Windows 11 22H2+ x64 desktop editions.'
    } elseif ($o.Errors.Count -gt 0) {
        $code='retry_failed_checks'; $requiresElevation=(!$o.Elevated)
        $message='A check failed. Retry in the intended Windows account; if access was denied, request human-approved elevation.'
    } elseif (($null -ne $o.ClientOS -and !$o.ClientOS) -or $o.Build -lt 22621 -or $o.Architecture -ne 'AMD64') {
        $status='unsupported'; $code='use_supported_windows'; $message='This release targets Windows 11 22H2+ x64 desktop editions.'
    } elseif (!$o.NativePowerShell) {
        $status='wrong_shell'; $code='use_native_windows_powershell'; $message='Run this command in 64-bit Windows PowerShell 5.1.'
    } elseif (!$o.TaskPresent -and $o.LegacyTaskPresent) {
        $status='legacy_installation'; $code='review_existing_installation'; $message='The original personal helper task exists. Review it before installing this release to avoid duplicate startup tasks.'
    } elseif (!$o.TaskPresent) {
        $status='not_installed'; if($o.FilesPresent){$status='partial_installation'}
        $code='install'; $requiresElevation=$true; $message='Review the source, then run Install.ps1 -StartNow as the intended user with administrator approval.'
    } elseif (!$o.FilesComplete -or !$o.ActionMatches) {
        $status='partial_installation'; $code='repair_installation'; $requiresElevation=$true; $message='Installed files or task action do not match this project. Review and rerun Install.ps1.'
    } elseif (!$o.ConfigValid) {
        $status='invalid_configuration'; $code='fix_configuration'; $message='Correct config.json using config.example.json, then run the task again.'
    } elseif ($o.TaskState -eq 'Disabled') {
        $status='disabled'; $code='enable_task'; $requiresElevation=$true; $message='Enable this project task in Task Scheduler if startup is desired.'
    } elseif (!$o.StartupEnabled) {
        $status='partial_installation'; $code='repair_startup_trigger'; $requiresElevation=$true; $message='No enabled sign-in trigger matches the intended user. Review and rerun Install.ps1.'
    } elseif ($o.TaskState -in @('Running','Queued')) {
        $status='running'; $code='wait_then_diagnose'; $message='The task is still running or queued. Wait for completion and run Diagnose.ps1 again.'
    } elseif (!$o.HasRun) {
        $status='not_tested'; $code='run_task'; $message='Run this project task in an unlocked desktop session, then diagnose again.'
    } elseif ($o.LastTaskResult -ne 0) {
        $status='failed'; $code='inspect_run_log'; $message='Read the local last-run.log and Task Scheduler result, resolve the error, then rerun the task.'
    } elseif (!$o.LogMatchesRun -or $o.LogOutcome -ne 'success') {
        $status='unverified'; $code='verify_fresh_run'; $message='A matching successful log is missing. Run the task and check a fresh completed result.'
    } else {
        $status='healthy'; $code='visually_verify_widget'; $message='The latest completed task and log agree on success. Visually confirm dark Summary view and placement; sign-in behavior is not proven by this check.'
    }
    return [pscustomobject]@{status=$status; nextAction=[pscustomobject]@{code=$code; message=$message; requiresElevation=$requiresElevation}}
}
