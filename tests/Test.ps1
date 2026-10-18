#Requires -Version 5.1
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot
foreach ($file in (Get-ChildItem -LiteralPath $root -Filter '*.ps1' -Recurse)) {
    $tokens = $null; $errors = $null
    $null = [Management.Automation.Language.Parser]::ParseFile($file.FullName, [ref]$tokens, [ref]$errors)
    if ($errors) { throw ($errors | Out-String) }
}
. (Join-Path $root 'src\Common.ps1')
. (Join-Path $root 'src\Diagnostics.ps1')
$source = Get-Content -LiteralPath (Join-Path $root 'src\Start-CompactTaskManager.ps1') -Raw
$nativeCode = [regex]::Match($source, '(?s)Add-Type @"\r?\n(.*?)\r?\n"@').Groups[1].Value
if (!$nativeCode) { throw 'Native interop source was not found.' }
Add-Type -TypeDefinition $nativeCode
function Assert($Value, $Message) { if (!$Value) { throw $Message } }
function New-DiagnosticFixture {
    return [pscustomobject]@{
        Platform='Win32NT'; Build=26200; Architecture='AMD64'; ClientOS=$true; NativePowerShell=$true
        Elevated=$false; Errors=@(); TaskPresent=$true; LegacyTaskPresent=$false; TaskState='Ready'
        FilesPresent=$true; FilesComplete=$true; ActionMatches=$true; StartupEnabled=$true; ConfigValid=$true
        HasRun=$true; LastTaskResult=0; LogMatchesRun=$true; LogOutcome='success'
    }
}
foreach($case in @(
    @{Changes=@{}; Expected='healthy'},
    @{Changes=@{Platform='Unix'}; Expected='unsupported'},
    @{Changes=@{Build=19045}; Expected='unsupported'},
    @{Changes=@{Architecture='ARM64'}; Expected='unsupported'},
    @{Changes=@{ClientOS=$false}; Expected='unsupported'},
    @{Changes=@{NativePowerShell=$false}; Expected='wrong_shell'},
    @{Changes=@{Errors=@('task_query_failed');TaskPresent=$false}; Expected='unknown'},
    @{Changes=@{TaskPresent=$false;FilesPresent=$false}; Expected='not_installed'},
    @{Changes=@{TaskPresent=$false;LegacyTaskPresent=$true}; Expected='legacy_installation'},
    @{Changes=@{FilesComplete=$false}; Expected='partial_installation'},
    @{Changes=@{ActionMatches=$false}; Expected='partial_installation'},
    @{Changes=@{StartupEnabled=$false}; Expected='partial_installation'},
    @{Changes=@{ConfigValid=$false}; Expected='invalid_configuration'},
    @{Changes=@{TaskState='Disabled'}; Expected='disabled'},
    @{Changes=@{TaskState='Running';LastTaskResult=0}; Expected='running'},
    @{Changes=@{TaskState='Queued'}; Expected='running'},
    @{Changes=@{HasRun=$false}; Expected='not_tested'},
    @{Changes=@{LastTaskResult=1}; Expected='failed'},
    @{Changes=@{LogMatchesRun=$false}; Expected='unverified'},
    @{Changes=@{LogOutcome='error'}; Expected='unverified'}
)) {
    $fixture=New-DiagnosticFixture
    foreach($key in $case.Changes.Keys){$fixture.$key=$case.Changes[$key]}
    $diagnosis=Get-CompactDiagnosis $fixture
    Assert ($diagnosis.status -eq $case.Expected) "Diagnostic expected $($case.Expected), got $($diagnosis.status)"
    Assert (![string]::IsNullOrWhiteSpace($diagnosis.nextAction.code)) 'Missing recommended action.'
}
$runTime=[datetime]::Parse('2026-01-01T10:00:00Z').ToUniversalTime()
$lines=@('2026-01-01T12:00:01+02:00 Starting','2026-01-01T12:00:09+02:00 SUCCESS: summary')
$evidence=Get-CompactRunEvidence $lines $runTime
Assert ($evidence.matchesRun -and $evidence.outcome -eq 'success') 'Timezone-aware fresh log did not match.'
$evidence=Get-CompactRunEvidence $lines $runTime.AddMinutes(1)
Assert (!$evidence.matchesRun) 'Stale log incorrectly matched a newer task run.'
$evidence=Get-CompactRunEvidence @($lines[0]) $runTime
Assert (!$evidence.matchesRun -and $evidence.outcome -eq 'incomplete') 'Incomplete log was treated as successful.'
$evidence=Get-CompactRunEvidence @($lines[0],'2026-01-01T12:00:09+02:00 ERROR: foreground') $runTime
Assert ($evidence.matchesRun -and $evidence.outcome -eq 'error') 'Error log evidence was misclassified.'
$evidence=Get-CompactRunEvidence @() $runTime
Assert (!$evidence.matchesRun -and $evidence.outcome -eq 'missing') 'Missing log was misclassified.'
$temp = Join-Path ([IO.Path]::GetTempPath()) ([guid]::NewGuid().ToString() + '.json')
try {
    $cfg = Read-CompactConfig (Join-Path $root 'config.example.json')
    $area = [pscustomobject]@{Left=0;Top=0;Right=1920;Bottom=1080;Width=1920;Height=1080}
    $p = Get-CompactPlacement $cfg $area 352
    Assert ($p.X -eq 1552 -and $p.Y -eq 16) 'Default top-right placement failed.'
    $cfg.X = -5000; $cfg.Y = -5000
    $area = [pscustomobject]@{Left=-1920;Top=-1080;Right=0;Bottom=0;Width=1920;Height=1080}
    $p = Get-CompactPlacement $cfg $area 352
    Assert ($p.X -eq -1920 -and $p.Y -eq -1080) 'Negative monitor coordinates were not clamped.'
    $cfg.X = 5000; $cfg.Y = 5000; $cfg.Height=4000
    $p = Get-CompactPlacement $cfg $area 352
    Assert ($p.X -eq -352 -and $p.Y -eq -1080 -and $p.Height -eq 1080) 'Offscreen position / oversized height failed.'
    foreach ($bad in @('{"X":1}', '{"X":"1","Y":2}', '{"Height":1}', '{"Height":null}', '{"AlwaysOnTop":"true"}', '{"X":1.2,"Y":2}', '{"Height":100001}')) {
        Set-Content -LiteralPath $temp -Value $bad
        $failed=$false
        try { $null=Read-CompactConfig $temp } catch { $failed=$true }
        Assert $failed "Accepted invalid configuration: $bad"
    }
    Set-Content -LiteralPath $temp -Value '{"X":-100,"Y":-200,"Height":640,"AlwaysOnTop":false}'
    $cfg=Read-CompactConfig $temp
    Assert ($cfg.X -eq -100 -and !$cfg.AlwaysOnTop) 'Valid configuration failed.'
    Write-Output 'PASS: PowerShell syntax, native interop compilation, config validation, placement, 20 diagnostic scenarios, and run-log freshness.'
} finally { if(Test-Path -LiteralPath $temp){Remove-Item -LiteralPath $temp} }
