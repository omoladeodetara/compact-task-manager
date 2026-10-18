# Changelog

## Unreleased

- Experimental macOS/Linux dark monitoring widget with user-only LaunchAgent/XDG startup, a private Python environment, and no telemetry.
- Shared `ctm.py` lifecycle/JSON diagnostics entry point; Windows delegates to the existing native backend.
- Real CPU/memory/disk/network samples; optional Linux NVIDIA GPU readings with explicit unavailable states elsewhere.
- Portable tests on three OS runners and a real Linux Tk lifecycle test under Xvfb.
- Read-only `Diagnose.ps1` command with versioned JSON, compatibility and installation checks, fresh-run evidence, and recommended next actions.
- Diagnostic scenario and stale-log tests.
- Reviewed screenshots of the dark compact widget in the README.

## 0.1.0

- Initial experimental public release, extracted from a working personal automation.
- Native Task Manager launch, dark Performance Summary view, and configurable screen placement.
- Per-user scheduled startup with administrator-protected installed scripts.
- Uninstaller, configuration validation, placement tests, and Windows CI.
