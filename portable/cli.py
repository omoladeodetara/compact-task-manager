"""Explicit, per-user lifecycle commands. Never requests sudo or bypasses policy."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
import venv

from .core import (LABEL, DEFAULT_CONFIG, atomic_json, decision, paths, read_config,
                   runtime_report, startup_bytes, startup_owned)

REPO = Path(__file__).resolve().parent.parent


def emit(value):
    print(json.dumps(value, indent=2))


def process_matches(state, app, psutil):
    try:
        pid = state.get("pid")
        if type(pid) is not int or pid <= 1:
            return None
        proc = psutil.Process(pid)
        if abs(proc.create_time() - float(state["createTime"])) > 0.01:
            return None
        args = proc.cmdline()
        if str(app) not in args or "run" not in args:
            return None
        return proc if proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE else None
    except (KeyError, ValueError, TypeError, psutil.Error):
        return None


def _probe(p, stop=False):
    """Runs inside the installed interpreter, never imports a missing dependency."""
    import psutil
    state = json.loads(p["state"].read_text()) if p["state"].exists() else {}
    proc = process_matches(state, p["app"], psutil)
    if stop and proc:
        proc.terminate()
        proc.wait(timeout=5)
    return {"alive": bool(proc) and not stop, "state": state}


def probe_dependencies(python):
    code = ("import importlib.util,json; "
            "print(json.dumps({n:importlib.util.find_spec(n) is not None "
            "for n in ['tkinter','psutil']}))")
    return json.loads(subprocess.check_output([str(python), "-B", "-c", code], text=True, timeout=10, stderr=subprocess.DEVNULL))


def desktop_available(system, env=None):
    env = os.environ if env is None else env
    if system == "Linux":
        return bool(env.get("DISPLAY"))
    # SSH alone is not evidence of a usable Aqua login session.
    return system == "Darwin" and not env.get("SSH_CONNECTION")


def diagnose(system):
    supported = system in ("Darwin", "Linux") and sys.version_info >= (3, 10)
    p = paths(system)
    errors = []
    installed = p["app"].is_file() and p["python"].is_file()
    deps = {"tkinter": False, "psutil": False}
    state = {}; alive = False; config_valid = True; startup_matches = False
    try:
        deps = probe_dependencies(p["python"] if p["python"].is_file() else sys.executable)
    except (OSError, ValueError, subprocess.SubprocessError):
        errors.append("dependency_probe_failed")
    try:
        read_config(p["config"])
    except (OSError, ValueError, TypeError):
        config_valid = False
    try:
        startup_matches = p["startup"].is_file() and p["startup"].read_bytes() == startup_bytes(system, p)
        if p["state"].is_file():
            state = json.loads(p["state"].read_text())
        if not isinstance(state, dict):
            raise ValueError("invalid state")
        if installed and deps["psutil"]:
            probe = json.loads(subprocess.check_output(
                [str(p["python"]), "-B", str(p["app"]), "_probe"], text=True, timeout=10, stderr=subprocess.DEVNULL))
            alive = probe["alive"]
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        errors.append("runtime_probe_failed")
    runtime = runtime_report(state, alive)
    observation = {"supported": supported, "errors": errors, "tkinter": deps["tkinter"],
                   "desktop": desktop_available(system), "installed": installed,
                   "dependencies": all(deps.values()), "startupMatches": startup_matches,
                   "configValid": config_valid, "runtime": runtime}
    status, action = decision(observation)
    emit({"schemaVersion": 1, "backend": "portable-widget", "checkedAt": time.time(), "status": status,
          "compatibility": {"platform": system, "architecture": platform.machine(), "python": platform.python_version(),
                            "supported": supported, "desktopSessionHint": observation["desktop"],
                            "displayConnectionVerified": False, "dependencies": deps},
          "installation": {"filesPresent": installed, "startupEntryMatches": startup_matches,
                           "configurationValid": config_valid}, "lastRun": runtime,
          "capabilities": {"cpu": True, "memory": True, "diskIO": True, "networkIO": True,
                           "gpu": "optional_nvidia_smi" if system == "Linux" else "unavailable"},
          "visualVerification": "not_performed", "errors": errors, "nextAction": action})
    return 1 if errors else 0


def require_user(system):
    if system not in ("Darwin", "Linux") or sys.version_info < (3, 10):
        raise RuntimeError("unsupported_platform_or_python")
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        raise RuntimeError("use_normal_user_not_root")


def install(system, start_now=False):
    require_user(system)
    p = paths(system)
    if importlib.util.find_spec("tkinter") is None:
        raise RuntimeError("install_python_with_tkinter_first")
    if p["startup"].exists() and not startup_owned(system, p["startup"].read_bytes()):
        raise RuntimeError("startup_path_owned_by_another_application")
    read_config(p["config"])  # Validate before making changes.
    p["root"].mkdir(parents=True, exist_ok=True)
    # Protect against symlink redirection at the project-controlled locations.
    for target in (p["root"], p["root"] / "app", p["root"] / "venv", p["startup"]):
        if target.is_symlink():
            raise RuntimeError("refusing_symlink_install_target")
    if not p["python"].is_file():
        venv.EnvBuilder(with_pip=True).create(p["root"] / "venv")
    subprocess.run([str(p["python"]), "-m", "pip", "install", "--disable-pip-version-check",
                    "-r", str(REPO / "requirements-portable.txt")], check=True, stdout=sys.stderr, stderr=sys.stderr)
    if p["app"].is_file():
        subprocess.run([str(p["python"]), "-B", str(p["app"]), "_stop"],
                       check=True, timeout=10, stdout=subprocess.DEVNULL)
    app_root = p["app"].parent
    (app_root / "portable").mkdir(parents=True, exist_ok=True)
    sources = [REPO / "ctm.py", REPO / "requirements-portable.txt", *sorted((REPO / "portable").glob("*.py"))]
    for source in sources:
        target = app_root / source.relative_to(REPO)
        if source.resolve() != target.resolve():
            temporary = target.with_suffix(target.suffix + ".new")
            temporary.write_bytes(source.read_bytes())
            os.replace(temporary, target)
    if not p["config"].exists():
        atomic_json(p["config"], DEFAULT_CONFIG)
    p["startup"].parent.mkdir(parents=True, exist_ok=True)
    p["startup"].write_bytes(startup_bytes(system, p))
    if start_now:
        start(system, report=False)
    emit({"status": "installed", "startup": "next_desktop_login", "startRequested": start_now,
          "nextAction": "diagnose_after_start" if start_now else "run_start_or_sign_in"})
    return 0


def start(system, report=True):
    require_user(system)
    p = paths(system)
    if not p["python"].is_file() or not p["app"].is_file():
        raise RuntimeError("install_first")
    if not desktop_available(system):
        raise RuntimeError("graphical_desktop_required")
    with (p["root"] / "launch-error.log").open("a") as log:
        subprocess.Popen([str(p["python"]), "-B", str(p["app"]), "run"],
                         stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
    if report:
        emit({"status": "starting", "nextAction": "run_diagnose_after_a_few_seconds"})
    return 0


def uninstall(system):
    require_user(system)
    p = paths(system)
    if p["startup"].exists():
        if not startup_owned(system, p["startup"].read_bytes()):
            raise RuntimeError("startup_path_owned_by_another_application")
        if system == "Darwin":
            subprocess.run(["launchctl", "bootout", "gui/%s/%s" % (os.getuid(), LABEL)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10, check=False)
        p["startup"].unlink()
    if p["app"].is_file() and p["python"].is_file():
        subprocess.run([str(p["python"]), "-B", str(p["app"]), "_stop"], check=True, timeout=10, stdout=subprocess.DEVNULL)
    emit({"status": "uninstalled", "retained": ["configuration", "runtime_cache", "local_state"],
          "nextAction": "none"})
    return 0


def windows(command, start_now=False):
    native = "Sysnative" if os.environ.get("PROCESSOR_ARCHITEW6432") else "System32"
    powershell = Path(os.environ["WINDIR"]) / native / "WindowsPowerShell/v1.0/powershell.exe"
    scripts = {"diagnose": "Diagnose.ps1", "install": "Install.ps1", "uninstall": "Uninstall.ps1"}
    if command not in scripts:
        raise RuntimeError("on_windows_run_the_installed_scheduled_task")
    args = [str(powershell), "-NoProfile", "-NonInteractive", "-File", str(REPO / scripts[command])]
    if command == "install" and start_now:
        args.append("-StartNow")
    return subprocess.run(args, check=False).returncode


def main(argv=None):
    parser = argparse.ArgumentParser(description="Compact Task Manager setup and diagnostics")
    parser.add_argument("command", choices=["diagnose", "install", "start", "run", "uninstall", "_probe", "_stop"])
    parser.add_argument("--start-now", action="store_true", help="Start the widget after installation")
    args = parser.parse_args(argv)
    system = platform.system()
    try:
        if system == "Windows":
            return windows(args.command, args.start_now)
        if args.command == "diagnose":
            return diagnose(system)
        if args.command == "install":
            return install(system, args.start_now)
        if args.command == "start":
            return start(system)
        if args.command == "uninstall":
            return uninstall(system)
        if args.command in ("_probe", "_stop"):
            require_user(system)
            emit(_probe(paths(system), stop=args.command == "_stop"))
            return 0
        require_user(system)
        from .widget import run
        return run(paths(system))
    except Exception as exc:
        # Avoid printing personal paths or full subprocess commands in agent-facing output.
        code = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
        emit({"status": "error", "errors": [code], "nextAction": "run_diagnose_and_review_local_logs"})
        return 1
