# Compact Task Manager

Compact dark performance graphs that open after signing in, with **AI-friendly setup and JSON diagnostics** on Windows, macOS, and Linux.

- **Windows:** opens native Task Manager in Performance Summary view. The existing PowerShell backend is unchanged.
- **macOS / Linux:** runs a small Tk monitoring app with CPU, memory, aggregate disk I/O, and network graphs. Linux optionally reads NVIDIA GPU utilization through an existing `nvidia-smi`; other GPUs are explicitly shown as unavailable. It does not automate Activity Monitor or a Linux system-monitor app.
- No telemetry. The portable installer downloads `psutil` into a private virtual environment; the portable widget remains running to collect metrics. The Windows helper exits after opening Task Manager.

The portable backend is experimental. CI tests its logic and metrics on macOS/Linux/Windows, plus a real Linux GUI lifecycle under Xvfb. macOS visual appearance, actual login startup, and every Linux compositor still require manual validation.

## Quick start by platform

Clone or download this repository first. Inspect the scripts before installing.

| Platform | Diagnose (read-only) | Install | Start / remove |
| --- | --- | --- | --- |
| Windows 11 x64 | `.\Diagnose.ps1` | `.\Install.ps1 -StartNow` from elevated 64-bit Windows PowerShell | Run the scheduled task / `.\Uninstall.ps1` |
| macOS | `python3 ctm.py diagnose` | `python3 ctm.py install --start-now` as your normal user | `python3 ctm.py start` / `python3 ctm.py uninstall` |
| Linux desktop | `python3 ctm.py diagnose` | `python3 ctm.py install --start-now` as your normal user | `python3 ctm.py start` / `python3 ctm.py uninstall` |

With Python available on Windows, `python ctm.py diagnose`, `install`, and `uninstall` delegate to the existing PowerShell scripts. They do not bypass Windows elevation. Python is not required for the native Windows commands.

### macOS and Linux requirements

