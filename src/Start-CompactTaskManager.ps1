#Requires -Version 5.1
[CmdletBinding()]
param([switch]$RestartTaskManager)
# Use native Windows PowerShell. Do not run the legacy 32-bit Task Manager.
if (![Environment]::Is64BitProcess) {
 $nativeArgs=@('-NoProfile','-NonInteractive','-File',$PSCommandPath)
 if($RestartTaskManager){$nativeArgs+='-RestartTaskManager'}
 & "$env:WINDIR\Sysnative\WindowsPowerShell\v1.0\powershell.exe" @nativeArgs
 exit $LASTEXITCODE
}
$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
$principal=New-Object Security.Principal.WindowsPrincipal($identity)
if(!$principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
 throw 'Run this helper elevated, or use the installed scheduled task.'
}
$ErrorActionPreference = 'Stop'
$base = Join-Path $env:USERPROFILE 'CompactTaskManager'
New-Item -ItemType Directory -Path $base -Force | Out-Null
. (Join-Path $PSScriptRoot 'Common.ps1')
$log = Join-Path $base 'last-run.log'
"$(Get-Date -Format o) Starting" | Set-Content $log
function Log($s) { "$(Get-Date -Format o) $s" | Add-Content $log }
try {
 $cfg = Read-CompactConfig (Join-Path $base 'config.json')
 $sessionId = (Get-Process -Id $PID).SessionId
 Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes,System.Windows.Forms,System.Drawing
 Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class TMWin {
 [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left,Top,Right,Bottom; }
 [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X,Y; public POINT(int x,int y){X=x;Y=y;} }
 [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
 [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h,out RECT r);
 [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h,out uint pid);
 [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h,IntPtr after,int x,int y,int w,int hgt,uint f);
 [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h,int cmd);
 [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
 [DllImport("user32.dll")] public static extern bool SetCursorPos(int x,int y);
 [DllImport("user32.dll")] public static extern bool GetCursorPos(out POINT p);
 [DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(POINT p);
 [DllImport("user32.dll")] public static extern void mouse_event(uint flags,uint x,uint y,uint data,UIntPtr extra);
}
"@
 [void][TMWin]::SetProcessDPIAware()
 $existing = @(Get-Process Taskmgr -ErrorAction SilentlyContinue | Where-Object {$_.SessionId -eq $sessionId})
 if ($RestartTaskManager) {
  foreach($p in $existing) { [void]$p.CloseMainWindow(); if(!$p.WaitForExit(5000)){throw 'Task Manager did not close normally'} }
  $existing=@()
 }
 if (!$existing.Count) {
  $settingsPath=Join-Path $env:LOCALAPPDATA 'Microsoft\Windows\TaskManager\settings.json'
  if(Test-Path $settingsPath){$s=Get-Content $settingsPath -Raw | ConvertFrom-Json}else{New-Item -ItemType Directory -Path (Split-Path $settingsPath) -Force | Out-Null; $s=[pscustomobject]@{}}
  $s | Add-Member DefaultStartPage 1 -Force
  $s | Add-Member AppTheme 2 -Force
  $s | Add-Member AlwaysOnTop $cfg.AlwaysOnTop -Force
  if(!(Test-Path (Join-Path $base 'settings-before.json')) -and (Test-Path $settingsPath)){Copy-Item -LiteralPath $settingsPath -Destination (Join-Path $base 'settings-before.json')}
  $s | ConvertTo-Json -Depth 100 -Compress | Set-Content $settingsPath -Encoding UTF8
  Start-Process "$env:WINDIR\System32\Taskmgr.exe"
 }
 $deadline=(Get-Date).AddSeconds(30)
 do { Start-Sleep -Milliseconds 500; $p=Get-Process Taskmgr -ErrorAction SilentlyContinue | Where-Object {$_.SessionId -eq $sessionId -and $_.MainWindowHandle -ne 0} | Select-Object -First 1 } until ($p -or (Get-Date) -gt $deadline)
 if(!$p){throw 'Task Manager window did not appear'}
 if($p.Path -ne "$env:WINDIR\System32\Taskmgr.exe"){throw "Unexpected Task Manager executable: $($p.Path)"}
 $hwnd=$p.MainWindowHandle
 [void][TMWin]::ShowWindow($hwnd,9)
 function Elements { $script:root=[Windows.Automation.AutomationElement]::FromHandle($hwnd); $script:all=$root.FindAll([Windows.Automation.TreeScope]::Descendants,[Windows.Automation.Condition]::TrueCondition) }

 Elements
 $perf=$all | Where-Object {$_.Current.AutomationId -eq 'PerformanceItem' -and $_.Current.ControlType -ne [Windows.Automation.ControlType]::Text} | Select-Object -First 1
 if($perf) {
  $pattern=$null
  if($perf.TryGetCurrentPattern([Windows.Automation.SelectionItemPattern]::Pattern,[ref]$pattern)){$pattern.Select()}
  elseif($perf.TryGetCurrentPattern([Windows.Automation.InvokePattern]::Pattern,[ref]$pattern)){$pattern.Invoke()}
  Start-Sleep -Milliseconds 700; Elements
 }
 $r=New-Object TMWin+RECT; [void][TMWin]::GetWindowRect($hwnd,[ref]$r)
 if(@($all | Where-Object {$_.Current.AutomationId -eq 'NavigationMenu'}).Count -gt 0) {
  $cpu=$all | Where-Object {$_.Current.AutomationId -eq 'dashSidebarCpuButton'} | Select-Object -First 1
  if(!$cpu){throw 'CPU sidebar control not found'}
  [void][TMWin]::SetForegroundWindow($hwnd)
  Start-Sleep -Milliseconds 400
  Elements
  $cpu=$all | Where-Object {$_.Current.AutomationId -eq 'dashSidebarCpuButton'} | Select-Object -First 1
  $b=$cpu.Current.BoundingRectangle
  $point=New-Object TMWin+POINT([int]($b.Left+$b.Width/2),[int]($b.Top+$b.Height/2))
  $target=[TMWin]::WindowFromPoint($point)
  [uint32]$targetPid=0; [void][TMWin]::GetWindowThreadProcessId($target,[ref]$targetPid)
  if($targetPid -ne $p.Id){throw 'Task Manager is not foreground; refusing to click another app'}
  $previous=New-Object TMWin+POINT; [void][TMWin]::GetCursorPos([ref]$previous)
  try {
   if(![TMWin]::SetCursorPos($point.X,$point.Y)){throw 'Unable to move the pointer'}
   $target=[TMWin]::WindowFromPoint($point)
   [void][TMWin]::GetWindowThreadProcessId($target,[ref]$targetPid)
   if($targetPid -ne $p.Id){throw 'Click target changed; refusing input'}
   [TMWin]::mouse_event(2,0,0,0,[UIntPtr]::Zero); [TMWin]::mouse_event(4,0,0,0,[UIntPtr]::Zero)
   Start-Sleep -Milliseconds 80
   [TMWin]::mouse_event(2,0,0,0,[UIntPtr]::Zero); [TMWin]::mouse_event(4,0,0,0,[UIntPtr]::Zero)
  } finally { [void][TMWin]::SetCursorPos($previous.X,$previous.Y) }
  Start-Sleep -Milliseconds 800
 }
 [void][TMWin]::GetWindowRect($hwnd,[ref]$r)
 Elements
 if(@($all | Where-Object {$_.Current.AutomationId -eq 'NavigationMenu'}).Count -gt 0 -or !@($all | Where-Object {$_.Current.AutomationId -eq 'dashSidebarCpuButton'}).Count){throw 'Summary view did not activate'}
 if($null -eq $cfg.X){$area=[Windows.Forms.Screen]::PrimaryScreen.WorkingArea}
 else {$area=([Windows.Forms.Screen]::FromPoint((New-Object Drawing.Point($cfg.X,$cfg.Y)))).WorkingArea}
 $placement=Get-CompactPlacement $cfg $area ($r.Right-$r.Left)
 $width=$placement.Width; $height=$placement.Height; $x=$placement.X; $y=$placement.Y
 $zOrder=[IntPtr](-2); if($cfg.AlwaysOnTop){$zOrder=[IntPtr](-1)}
 if(![TMWin]::SetWindowPos($hwnd,$zOrder,$x,$y,$width,$height,0x10)){throw 'Unable to place Task Manager'}
 Start-Sleep -Milliseconds 500
 Log "SUCCESS: native Task Manager Summary view at $x,$y size ${width}x$height; dark theme requested."
 exit 0
} catch { Log "ERROR: $_"; exit 1 }
