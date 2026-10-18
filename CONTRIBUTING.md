# Contributing

Small pull requests are welcome. Describe the Windows build and scaling used for UI changes. Keep configuration declarative, do not add remote downloads or telemetry, and never commit actual user settings, logs, or UI dumps. Documentation screenshots must be explicitly reviewed and limited to the widget, without personal desktop content.

Run `tests/Test.ps1` in Windows PowerShell 5.1. For portable changes, install `requirements-portable.txt` in a development environment and run `python3 -m unittest discover -s tests -p 'test_portable.py' -v`. The Linux Xvfb smoke test is `xvfb-run -a python3 -m tests.smoke_portable`.

## Manual test checklist

Use a Windows 11 x64 test account with administrator privileges:

1. Install with `Install.ps1 -StartNow`; confirm the task belongs to that user and executable scripts are protected in Program Files.
2. Confirm dark Summary view displays CPU and memory, with no navigation sidebar.
3. Run the task again with Task Manager already open. Confirm it closes gracefully and returns to Summary view.
4. Test null coordinates, a negative-coordinate monitor, a missing preferred monitor, and different scaling factors.
5. Try a locked desktop and a foreground-stealing app. The helper must fail without intentionally clicking another app.
6. Sign out and back in. Confirm the task runs without an elevation prompt.
7. Uninstall; confirm only this project's task and known installed files were removed.

The original predecessor's scheduled launch was tested twice on Windows 11 build 26200. The generalized installer and multi-machine behavior need additional community testing. Do not describe syntax/config tests as end-to-end desktop verification.

## macOS / Linux manual checks

1. Use a normal user in an actual graphical session. Run `python3 ctm.py diagnose` before installing; verify no files or startup entries were created by diagnosis.
2. Install with `--start-now`. Check the per-user LaunchAgent or XDG entry, the dark window, real changing readings, and the diagnostic heartbeat.
3. Close the widget, confirm `not_running`, then start it twice and confirm only one window appears.
4. Edit config, update with `install --start-now`, and confirm preferences survive. Test paths containing spaces, quotes, dollar signs, and percent characters.
5. Sign out and back in. Confirm launch without root/admin privileges, respecting macOS Login Items or desktop startup policy.
6. Test X11 and XWayland separately, compositor-specific topmost behavior, scaling, and primary-screen positioning. Plain Wayland without XWayland should report the missing display.
7. Uninstall; verify this project's startup entry is gone and only its verified widget process stops. Configuration and cached files remain intentionally.

GPU tests must distinguish unavailable sensors from zero load. Linux NVIDIA support is optional; Apple Silicon, AMD, and Intel GPU monitoring are not implemented. Do not add privileged sensor tools automatically or fabricate portable screenshots from the Windows UI.