- Python **3.10+**, Tkinter, and `venv` support. Diagnostics work before installing `psutil`.
- macOS: use a Python distribution with Aqua Tk support, such as the [python.org installer](https://www.python.org/download/mac/tcltk/). Run from your logged-in graphical session, not an SSH-only session.
- Linux: use a graphical desktop implementing [XDG autostart](https://specifications.freedesktop.org/autostart/latest/), with X11 or XWayland (`DISPLAY`). Wayland-only sessions without XWayland are not supported by this Tk backend. Your distribution may package Tk/venv separately (for example `python3-tk` and `python3-venv` on Debian/Ubuntu); the installer does not run a system package manager for you.
- Run installation **without sudo**. The portable backend refuses root installation and needs no Accessibility, Screen Recording, or administrator permissions.
- `install` creates a private virtual environment, installs `psutil>=7.2,<8`, copies only project source files, preserves existing configuration, and writes one per-user startup entry. Downloads occur only during an explicit install/update.
- On macOS it writes a [LaunchAgent](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html) limited to Aqua sessions. On Linux it writes an XDG `.desktop` entry. Both take effect at the next graphical login. `--start-now` separately requests a current-session launch; verify it with diagnostics rather than treating process launch as success.

Run these again to update an existing portable installation. Installation is repeatable, preserves preferences, and stops the old widget before replacing its code; use `--start-now` to reopen it immediately. Uninstall disables this project's startup entry and stops only a process whose PID, creation time, and application command match. It retains configuration, local state, and cached runtime files; it does not remove Python or system packages.

### Portable configuration and diagnostics

Portable files live under:

- macOS: `~/Library/Application Support/CompactTaskManager/`.
- Linux: `${XDG_DATA_HOME:-~/.local/share}/compact-task-manager/`; startup uses `${XDG_CONFIG_HOME:-~/.config}/autostart/`.

Edit `config.json` there (the Windows configuration below uses a different schema):

```json
{"width": 330, "x": null, "y": null, "alwaysOnTop": true, "intervalSeconds": 1}
```

The widget saves its position when closed. Initial position is clamped to the primary screen; exact multi-monitor positioning and always-on-top behavior depend on the window manager. Disk/network graphs show total throughput and auto-scale; unavailable readings are not displayed as zero.

`python3 ctm.py diagnose` returns the same top-level contract as Windows: `schemaVersion`, `status`, `compatibility`, `installation`, `lastRun`, `errors`, `nextAction`, and `visualVerification`. Fields inside the platform-specific sections differ. Portable diagnostics also report `backend` and `capabilities`.

An agent should parse `status` and `nextAction.code`. Portable statuses include `unsupported`, `unknown`, `missing_dependency`, `headless`, `not_installed`, `partial_installation`, `invalid_configuration`, `healthy`, `failed`, and `not_running`. `healthy` requires a matching live process **and** a recent heartbeat written after actual samples were drawn. A stale PID file alone never counts as success. Diagnostics do not open a test window, download dependencies, enable startup, or inspect pixels. `desktopSessionHint` is only a hint, not proof of display access. `startupEntryMatches` verifies the file, not that macOS Login Items or your desktop policy will allow it at login.

For every backend, exit code 0 means the checks completed, not necessarily that the widget is healthy. Exit code 1 indicates a check/command failure. Do not claim login behavior or visual appearance was verified by diagnostics alone.

## Screenshots

Actual Windows 11 Task Manager in dark Summary view. Only the widget's client area is captured; no desktop or other applications are included. Hardware and readings are illustrative and will differ on your PC. These images show the working original helper, not a claim of installer verification on every supported configuration.

![Dark compact Task Manager showing CPU, memory, disks, Ethernet, and GPU graphs](docs/images/summary-dark.png)

<details>
<summary>CPU and memory close-up</summary>

![CPU and memory graphs in dark Summary view](docs/images/cpu-memory-detail.png)

</details>

## Windows diagnostic command

From this checkout, run:

```powershell
.\Diagnose.ps1
```

The command is **read-only**: it does not install, elevate, change settings, start tasks, or move windows. It prints one JSON object with `schemaVersion`, `status`, `compatibility`, `installation`, `lastRun`, `errors`, and `nextAction`. It normally runs without administrator privileges. Use 64-bit Windows PowerShell 5.1 for the full supported check; other environments are reported rather than installed into.

An agent can consume the result directly:

```powershell
$report = .\Diagnose.ps1 | ConvertFrom-Json
$report.status
$report.nextAction.code
$report.nextAction.message
```

Key outcomes:

| Status | What to do next |
| --- | --- |
| `unsupported` / `wrong_shell` | Use the supported Windows platform / native Windows PowerShell. |
| `not_installed` / `partial_installation` | Review and install or repair with human-approved administrator privileges. |
| `legacy_installation` | Review the original personal helper before adding another startup task. |
| `invalid_configuration` / `disabled` | Fix the config or enable the task, as requested by the user. |
| `running` / `not_tested` | Wait for completion, or run the task once, then diagnose again. |
| `failed` / `unverified` | Inspect the local log or obtain a matching fresh run. |
| `healthy` | The latest completed task and matching log agree on success. Visually verify the widget. |
| `unknown` | One or more checks failed; inspect the error codes before drawing conclusions. |

`nextAction` includes a stable `code`, a human-readable `message`, and `requiresElevation`. These are recommendations, not authorization for an agent to act. `visualVerification` is always `not_performed`: the command does not inspect pixels or claim to have tested sign-in. A previous successful run does not prove the widget is currently visible.

Exit code `0` means the diagnostic checks completed, **not** that the installation is healthy. Exit code `1` means a check failed. Parse `status` for application health. Raw logs, account names, SIDs, and personal paths are not emitted; OS/architecture and task result information are included.

New installations also include the command in the installed directory:

```powershell
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
& "$env:ProgramFiles\CompactTaskManager\$sid\Diagnose.ps1"
```

## Can my AI agent set this up?

**Yes, if it can run local commands on your computer.** Preferences use JSON and every backend offers read-only structured diagnostics. Windows uses PowerShell and Task Scheduler; macOS/Linux use Python and per-user startup entries. No particular AI provider or model is required.

This is **scriptable, not universally unattended**. Windows requires human-approved elevation; macOS/Linux run as the normal user but may need Python/Tk installed first. The widget needs a graphical desktop. A cloud-only agent or a headless runner cannot verify the user's desktop or next login.

You can give your agent this prompt:

> Set up Compact Task Manager from https://github.com/omoladeodetara/compact-task-manager on this computer. Read the README and choose the backend for my operating system. Run its diagnostic command first and inspect the JSON next action. Use the default position unless I specify another. Install only for my account; on Windows let me approve elevation, and on macOS/Linux do not use sudo. Do not bypass security controls or silently install system packages. Start the widget, verify a fresh diagnostic result, and visually inspect it if you can. Tell me which metrics are supported, what you verified, what remains untested, and how to uninstall it.

### Windows agent setup checklist

1. **Check the environment.** Run `Diagnose.ps1` and read its JSON report, then use the compatibility table below. Installation requires native 64-bit Windows PowerShell 5.1, not merely any shell named PowerShell. Elevate as the intended Windows user, not a different administrator account.
2. **Inspect before running.** Read `Install.ps1`, `src/Start-CompactTaskManager.ps1`, `src/Common.ps1`, and `Uninstall.ps1`. Run `tests/Test.ps1`; these checks do not install anything or exercise the desktop.
3. **Check for an existing setup.** Inspect this user's `Compact Task Manager (<SID>)` task and configuration. Reinstallation updates the installed scripts and task, but preserves an existing `config.json`. Do not create additional startup shortcuts or unrelated tasks.
4. **Install with user authorization.** Follow the installation section. `-StartNow` starts the task asynchronously; installer success alone does not prove the widget opened. The task closes and reopens Task Manager to apply its settings. Never interact with UAC prompts on the user's behalf, disable UAC, or weaken execution policies to finish setup.
5. **Verify a fresh run.** Wait for the task to finish, then inspect its Last Run Time, Last Run Result, and the timestamped log. Confirm the results belong to the run you just requested. If desktop inspection is available, verify dark Summary view and placement as well. Otherwise explicitly report that visual appearance was not verified.
6. **Report the result.** Give the user the task name, config location, observed result, and uninstall command. Keep personal paths, logs, settings backups, and screenshots out of public commits and issue reports.

These are read-only verification commands, run after the task finishes:

```powershell
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$task = Get-ScheduledTask -TaskName "Compact Task Manager ($sid)"
$info = $task | Get-ScheduledTaskInfo
[pscustomobject]@{
    TaskName = $task.TaskName
    State = [string]$task.State
    LastRunTime = $info.LastRunTime
    LastTaskResult = $info.LastTaskResult
} | ConvertTo-Json
Get-Content -LiteralPath "$env:USERPROFILE\CompactTaskManager\last-run.log"
```

A completed fresh run with result `0` and a matching `SUCCESS` log means the helper's checks passed. This does not replace visual verification or prove the next sign-in has been tested. Never describe a queued or still-running task as a successful installation test.

## Does it work across operating systems?

**Yes, through separate backends.** The native Task Manager automation remains Windows-specific. macOS and Linux use the new Python/Tk monitor with the shared setup/diagnostic command interface; they do not require Windows APIs or PowerShell.

| Platform | Status |
| --- | --- |
| Windows 11 22H2 or newer, x64 | Intended target. Original workflow tested on build 26200; generalized installer and other builds need further testing. |
| Windows 11 ARM64 | Not verified or supported by this release. |
| Windows 10 and older | Unsupported; the legacy Task Manager has different UI and theme behavior. |
| macOS with Python 3.10+ and Aqua Tk | Experimental portable widget; CI logic/metrics tests, manual desktop/login validation still needed. |
| Linux desktop with Python 3.10+, Tk, X11/XWayland | Experimental portable widget; CI logic/metrics and real Xvfb GUI lifecycle tests. Actual desktop/login validation still needed. |
| WSL, Windows Server, or headless environments | Unsupported deployment environments for this desktop helper. |

CPU/memory/disk/network monitoring is shared across the portable platforms. GPU parity is incomplete: this release supports optional Linux NVIDIA utilization but not Apple Silicon, AMD, or Intel GPU sensors. Missing GPU data is labeled unavailable, never fabricated.

## Windows requirements

- Windows 11 22H2 or newer, x64, with the modern Task Manager.
- Windows PowerShell 5.1 (included with Windows).
- An administrator account; install from an elevated PowerShell window **as the same user who will use the widget**.
- An unlocked interactive desktop. The helper briefly takes focus and moves the pointer, then restores its previous position.

The original workflow was tested on Windows 11 build 26200. Other Windows builds, languages, ARM64, and mixed-DPI layouts have not been verified. This is an experimental v0.1 release; Task Manager's UI and settings format are not stable public APIs.

## Windows installation

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

## Windows position and size

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

## Windows uninstall

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

Portable tests (use a development virtual environment):

```sh
python3 -m pip install -r requirements-portable.txt
python3 -m unittest discover -s tests -p 'test_portable.py' -v
# Linux, with Tk and Xvfb installed:
xvfb-run -a python3 -m tests.smoke_portable
```

Windows tests cover PowerShell syntax, config validation, diagnostics, and placement. Portable tests cover configuration, read-only diagnostics, process evidence, startup serialization, lifecycle behavior in temporary directories, and actual psutil metrics. Linux CI also opens and closes a real Tk window under Xvfb, requiring live graph draws and saved state. CI does **not** validate Windows desktop clicks, macOS visual appearance, or real user login startup; use the [manual test checklist](CONTRIBUTING.md) for those.

Only the reviewed documentation screenshots in `docs/images/` are committed. UI dumps, user settings, logs, and other captures remain excluded. The distributed helper and diagnostic command do not capture screenshots or send network requests.

## License

[MIT](LICENSE).
