"""Optional read-only macOS counters; never require sudo or infer missing values."""
import math
import plistlib
import subprocess
from xml.parsers.expat import ExpatError


def pressure_level(raw):
    # sysctl returns NOTE_MEMORYSTATUS flags, NOT the kernel's internal enum.
    return {b"1": "Normal", b"2": "Warning", b"4": "Critical"}.get(raw.strip())


def gpu_utilization(raw):
    """Only accept a driver's explicit overall percentage, not engine/memory usage."""
    tree = plistlib.loads(raw)
    values = []
    pending = [tree]
    while pending:
        item = pending.pop()
        if isinstance(item, list):
            pending.extend(item)
        elif isinstance(item, dict):
            stats = item.get("PerformanceStatistics")
            if isinstance(stats, dict):
                value = stats.get("Device Utilization %")
                if type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 100:
                    values.append(float(value))
            children = item.get("IORegistryEntryChildren")
            if isinstance(children, list):
                pending.extend(children)
    return max(values) if values else None


def read_pressure():
    try:
        return pressure_level(subprocess.check_output(
            ["/usr/sbin/sysctl", "-n", "kern.memorystatus_vm_pressure_level"],
            timeout=1, stderr=subprocess.DEVNULL))
    except (OSError, subprocess.SubprocessError):
        return None


def read_gpu():
    # Driver registry properties are not a stable public sensor API.
    for driver in ("IOAccelerator", "IOGPU"):
        try:
            raw = subprocess.check_output(
                ["/usr/sbin/ioreg", "-a", "-r", "-c", driver, "-d", "1"],
                timeout=1, stderr=subprocess.DEVNULL)
            value = gpu_utilization(raw)
            if value is not None:
                return value
        except (OSError, ValueError, ExpatError, plistlib.InvalidFileException, subprocess.SubprocessError):
            pass
    return None


def snapshot():
    pressure, gpu = read_pressure(), read_gpu()
    return {"memoryPressure": {"available": pressure is not None, "level": pressure,
                               "source": "kern.memorystatus_vm_pressure_level"},
            "gpu": {"available": gpu is not None, "utilizationPercent": gpu,
                    "source": "IOKit PerformanceStatistics / Device Utilization %"}}
