#Requires -Version 5.1
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot
foreach ($file in (Get-ChildItem -LiteralPath $root -Filter '*.ps1' -Recurse)) {
    $tokens = $null; $errors = $null
    $null = [Management.Automation.Language.Parser]::ParseFile($file.FullName, [ref]$tokens, [ref]$errors)
    if ($errors) { throw ($errors | Out-String) }
}
. (Join-Path $root 'src\Common.ps1')
$source = Get-Content -LiteralPath (Join-Path $root 'src\Start-CompactTaskManager.ps1') -Raw
$nativeCode = [regex]::Match($source, '(?s)Add-Type @"\r?\n(.*?)\r?\n"@').Groups[1].Value
if (!$nativeCode) { throw 'Native interop source was not found.' }
Add-Type -TypeDefinition $nativeCode
function Assert($Value, $Message) { if (!$Value) { throw $Message } }
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
    Write-Output 'PASS: PowerShell syntax, native interop compilation, config validation, default placement, multi-monitor bounds.'
} finally { if(Test-Path -LiteralPath $temp){Remove-Item -LiteralPath $temp} }
