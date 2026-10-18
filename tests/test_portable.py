import contextlib
import io
import json
import os
from pathlib import Path
import plistlib
import tempfile
import unittest
from unittest.mock import patch

from portable import cli, core
from portable.metrics import rate, Sampler


class PortableTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)

    def fixture(self):
        return dict(supported=True, errors=[], tkinter=True, desktop=True,
                    installed=True, dependencies=True, startupMatches=True, configValid=True,
                    runtime=dict(healthy=True, state="running"))

    def test_diagnoses_do_not_confuse_stale_and_live_widgets(self):
        o = self.fixture()
        self.assertEqual(core.decision(o)[0], "healthy")
        o["runtime"] = core.runtime_report({"status": "running", "updatedAt": 20}, True, now=100)
        self.assertEqual(core.decision(o)[0], "not_running")
        o["runtime"] = core.runtime_report({"status": "running", "updatedAt": 100}, False, now=100)
        self.assertEqual(core.decision(o)[0], "not_running")
        self.assertFalse(core.runtime_report({"status": "running", "updatedAt": 120}, True, now=100)["healthy"])

    def test_next_actions_cover_unsupported_dependencies_and_errors(self):
        cases = [("supported", False, "unsupported"), ("errors", ["permission_denied"], "unknown"),
                 ("tkinter", False, "missing_dependency"), ("desktop", False, "headless"),
                 ("installed", False, "not_installed"), ("dependencies", False, "partial_installation"),
                 ("startupMatches", False, "partial_installation"), ("configValid", False, "invalid_configuration")]
        for key, value, expected in cases:
            with self.subTest(key=key):
                o = self.fixture(); o[key] = value
                status, action = core.decision(o)
                self.assertEqual(status, expected)
                self.assertFalse(action["requiresElevation"])

    def test_launchagent_is_per_user_aqua_and_uses_argument_array(self):
        p = core.paths("Darwin", self.home / "Name With Spaces", {})
        result = plistlib.loads(core.startup_bytes("Darwin", p))
        self.assertEqual(result["ProgramArguments"], [str(p["python"]), str(p["app"]), "run"])
        self.assertEqual(result["LimitLoadToSessionType"], "Aqua")
        self.assertTrue(result["RunAtLoad"])
        self.assertNotIn("KeepAlive", result)
        self.assertTrue(core.startup_owned("Darwin", core.startup_bytes("Darwin", p)))
        self.assertFalse(core.startup_owned("Darwin", plistlib.dumps({"Label": "someone.else"})))

    def test_linux_startup_quotes_paths_without_a_shell(self):
        p = core.paths("Linux", self.home / 'Name $with% "quotes"', {})
        entry = core.startup_bytes("Linux", p).decode()
        self.assertIn("Type=Application", entry)
        self.assertIn("Terminal=false", entry)
        self.assertIn("%%", entry)
        self.assertIn('\\\\"', entry)
        self.assertNotIn("sh -c", entry)
        self.assertNotIn("Hidden=true", entry)
        self.assertTrue(core.startup_owned("Linux", entry.encode()))
        with self.assertRaises(ValueError):
            core.desktop_quote("bad\npath")

    def test_xdg_paths_and_invalid_relative_xdg(self):
        p = core.paths("Linux", self.home, {"XDG_DATA_HOME": str(self.home / "data"), "XDG_CONFIG_HOME": str(self.home / "settings")})
        self.assertEqual(p["startup"].parent, self.home / "settings/autostart")
        with self.assertRaises(ValueError):
            core.paths("Linux", self.home, {"XDG_DATA_HOME": "relative"})

    def test_configuration_rejects_nonfinite_and_invalid_types(self):
        for data in ({"width": True}, {"width": 20}, {"x": 1}, {"intervalSeconds": float("nan")},
                     {"intervalSeconds": 0}, {"alwaysOnTop": 1}, [], {"x": "4", "y": 2}):
            with self.subTest(data=data), self.assertRaises(ValueError):
                core.config_from(data)
        self.assertEqual(core.config_from({"x": -100, "y": 20})["x"], -100)

    def test_counter_resets_and_first_sample_stay_unavailable(self):
        self.assertIsNone(rate(10, None, 1))
        self.assertIsNone(rate(10, 20, 1))
        self.assertIsNone(rate(10, 1, 0))
        self.assertEqual(rate(300, 100, 2), 100)

    def test_real_metrics_are_bounded(self):
        import psutil
        sampler = Sampler(psutil, "Darwin")  # Never calls a GPU vendor utility in tests.
        rows = sampler.sample()
        self.assertEqual([r[0] for r in rows], ["CPU", "Memory", "Disk I/O", "Network", "GPU"])
        self.assertTrue(0 <= rows[0][1] <= 100)
        self.assertTrue(0 <= rows[1][1] <= 100)
        self.assertIsNone(rows[2][1])
        self.assertIsNone(rows[4][1])

    def test_diagnose_is_json_and_does_not_create_files(self):
        p = core.paths("Linux", self.home, {})
        before = list(self.home.rglob("*"))
        with patch.object(cli, "paths", return_value=p), patch.object(cli, "probe_dependencies", return_value={"tkinter": True, "psutil": False}), patch.object(cli, "desktop_available", return_value=True):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = cli.diagnose("Linux")
        result = json.loads(output.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(result["status"], "not_installed")
        self.assertEqual(result["visualVerification"], "not_performed")
        self.assertNotIn(str(self.home), output.getvalue())
        self.assertEqual(before, list(self.home.rglob("*")))

    def test_installer_preserves_config_and_uninstaller_only_removes_owned_startup(self):
        p = core.paths("Linux", self.home, {})
        p["python"].parent.mkdir(parents=True)
        p["python"].touch()
        core.atomic_json(p["config"], {"width": 420})
        with patch.object(cli, "paths", return_value=p), patch.object(cli, "require_user"), patch.object(cli.importlib.util, "find_spec", return_value=object()), patch.object(cli.subprocess, "run") as run:
            with contextlib.redirect_stdout(io.StringIO()):
                cli.install("Linux")
            self.assertEqual(json.loads(p["config"].read_text())["width"], 420)
            self.assertTrue(p["app"].exists())
            self.assertEqual(p["startup"].read_bytes(), core.startup_bytes("Linux", p))
            # Reinstall is repeatable and must not spawn the widget by default.
            with contextlib.redirect_stdout(io.StringIO()):
                cli.install("Linux")
                cli.uninstall("Linux")
            self.assertFalse(p["startup"].exists())
            self.assertTrue(p["config"].exists())
            self.assertTrue(p["app"].exists())
            self.assertTrue(run.called)

    def test_installer_refuses_foreign_startup(self):
        p = core.paths("Linux", self.home, {})
        p["startup"].parent.mkdir(parents=True)
        p["startup"].write_text("[Desktop Entry]\nName=Someone else\n")
        with patch.object(cli, "paths", return_value=p), patch.object(cli, "require_user"), patch.object(cli.importlib.util, "find_spec", return_value=object()):
            with self.assertRaisesRegex(RuntimeError, "owned_by_another"):
                cli.install("Linux")
        self.assertIn("Someone else", p["startup"].read_text())

    def test_headless_linux_and_ssh_mac(self):
        self.assertFalse(cli.desktop_available("Linux", {}))
        self.assertFalse(cli.desktop_available("Linux", {"WAYLAND_DISPLAY": "wayland-0"}))
        self.assertTrue(cli.desktop_available("Linux", {"DISPLAY": ":99"}))
        self.assertFalse(cli.desktop_available("Darwin", {"SSH_CONNECTION": "example"}))


if __name__ == "__main__":
    unittest.main()
