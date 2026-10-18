# Compact Task Manager

Open Windows 11 Task Manager automatically in **dark Performance Summary view** after signing in. CPU, memory, disks, network, and GPU graphs stay in a small, always-on-top window.

No downloads beyond this project, no telemetry, no resident helper. A Windows scheduled task opens Task Manager, locates the CPU sidebar through accessibility, double-clicks it, positions the compact window, and exits.

## Requirements

- Windows 11 22H2 or newer, x64, with the modern Task Manager.
- Windows PowerShell 5.1 (included with Windows).
- An administrator account; install from an elevated PowerShell window **as the same user who will use the widget**.
- An unlocked interactive desktop. The helper briefly takes focus and moves the pointer, then restores its previous position.

The original workflow was tested on Windows 11 build 26200. Other Windows builds, languages, ARM64, and mixed-DPI layouts have not been verified. This is an experimental v0.1 release; Task Manager's UI and settings format are not stable public APIs.

## Install

Download and extract the repository, or clone it:

```powershell
git clone https://github.com/omoladeodetara/compact-task-manager.git
cd compact-task-manager
```

Review the scripts, then open **64-bit Windows PowerShell as administrator** in that folder:

```powershell
.\Install.ps1 -StartNow
```

If Windows marks downloaded scripts as blocked, review them and use the file's Properties > Unblock. This project does not disable execution policies or change UAC settings. Organization-managed execution policies still apply.

The installer copies executable scripts into an administrator-protected subdirectory of Program Files and creates a per-user task named `Compact Task Manager (<your SID>)`. It runs 15 seconds after sign-in. `-StartNow` also tests it immediately; omit the switch to wait until your next sign-in.

The helper gracefully closes an existing Task Manager instance before reopening it, so dark mode and the Performance start page are applied consistently. It does not stop any applications listed inside Task Manager.

## Position and size

Edit `%USERPROFILE%\CompactTaskManager\config.json`:

```json
{
  "X": null,
  "Y": null,
  "Height": 540,
  "AlwaysOnTop": true
}
```

- Leave X and Y null for the primary monitor's upper-right corner.
- Set both to integer screen coordinates (physical pixels) for a preferred location. Negative coordinates are supported.
- Height accepts 200–4000 pixels. Increase it if your PC has more devices than fit in the window.
- The window is clamped to the nearest available screen's working area if the preferred screen is missing.
- Set AlwaysOnTop to false to let other windows cover it.

To apply changes, run the task from Task Scheduler, or use:

```powershell
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
Start-ScheduledTask -TaskName "Compact Task Manager ($sid)"
```

## Uninstall

From an elevated 64-bit Windows PowerShell window, run `Uninstall.ps1` in this checkout, or the installed copy:

```powershell
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
& "$env:ProgramFiles\CompactTaskManager\$sid\Uninstall.ps1"
```

This removes the scheduled task and its known script files. It leaves your configuration, logs, and Task Manager preferences in place. The helper saves the original settings as `%USERPROFILE%\CompactTaskManager\settings-before.json` when available. Restore that backup manually only with Task Manager closed, if desired.

## Why a startup shortcut is not enough

On the tested Windows build, Task Manager remembers its start page but does not reopen in Performance Summary view. Task Manager also elevates itself, preventing ordinary automation from interacting with it. The scheduled task runs at the required privilege level in the user's interactive session.

Two implementation traps informed this project:

1. A 32-bit launcher may redirect `System32` to `SysWOW64` and open the older Task Manager. The helper explicitly uses native Windows PowerShell.
2. Packaged applications can virtualize AppData paths. A file visible to an app may not exist at that path for Task Scheduler. Installed code lives in Program Files; runtime configuration and logs live directly beneath the user profile.

The helper finds controls by automation ID, verifies the click target's process, and checks that the navigation UI disappeared while the CPU sidebar remains. It fails rather than intentionally clicking a different application. Do not interact with the pointer while the startup sequence is running.

## Troubleshooting and limits

- Read `%USERPROFILE%\CompactTaskManager\last-run.log` and the task's Last Run Result; `0` indicates success.
- If foreground activation fails, unlock the desktop and run the task again.
- If it opens in full view after a Windows update, the control identifiers may have changed. File an issue with your Windows build and the error text; redact personal paths.
- Dark mode and the Performance start page are written to Task Manager's settings JSON before launch. A Windows update may change that format.
- Turning a monitor off/on or waking from sleep is not a separate trigger. This release runs at sign-in or on manual task invocation.
- This is an independent project, not a Microsoft product.

## Development

```powershell
.\tests\Test.ps1
```

Tests cover PowerShell syntax, config validation, and placement on screens with negative coordinates or insufficient room. GitHub Actions runs these checks on Windows. CI does **not** validate desktop clicks or install elevated tasks; use the [manual test checklist](CONTRIBUTING.md) for those.

No screenshots, UI dumps, user settings, or logs are committed. The distributed helper does not capture screenshots or send network requests.

## License

[MIT](LICENSE).
