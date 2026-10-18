# Contributing

Small pull requests are welcome. Describe the Windows build and scaling used for UI changes. Keep configuration declarative, do not add remote downloads or telemetry, and never commit actual user settings, logs, or UI dumps. Documentation screenshots must be explicitly reviewed and limited to the widget, without personal desktop content.

Run `tests/Test.ps1` in Windows PowerShell 5.1. Automated tests do not cover interactive desktop behavior.

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
