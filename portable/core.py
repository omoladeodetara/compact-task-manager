"""Platform-independent configuration, status decisions, and startup serialization."""
import json
import math
import os
from pathlib import Path
import plistlib
import time

LABEL = "org.compacttaskmanager.widget"
DEFAULT_CONFIG = {"width": 330, "x": None, "y": None, "alwaysOnTop": True, "intervalSeconds": 1}


def paths(system, home=None, env=None):
    home = Path(home or Path.home())
    env = os.environ if env is None else env
    if system == "Darwin":
        root = home / "Library/Application Support/CompactTaskManager"
        startup = home / "Library/LaunchAgents" / (LABEL + ".plist")
    else:
        data = Path(env.get("XDG_DATA_HOME") or home / ".local/share")
        config = Path(env.get("XDG_CONFIG_HOME") or home / ".config")
        if not data.is_absolute() or not config.is_absolute():
            raise ValueError("XDG directories must be absolute")
        root = data / "compact-task-manager"
        startup = config / "autostart/compact-task-manager.desktop"
    return {"root": root, "startup": startup, "python": root / "venv/bin/python",
            "app": root / "app/ctm.py", "config": root / "config.json", "state": root / "state.json"}


def config_from(data):
    if not isinstance(data, dict):
        raise ValueError("configuration must be an object")
    result = dict(DEFAULT_CONFIG, **data)
    if type(result["width"]) is not int or not 260 <= result["width"] <= 800:
        raise ValueError("width must be an integer between 260 and 800")
    if (result["x"] is None) != (result["y"] is None):
        raise ValueError("set both x and y or leave both null")
    for key in ("x", "y"):
        if result[key] is not None and (type(result[key]) is not int or not -100000 <= result[key] <= 100000):
            raise ValueError("coordinates must be bounded integers")
    interval = result["intervalSeconds"]
    if type(interval) not in (int, float) or not math.isfinite(interval) or not 0.5 <= interval <= 10:
        raise ValueError("intervalSeconds must be between 0.5 and 10")
    if type(result["alwaysOnTop"]) is not bool:
        raise ValueError("alwaysOnTop must be boolean")
    return result


def read_config(path):
    return config_from(json.loads(path.read_text()) if path.exists() else {})


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def desktop_quote(value):
    # Desktop Entry quoting is not shell quoting. Escape field codes and the
    # four reserved characters inside double quotes, then escape backslashes
    # for the desktop-file string layer. Never pass this string to a shell.
    value = str(value)
    if any(c in value for c in "\r\n\0"):
        raise ValueError("control characters are not allowed in startup paths")
    value = value.replace("%", "%%")
    for c in ("\\", '"', "`", "$"):
        value = value.replace(c, "\\" + c)
    return '"' + value.replace("\\", "\\\\") + '"'


def startup_bytes(system, p):
    args = [str(p["python"]), str(p["app"]), "run"]
    if system == "Darwin":
        return plistlib.dumps({"Label": LABEL, "ProgramArguments": args,
                              "RunAtLoad": True, "LimitLoadToSessionType": "Aqua",
                              "StandardErrorPath": str(p["root"] / "launch-error.log")})
    return ("[Desktop Entry]\nType=Application\nName=Compact Task Manager\n"
            "Comment=Dark desktop performance graphs\nTerminal=false\n"
            "X-CompactTaskManager=true\nExec=" + " ".join(desktop_quote(a) for a in args) + "\n").encode()


def startup_owned(system, content):
    try:
        if system == "Darwin":
            value = plistlib.loads(content)
            return isinstance(value, dict) and value.get("Label") == LABEL
        return "X-CompactTaskManager=true" in content.decode().splitlines()
    except (ValueError, TypeError, UnicodeError, plistlib.InvalidFileException):
        return False


def runtime_report(state, alive, now=None):
    now = time.time() if now is None else now
    updated = state.get("updatedAt", 0)
    fresh = (isinstance(updated, (int, float)) and 0 <= now - updated <= 15)
    return {"state": state.get("status", "never_started"), "heartbeatFresh": fresh,
            "processMatches": alive, "healthy": alive and fresh and state.get("status") == "running"}


def decision(o):
    """Return stable status/action codes; never turn unknown probes into success."""
    cases = [
        (not o["supported"], "unsupported", "use_supported_platform", "Use macOS or a Linux graphical desktop, or the Windows backend."),
        (bool(o["errors"]), "unknown", "retry_failed_checks", "Review the check error codes before making changes."),
        (not o["tkinter"], "missing_dependency", "install_tkinter", "Install Python with Tk support, then run diagnose again."),
        (not o["desktop"], "headless", "use_desktop_session", "Run in a logged-in desktop session. Linux Tk requires DISPLAY (X11 or XWayland)."),
        (not o["installed"], "not_installed", "install", "Run python3 ctm.py install as your normal user; it downloads psutil into a private virtual environment."),
        (not o["dependencies"] or not o["startupMatches"], "partial_installation", "repair_installation", "Review the startup entry and rerun python3 ctm.py install."),
        (not o["configValid"], "invalid_configuration", "fix_configuration", "Correct the portable config.json and diagnose again."),
        (o["runtime"]["healthy"], "healthy", "visually_verify_widget", "The widget process and fresh heartbeat agree. Visually verify graphs and placement; login startup is not proven."),
        (o["runtime"]["state"] == "error", "failed", "inspect_run_error", "Inspect the local state.json errorCode, resolve dependencies or desktop access, and run start."),
        (True, "not_running", "start_widget", "Run python3 ctm.py start in your desktop session, then diagnose again."),
    ]
    for matches, status, code, message in cases:
        if matches:
            return status, {"code": code, "message": message, "requiresElevation": False}
