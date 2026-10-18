"""Read-only samples. Missing counters stay unavailable, not zero utilization."""
import shutil
import subprocess
import time
from . import mac_sensors


def rate(current, previous, elapsed):
    if current is None or previous is None or elapsed <= 0 or current < previous:
        return None
    return (current - previous) / elapsed


def human_bytes(value):
    if value is None:
        return "unavailable"
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024:
            return "%.1f %s" % (value, unit)
        value /= 1024
    return "%.1f PiB" % value


class Sampler:
    def __init__(self, psutil, system):
        self.ps = psutil
        self.system = system
        self.pressure = None
        self.mac_sampled = None
        self.previous = None
        self.ps.cpu_percent(None)  # Discard the meaningless first nonblocking result.
        self.nvidia = shutil.which("nvidia-smi") if system == "Linux" else None
        self.gpu = None
        self.gpu_sampled = 0

    def sample(self):
        now = time.monotonic()
        memory = self.ps.virtual_memory()
        if self.system == "Darwin" and (self.mac_sampled is None or now - self.mac_sampled >= 5):
            self.pressure = mac_sensors.read_pressure()
            self.gpu = mac_sensors.read_gpu()
            self.mac_sampled = now
        try:
            disk = self.ps.disk_io_counters()
        except (OSError, self.ps.Error):
            disk = None
        try:
            network = self.ps.net_io_counters()
        except (OSError, self.ps.Error):
            network = None
        current = (now, disk, network)
        disk_rate = net_rate = None
        if self.previous:
            before, old_disk, old_network = self.previous
            if disk and old_disk:
                disk_rate = rate(disk.read_bytes + disk.write_bytes,
                                 old_disk.read_bytes + old_disk.write_bytes, now - before)
            if network and old_network:
                net_rate = rate(network.bytes_sent + network.bytes_recv,
                                old_network.bytes_sent + old_network.bytes_recv, now - before)
        self.previous = current
        if self.nvidia and now - self.gpu_sampled >= 5:
            self.gpu_sampled = now
            try:
                output = subprocess.check_output([self.nvidia, "--query-gpu=utilization.gpu",
                                                  "--format=csv,noheader,nounits"],
                                                 text=True, timeout=1, stderr=subprocess.DEVNULL)
                values = [float(line.strip()) for line in output.splitlines() if line.strip()]
                self.gpu = max(values) if values and all(0 <= v <= 100 for v in values) else None
            except (OSError, ValueError, subprocess.SubprocessError):
                self.gpu = None
        rows = [
            ("CPU", self.ps.cpu_percent(None), "System utilization", True),
            ("Memory", memory.percent, human_bytes(memory.total - memory.available) + " / " + human_bytes(memory.total), True),
            ("Disk I/O", disk_rate, human_bytes(disk_rate) + ("/s total read + write" if disk_rate is not None else ""), False),
            ("Network", net_rate, human_bytes(net_rate) + ("/s total send + receive" if net_rate is not None else ""), False),
            ("GPU", self.gpu, ("Driver GPU utilization" if self.system == "Darwin" else "Peak NVIDIA GPU utilization") if self.gpu is not None else "GPU reading unavailable", True),
        ]
        if self.system == "Darwin":
            try:
                swap = self.ps.swap_memory()
                swap_value = swap.used
                swap_detail = human_bytes(swap.used) + " used / " + human_bytes(swap.total) + " allocated"
            except (OSError, self.ps.Error):
                swap_value, swap_detail = None, "Swap reading unavailable"
            # Pressure is categorical; never present it as a made-up percentage.
            rows.extend([("Pressure", None, self.pressure or "Unavailable", False),
                         ("Swap", swap_value, swap_detail, False)])
        return rows
