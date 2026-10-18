import plistlib
import subprocess
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from portable import mac_sensors
from portable.metrics import Sampler


class MacSensorsTests(unittest.TestCase):
    def test_pressure_flags_are_not_internal_enum(self):
        for raw, expected in [(b"1\n", "Normal"), (b"2", "Warning"), (b"4", "Critical"),
                              (b"0", None), (b"3", None), (b"invalid", None)]:
            self.assertEqual(mac_sensors.pressure_level(raw), expected)

    def test_gpu_validates_explicit_overall_counter(self):
        for value, expected in [(0, 0), (53, 53), (100, 100), (-1, None),
                                (101, None), (True, None), ("25", None), (float("nan"), None)]:
            raw = plistlib.dumps([{"PerformanceStatistics": {"Device Utilization %": value}}])
            self.assertEqual(mac_sensors.gpu_utilization(raw), expected)
        self.assertIsNone(mac_sensors.gpu_utilization(plistlib.dumps([
            {"PerformanceStatistics": {"Renderer Utilization %": 50}}])))

    def test_gpu_nested_devices_and_fallback(self):
        raw = plistlib.dumps([{"IORegistryEntryChildren": [
            {"PerformanceStatistics": {"Device Utilization %": 11}},
            {"PerformanceStatistics": {"Device Utilization %": 42}}]}])
        self.assertEqual(mac_sensors.gpu_utilization(raw), 42)
        with patch.object(mac_sensors.subprocess, "check_output", side_effect=[plistlib.dumps([]), raw]) as call:
            self.assertEqual(mac_sensors.read_gpu(), 42)
            self.assertEqual(call.call_args.args[0][4], "IOGPU")

    def test_failures_do_not_become_zero(self):
        for error in (FileNotFoundError(), subprocess.TimeoutExpired("sensor", 1)):
            with patch.object(mac_sensors.subprocess, "check_output", side_effect=error):
                self.assertIsNone(mac_sensors.read_pressure())
                self.assertIsNone(mac_sensors.read_gpu())
        for raw in (b"not a plist", b"<?xml version='1.0'?><plist><broken>"):
            with patch.object(mac_sensors.subprocess, "check_output", return_value=raw):
                self.assertIsNone(mac_sensors.read_gpu())

    def test_snapshot_distinguishes_zero_from_missing_sensor(self):
        with patch.object(mac_sensors, "read_pressure", return_value=None), patch.object(
                mac_sensors, "read_gpu", return_value=0):
            result = mac_sensors.snapshot()
            self.assertFalse(result["memoryPressure"]["available"])
            self.assertTrue(result["gpu"]["available"])
            self.assertEqual(result["gpu"]["utilizationPercent"], 0)

    def test_sampling_keeps_swap_and_pressure_separate_and_expires_failed_gpu(self):
        import psutil
        with patch.object(mac_sensors, "read_pressure", return_value="Warning"), patch.object(
                mac_sensors, "read_gpu", side_effect=[24, None]) as gpu, patch.object(
                psutil, "swap_memory", return_value=SimpleNamespace(used=1024, total=2048)):
            sampler = Sampler(psutil, "Darwin")
            rows = {r[0]: r for r in sampler.sample()}
            self.assertEqual(rows["Pressure"][1:3], (None, "Warning"))
            self.assertEqual(rows["Swap"][1], 1024)
            self.assertEqual(rows["GPU"][1], 24)
            sampler.sample()
            self.assertEqual(gpu.call_count, 1)
            sampler.mac_sampled -= 6
            rows = {r[0]: r for r in sampler.sample()}
            self.assertIsNone(rows["GPU"][1])


if __name__ == "__main__":
    unittest.main()
