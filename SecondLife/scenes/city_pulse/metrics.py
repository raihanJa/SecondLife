"""Live/demo system metrics for City Pulse — unchanged from the standalone app."""
import math

try:
    import psutil
except ImportError:
    psutil = None

from shared.utils.mathutil import clamp

MB = 1024.0 * 1024.0


class MetricsProvider:
    """Samples live system metrics via psutil (rates computed from deltas)."""

    SAMPLE_EVERY = 0.5

    def __init__(self):
        self.available = psutil is not None
        self.cpu = 0.0
        self.ram = 0.0
        self.dl = 0.0
        self.ul = 0.0
        self.disk_r = 0.0
        self.disk_w = 0.0
        self._timer = 0.0
        self._net = None
        self._disk = None
        if self.available:
            try:
                psutil.cpu_percent(interval=None)
                self._net = psutil.net_io_counters()
                self._disk = psutil.disk_io_counters()
                self.ram = psutil.virtual_memory().percent
            except Exception:
                self.available = False

    def update(self, dt):
        if not self.available:
            return
        self._timer += dt
        if self._timer < self.SAMPLE_EVERY:
            return
        elapsed = self._timer
        self._timer = 0.0
        try:
            self.cpu = psutil.cpu_percent(interval=None)
            self.ram = psutil.virtual_memory().percent
            net = psutil.net_io_counters()
            if net and self._net:
                self.dl = max(0.0, (net.bytes_recv - self._net.bytes_recv) / elapsed)
                self.ul = max(0.0, (net.bytes_sent - self._net.bytes_sent) / elapsed)
            self._net = net
            disk = psutil.disk_io_counters()
            if disk and self._disk:
                self.disk_r = max(0.0, (disk.read_bytes - self._disk.read_bytes) / elapsed)
                self.disk_w = max(0.0, (disk.write_bytes - self._disk.write_bytes) / elapsed)
            self._disk = disk
        except Exception:
            pass


class DemoMetrics:
    """Synthetic, slowly-evolving metrics for demo mode."""

    def sample(self, t):
        burst = max(0.0, math.sin(t * 0.23 + 1.4)) ** 6
        cpu = clamp(46 + 30 * math.sin(t * 0.34) + 11 * math.sin(t * 1.9) + burst * 28, 2, 99)
        ram = clamp(56 + 21 * math.sin(t * 0.11 + 2.2) + 5 * math.sin(t * 0.9), 8, 97)
        dl = max(0.0, (2.4 + 2.2 * math.sin(t * 0.5) + burst * 7) * MB)
        ul = max(0.0, (0.8 + 0.7 * math.sin(t * 0.4 + 3) + burst * 2.4) * MB)
        dr = max(0.0, (7 + 9 * math.sin(t * 0.7 + 1) + burst * 45) * MB)
        dw = max(0.0, (4 + 6 * math.sin(t * 0.55 + 4) + burst * 25) * MB)
        return cpu, ram, dl, ul, dr, dw
