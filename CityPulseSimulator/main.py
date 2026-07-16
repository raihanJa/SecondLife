"""
CITY PULSE SIMULATOR
====================
A living, neon-soaked isometric cyberpunk city block powered by your
computer's vital signs. One compact city island, districts packed tight:

  CPU      -> Electric-orange processing towers (back-right, pulse with load)
  RAM      -> Cyan memory spires (back-left, windows fill with memory)
  Download -> Blue expressway cutting through the island (glowing pods)
  Upload   -> Purple expressway crossing it (glowing pods, light trails)
  Disk     -> Lime storage docks (warehouses, cranes, trucks, front-left)
  GPU      -> Magenta fusion reactor on its own satellite platform
              (core pulse = load, core colour = temperature, fuel
              rods = VRAM, cooling-tower steam = heat)
  Stress   -> Red beacons, drones, rain, lightning, emergency pods

The 3D look is faked entirely with 2D shapes: isometric boxes with lit
side faces, rooftops, shadows, additive glow and wet reflections.

Controls:  ESC quit | SPACE pause | M live/demo | R stress surge

Everything is drawn procedurally - no external assets.
"""

import math
import os
import random
import sys
from collections import deque

import pygame

try:
    import psutil
except ImportError:  # graceful fallback: demo mode only
    psutil = None

try:
    import pynvml
except ImportError:  # graceful fallback: nvidia-smi or demo values
    pynvml = None

# ----------------------------------------------------------------------------
# Config / palette
# ----------------------------------------------------------------------------

WIDTH, HEIGHT = 1280, 800
FPS = 60

KB = 1024.0
MB = KB * 1024.0

COL_BG_TOP = (5, 7, 18)
COL_BG_BOT = (11, 14, 32)
COL_TEXT_DIM = (168, 192, 224)
COL_TEXT = (190, 215, 245)
COL_PANEL_EDGE = (80, 190, 255)

CPU_COLOR = (255, 122, 24)          # electric orange
RAM_COLOR = (0, 224, 255)           # bright cyan
DOWN_COLOR = (52, 130, 255)         # bright blue
UP_COLOR = (178, 74, 255)           # purple
DISK_COLOR = (128, 255, 64)         # lime green
GPU_COLOR = (255, 64, 200)          # hot magenta
STRESS_COLOR = (255, 46, 64)        # red

# reactor-core temperature gradient (cool -> warm -> critical)
GPU_TEMP_COOL = (60, 220, 255)      # icy cyan      (~<50 C)
GPU_TEMP_WARM = (255, 170, 40)      # furnace amber (~70 C)
GPU_TEMP_HOT = (255, 60, 60)        # red-hot       (~85+ C)


def gpu_temp_color(temp_n):
    """0..1 normalised core temperature -> glow colour."""
    if temp_n < 0.55:
        return mix(GPU_TEMP_COOL, GPU_TEMP_WARM, clamp(temp_n / 0.55))
    return mix(GPU_TEMP_WARM, GPU_TEMP_HOT, clamp((temp_n - 0.55) / 0.45))

HUD_RECT = pygame.Rect(988, 18, 276, 764)

# ----------------------------------------------------------------------------
# Isometric projection
# ----------------------------------------------------------------------------
# The city lives on a GRID_N x GRID_N diamond island. World coords are
# (gx, gy) on the ground plane plus gz height in screen pixels.

TILE_W, TILE_H = 44, 22            # screen size of one iso tile
HW, HH = TILE_W // 2, TILE_H // 2
GRID_N = 20
ISO_OX, ISO_OY = 496, 150          # screen position of grid corner (0, 0)
PLAT_SIDE = 26                     # platform slab thickness (px)


def iso(gx, gy, gz=0.0):
    """World grid coords -> screen pixel coords."""
    return (ISO_OX + (gx - gy) * HW, ISO_OY + (gx + gy) * HH - gz)


def box_points(gx, gy, w, d, h):
    """Screen-space corners of an iso box: base A,B,C,D and roof At..Dt.
    A = back corner, B = right, C = front (closest to camera), D = left."""
    A, B = iso(gx, gy), iso(gx + w, gy)
    C, D = iso(gx + w, gy + d), iso(gx, gy + d)
    At, Bt = iso(gx, gy, h), iso(gx + w, gy, h)
    Ct, Dt = iso(gx + w, gy + d, h), iso(gx, gy + d, h)
    return A, B, C, D, At, Bt, Ct, Dt


def on_island(gx, gy):
    return 0.0 <= gx <= GRID_N and 0.0 <= gy <= GRID_N


def clamp(v, lo=0.0, hi=1.0):
    return lo if v < lo else hi if v > hi else v


def lerp(a, b, t):
    return a + (b - a) * t


def mix(c1, c2, t):
    return (int(lerp(c1[0], c2[0], t)), int(lerp(c1[1], c2[1], t)),
            int(lerp(c1[2], c2[2], t)))


def col_scale(color, f):
    f = clamp(f, 0.0, 1.0)
    return (int(color[0] * f), int(color[1] * f), int(color[2] * f))


def soft_norm(value, ref):
    """Map an unbounded value (bytes/s) into 0..1 softly."""
    return value / (value + ref) if value > 0 else 0.0


def fmt_speed(bps):
    if bps >= MB:
        return f"{bps / MB:5.1f} MB/s"
    if bps >= KB:
        return f"{bps / KB:5.0f} KB/s"
    return f"{bps:5.0f}  B/s"


def sysfont(size, bold=False):
    try:
        return pygame.font.SysFont("consolas", size, bold=bold)
    except Exception:
        return pygame.font.Font(None, size + 4)


# ----------------------------------------------------------------------------
# Glow rendering (cached radial gradients, blitted additively)
# ----------------------------------------------------------------------------

_GLOW_CACHE = {}


def _make_glow(radius, color):
    surf = pygame.Surface((radius * 2, radius * 2))
    for r in range(radius, 0, -1):
        f = (1.0 - r / radius) ** 2
        pygame.draw.circle(surf, col_scale(color, f), (radius, radius), r)
    return surf


def blit_glow(dst, center, radius, color, intensity=1.0):
    intensity = clamp(intensity, 0.0, 1.0)
    if intensity <= 0.02 or radius < 2:
        return
    c = col_scale(color, intensity)
    key = (int(radius), c[0] // 8, c[1] // 8, c[2] // 8)
    surf = _GLOW_CACHE.get(key)
    if surf is None:
        surf = _make_glow(int(radius), (key[1] * 8, key[2] * 8, key[3] * 8))
        _GLOW_CACHE[key] = surf
    dst.blit(surf, (center[0] - radius, center[1] - radius),
             special_flags=pygame.BLEND_RGB_ADD)


# ----------------------------------------------------------------------------
# Metrics
# ----------------------------------------------------------------------------

class MetricsProvider:
    """Samples live system metrics via psutil (rates computed from deltas)."""

    SAMPLE_EVERY = 0.5

    def __init__(self):
        self.available = psutil is not None
        self.cpu = 0.0
        self.ram = 0.0
        self.dl = 0.0        # bytes/s
        self.ul = 0.0
        self.disk_r = 0.0
        self.disk_w = 0.0
        self._timer = 0.0
        self._net = None
        self._disk = None
        if self.available:
            try:
                psutil.cpu_percent(interval=None)  # prime
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


class GpuMetrics:
    """GPU load / temperature / VRAM. Prefers NVML (nvidia-ml-py); falls
    back to polling nvidia-smi on a background thread; else unavailable."""

    SAMPLE_EVERY = 1.0

    def __init__(self):
        self.util = 0.0          # %
        self.temp = 0.0          # degrees C
        self.vram_used = 0.0     # bytes
        self.vram_total = 0.0
        self._timer = self.SAMPLE_EVERY   # sample immediately on first update
        self._handle = None
        self.available = False
        if pynvml is not None:
            try:
                pynvml.nvmlInit()
                self._handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                self.available = True
            except Exception:
                self._handle = None
        if not self.available:
            self.available = self._start_smi_thread()

    # -- nvidia-smi fallback (subprocess polled off the render thread) -------

    def _start_smi_thread(self):
        import shutil
        if shutil.which("nvidia-smi") is None:
            return False
        import threading
        threading.Thread(target=self._smi_loop, daemon=True).start()
        return True

    def _smi_loop(self):
        import subprocess
        import time
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        query = ("--query-gpu=utilization.gpu,temperature.gpu,"
                 "memory.used,memory.total")
        while True:
            try:
                out = subprocess.check_output(
                    ["nvidia-smi", query, "--format=csv,noheader,nounits"],
                    creationflags=flags, timeout=5, text=True)
                u, tc, mu, mt = out.strip().splitlines()[0].split(",")
                self.util = float(u)
                self.temp = float(tc)
                self.vram_used = float(mu) * MB
                self.vram_total = float(mt) * MB
            except Exception:
                pass
            time.sleep(1.5)

    # -- NVML sampling --------------------------------------------------------

    def update(self, dt):
        if self._handle is None:
            return               # smi thread (or nothing) feeds the fields
        self._timer += dt
        if self._timer < self.SAMPLE_EVERY:
            return
        self._timer = 0.0
        try:
            self.util = float(
                pynvml.nvmlDeviceGetUtilizationRates(self._handle).gpu)
            self.temp = float(pynvml.nvmlDeviceGetTemperature(
                self._handle, pynvml.NVML_TEMPERATURE_GPU))
            mem = pynvml.nvmlDeviceGetMemoryInfo(self._handle)
            self.vram_used = float(mem.used)
            self.vram_total = float(mem.total)
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
        gpu = clamp(38 + 34 * math.sin(t * 0.27 + 4.1) + 9 * math.sin(t * 1.3)
                    + burst * 34, 1, 99)
        gtemp = clamp(47 + 20 * math.sin(t * 0.19 + 4.6) + burst * 22, 34, 93)
        gvram_total = 8.0 * KB * MB
        gvram = clamp(0.42 + 0.30 * math.sin(t * 0.13 + 1.1) + burst * 0.18,
                      0.05, 0.97) * gvram_total
        return cpu, ram, dl, ul, dr, dw, gpu, gtemp, gvram, gvram_total


# ----------------------------------------------------------------------------
# Isometric buildings
# ----------------------------------------------------------------------------

class IsoBuilding:
    """Pseudo-3D tower: shadow, two lit side faces, neon-edged rooftop,
    glowing window grid, optional antenna / rooftop neon sign."""

    def __init__(self, gx, gy, w, d, h, color, metric, sign=None):
        self.color = color
        self.metric = metric
        self.h = h
        self.key = gx + gy + w + d           # painter depth: front corner
        (self.A, self.B, self.C, self.D,
         self.At, self.Bt, self.Ct, self.Dt) = box_points(gx, gy, w, d, h)
        self.top = [self.At, self.Bt, self.Ct, self.Dt]
        self.right = [self.Bt, self.Ct, self.C, self.B]
        self.left = [self.Dt, self.Ct, self.C, self.D]
        self.roof_c = ((self.At[0] + self.Ct[0]) // 2,
                       (self.At[1] + self.Ct[1]) // 2)
        self.phase = random.uniform(0, math.tau)
        self.pulse_speed = random.uniform(0.8, 1.4)
        self.antenna = random.random() < 0.45
        self.windows = []
        self._face_windows(self.Bt, self.Ct, self.B, self.C)
        self._face_windows(self.Dt, self.Ct, self.D, self.C)
        self.order = list(range(len(self.windows)))
        random.shuffle(self.order)
        self.rand = [random.random() for _ in self.windows]
        self.sign = self._make_sign(sign) if sign else None

    def _face_windows(self, ta, tb, ba, bb):
        length = math.hypot(tb[0] - ta[0], tb[1] - ta[1])
        cols = max(1, int(length / 10))
        for i in range(cols):
            u = (i + 0.5) / cols
            wx = lerp(ta[0], tb[0], u)
            wy = lerp(ta[1], tb[1], u) + 7
            bottom = lerp(ba[1], bb[1], u)
            while wy < bottom - 8:
                self.windows.append((int(wx - 2), int(wy)))
                wy += 11

    def _make_sign(self, text):
        f = sysfont(11, bold=True)
        txt = f.render(text, True, mix(self.color, (255, 255, 255), 0.35))
        board = pygame.Surface((txt.get_width() + 10, txt.get_height() + 5))
        board.fill((10, 12, 22))
        pygame.draw.rect(board, col_scale(self.color, 0.85), board.get_rect(), 1)
        board.blit(txt, (5, 2))
        return board

    def draw(self, surf, t, activity, stress):
        c = self.color
        is_cpu = self.metric == "cpu"
        pulse = 0.5 + 0.5 * math.sin(
            t * self.pulse_speed * (1.2 + activity * (5.0 if is_cpu else 1.8))
            + self.phase)
        glowf = activity * (0.45 + 0.55 * pulse) if is_cpu \
            else activity * (0.75 + 0.25 * pulse)

        # drop shadow cast to the lower-left of the slab
        pygame.draw.polygon(surf, (7, 9, 17), [
            self.D, self.C, (self.C[0] - 18, self.C[1] + 9),
            (self.D[0] - 18, self.D[1] + 9)])

        # faces: left darkest, right lit, roof dark with neon rim
        pygame.draw.polygon(surf, mix((12, 14, 27), c, 0.05 + 0.05 * activity),
                            self.left)
        pygame.draw.polygon(surf, mix((17, 20, 36), c, 0.10 + 0.08 * activity),
                            self.right)
        pygame.draw.polygon(surf, mix((9, 11, 22), c, 0.16 + 0.10 * glowf),
                            self.top)
        edge = col_scale(c, 0.30 + 0.55 * glowf + 0.10 * stress)
        pygame.draw.lines(surf, edge, True, self.top, 1)
        pygame.draw.line(surf, col_scale(c, 0.45 + 0.55 * glowf), self.Ct, self.C)
        pygame.draw.line(surf, col_scale(c, 0.25), self.Bt, self.B)
        pygame.draw.line(surf, col_scale(c, 0.16), self.Dt, self.D)
        blit_glow(surf, self.roof_c, max(12, (self.B[0] - self.D[0]) // 2),
                  c, 0.10 + 0.28 * glowf)

        # window grid
        n = len(self.windows)
        if n:
            if self.metric == "ram":
                lit = int(n * clamp(activity * 1.05))
            elif is_cpu:
                lit = int(n * clamp(activity * (0.5 + 0.4 * pulse)))
            else:
                lit = int(n * clamp(activity * 0.9))
            dark = mix((10, 12, 22), c, 0.06)
            for idx in range(n):
                wx, wy = self.windows[self.order[idx]]
                if idx < lit:
                    tw = 0.6 + 0.4 * math.sin(t * 3.1 + self.rand[idx] * 12.0)
                    surf.fill(col_scale(c, tw), (wx, wy, 4, 6))
                else:
                    surf.fill(dark, (wx, wy, 4, 6))

        # rising data band on memory spires
        if self.metric == "ram" and activity > 0.12:
            span = self.h - 8
            v = (t * (24 + 70 * activity) + self.phase * 40) % span
            pa = (self.B[0], self.B[1] - 4 - v)
            pb = (self.C[0], self.C[1] - 4 - v)
            pygame.draw.line(surf, col_scale(c, 0.3 + 0.5 * activity), pa, pb)
            blit_glow(surf, ((pa[0] + pb[0]) // 2, (pa[1] + pb[1]) // 2),
                      8, c, 0.4 * activity)

        # wet reflection pooling under the bright front corner
        if glowf > 0.15:
            fx, fy = self.C
            pygame.draw.line(surf, col_scale(c, 0.10 + 0.18 * glowf),
                             (fx, fy + 2), (fx, fy + 9 + int(8 * glowf)))
            blit_glow(surf, (fx, fy + 6), 10, c, 0.16 * glowf)

        # antenna + beacon (turns red under stress)
        if self.antenna:
            ax, ay = self.roof_c
            pygame.draw.line(surf, col_scale(c, 0.5), (ax, ay), (ax, ay - 13))
            beat = 0.5 + 0.5 * math.sin(t * 2.4 + self.phase)
            if beat > 0.55:
                bc = STRESS_COLOR if (stress > 0.6 or is_cpu) else c
                pygame.draw.circle(surf, bc, (ax, ay - 14), 2)
                blit_glow(surf, (ax, ay - 14), 8, bc, beat * 0.8)

        # rooftop neon sign on a pole
        if self.sign:
            sw, sh = self.sign.get_size()
            bx = self.roof_c[0] - sw // 2
            by = self.roof_c[1] - 20 - sh
            pygame.draw.line(surf, (60, 70, 100), self.roof_c,
                             (self.roof_c[0], by + sh))
            surf.blit(self.sign, (bx, by))
            blit_glow(surf, (self.roof_c[0], by + sh // 2), sw,
                      c, 0.20 + 0.25 * glowf)


class IsoWarehouse:
    """Low, wide storage dock: iso slab, animated loading door, crates."""

    metric = "disk"

    def __init__(self, gx, gy, w=2.6, d=1.9, h=24):
        self.key = gx + gy + w + d
        (self.A, self.B, self.C, self.D,
         self.At, self.Bt, self.Ct, self.Dt) = box_points(gx, gy, w, d, h)
        self.h = h
        self.top = [self.At, self.Bt, self.Ct, self.Dt]
        self.right = [self.Bt, self.Ct, self.C, self.B]
        self.left = [self.Dt, self.Ct, self.C, self.D]
        self.phase = random.uniform(0, math.tau)
        # loading door on the right face (u along B -> C)
        self.door = []
        for u in (0.30, 0.72):
            x = lerp(self.B[0], self.C[0], u)
            y = lerp(self.B[1], self.C[1], u)
            self.door.append((x, y))
        self.door_h = h - 8
        # crates stacked out front
        self.crates = []
        cx = gx + 0.2
        for _ in range(random.randint(2, 4)):
            s = random.uniform(0.30, 0.45)
            self.crates.append(box_points(cx, gy + d + 0.15, s, s, s * 22))
            cx += s + 0.15

    def draw(self, surf, t, activity, stress):
        c = DISK_COLOR
        pygame.draw.polygon(surf, (7, 9, 17), [
            self.D, self.C, (self.C[0] - 14, self.C[1] + 7),
            (self.D[0] - 14, self.D[1] + 7)])
        pygame.draw.polygon(surf, mix((12, 15, 24), c, 0.06), self.left)
        pygame.draw.polygon(surf, mix((16, 20, 30), c, 0.11), self.right)
        pygame.draw.polygon(surf, mix((10, 13, 20), c, 0.15 + 0.1 * activity),
                            self.top)
        pygame.draw.lines(surf, col_scale(c, 0.35 + 0.35 * activity), True,
                          self.top, 1)
        pygame.draw.line(surf, col_scale(c, 0.5), self.Ct, self.C)
        blit_glow(surf, ((self.At[0] + self.Ct[0]) // 2,
                         (self.At[1] + self.Ct[1]) // 2),
                  22, c, 0.10 + 0.25 * activity)

        # loading door + rolling shutter light bars
        (x0, y0), (x1, y1) = self.door
        dh = self.door_h
        pygame.draw.polygon(surf, (8, 12, 16),
                            [(x0, y0 - dh), (x1, y1 - dh), (x1, y1), (x0, y0)])
        pygame.draw.lines(surf, col_scale(c, 0.55), True,
                          [(x0, y0 - dh), (x1, y1 - dh), (x1, y1), (x0, y0)], 1)
        if activity > 0.05:
            offset = (t * (10 + 55 * activity) + self.phase * 10) % 6
            v = 2 + offset
            bright = 0.25 + 0.55 * activity
            while v < dh - 2:
                pygame.draw.line(surf, col_scale(c, bright),
                                 (x0 + 1, y0 - v), (x1 - 1, y1 - v))
                v += 6
            blit_glow(surf, ((x0 + x1) / 2, (y0 + y1) / 2), 14, c,
                      0.35 * activity)

        # crates (tiny iso boxes)
        for (_, _, cc, cd, cat, cbt, cct, cdt) in self.crates:
            pygame.draw.polygon(surf, mix((13, 17, 22), c, 0.10),
                                [cdt, cct, cc, cd])
            pygame.draw.polygon(surf, mix((16, 21, 28), c, 0.16),
                                [cat, cbt, cct, cdt])
            pygame.draw.lines(surf, col_scale(c, 0.4), True,
                              [cat, cbt, cct, cdt], 1)

        # roof beacon
        beat = 0.5 + 0.5 * math.sin(t * (1.5 + 4 * activity) + self.phase)
        if activity > 0.25 and beat > 0.5:
            bx, by = self.Bt
            pygame.draw.circle(surf, c, (bx - 4, by + 2), 2)
            blit_glow(surf, (bx - 4, by + 2), 9, c, beat)


class Crane:
    """Dock crane anchored to a grid cell; trolley speed follows disk I/O."""

    metric = "disk"

    def __init__(self, gx, gy, height=86, jib=64, flip=False):
        self.key = gx + gy + 1.0
        self.x, self.ground = iso(gx, gy)
        self.h = height
        self.jib = jib
        self.flip = -1 if flip else 1
        self.phase = random.uniform(0, math.tau)

    def draw(self, surf, t, activity, stress):
        c = col_scale(DISK_COLOR, 0.55 + 0.25 * activity)
        top = self.ground - self.h
        x = self.x
        pygame.draw.line(surf, c, (x - 4, self.ground), (x - 4, top))
        pygame.draw.line(surf, c, (x + 4, self.ground), (x + 4, top))
        for i, y in enumerate(range(int(top), int(self.ground) - 8, 12)):
            if i % 2 == 0:
                pygame.draw.line(surf, col_scale(c, 0.6), (x - 4, y), (x + 4, y + 12))
            else:
                pygame.draw.line(surf, col_scale(c, 0.6), (x + 4, y), (x - 4, y + 12))
        tip = x + self.flip * self.jib
        pygame.draw.line(surf, c, (x - self.flip * 16, top + 4), (tip, top + 4), 2)
        pygame.draw.line(surf, col_scale(c, 0.7), (x, top - 9), (tip, top + 4))
        pygame.draw.line(surf, col_scale(c, 0.7), (x, top - 9),
                         (x - self.flip * 16, top + 4))
        pygame.draw.rect(surf, mix((14, 18, 24), DISK_COLOR, 0.25),
                         (x - self.flip * 16 - 4, top + 2, 8, 7))
        speed = 0.25 + activity * 1.9
        tpos = 0.25 + 0.62 * (0.5 + 0.5 * math.sin(t * speed + self.phase))
        tx = x + self.flip * self.jib * tpos
        drop = 14 + (0.5 + 0.5 * math.sin(t * speed * 0.63 + self.phase * 2)) \
            * (self.h - 44)
        pygame.draw.rect(surf, c, (int(tx - 3), int(top + 3), 6, 4))
        pygame.draw.line(surf, col_scale(c, 0.8), (tx, top + 7), (tx, top + 7 + drop))
        box = pygame.Rect(int(tx - 6), int(top + 7 + drop), 12, 8)
        pygame.draw.rect(surf, mix((10, 14, 20), DISK_COLOR, 0.3), box)
        pygame.draw.rect(surf, col_scale(DISK_COLOR, 0.8), box, 1)
        if activity > 0.15:
            blit_glow(surf, box.center, 10, DISK_COLOR, 0.4 * activity)
        beat = 0.5 + 0.5 * math.sin(t * 2.1 + self.phase)
        if beat > 0.45:
            pygame.draw.circle(surf, STRESS_COLOR, (int(tip), int(top + 3)), 2)
            blit_glow(surf, (tip, top + 3), 7, STRESS_COLOR, beat * 0.7)


class Streetlight:
    """Tiny neon streetlight with a glowing pool on the wet asphalt."""

    def __init__(self, gx, gy, color, metric):
        self.key = gx + gy
        self.x, self.y = iso(gx, gy)
        self.color = color
        self.metric = metric
        self.phase = random.uniform(0, math.tau)

    def draw(self, surf, t, activity, stress):
        c = self.color
        f = 0.35 + 0.55 * activity
        pygame.draw.line(surf, (46, 54, 78), (self.x, self.y), (self.x, self.y - 14))
        pygame.draw.line(surf, (46, 54, 78), (self.x, self.y - 14),
                         (self.x + 4, self.y - 13))
        pygame.draw.circle(surf, col_scale(c, 0.6 + 0.4 * f),
                           (self.x + 4, self.y - 12), 2)
        blit_glow(surf, (self.x + 4, self.y - 12), 9, c, f)
        blit_glow(surf, (self.x + 3, self.y + 2), 7, c, f * 0.45)


class Reactor:
    """GPU fusion reactor on its own satellite platform: a containment
    ring holding a floating plasma core. Core pulse rate & orbiting
    charge = GPU load, core colour = temperature (icy cyan -> red-hot),
    fuel rods fill with VRAM, twin cooling towers vent steam with heat,
    and past ~82 C the whole site strobes red."""

    metric = "gpu"

    CX_G, CY_G = 27.0, 18.0            # platform centre in grid coords
    RODS = 8

    def __init__(self):
        self.city = None               # wired up by City after construction
        self.key = self.CX_G + self.CY_G + 6.0     # frontmost in draw order
        self.cx, self.cy = iso(self.CX_G, self.CY_G)
        self.phase = random.uniform(0, math.tau)
        self.towers = [(-74, -16, 76), (78, -12, 88)]   # dx, dy, height
        self.steam = []                # [x, y, vx, vy, age, life, size]
        self.arcs = []                 # [points, life]
        self._last_t = None
        self.sign = self._make_sign("GPU CORE", GPU_COLOR)
        self.warn_sign = self._make_sign("OVERHEAT", STRESS_COLOR)

    @staticmethod
    def _make_sign(text, color):
        f = sysfont(11, bold=True)
        txt = f.render(text, True, mix(color, (255, 255, 255), 0.35))
        board = pygame.Surface((txt.get_width() + 10, txt.get_height() + 5))
        board.fill((10, 12, 22))
        pygame.draw.rect(board, col_scale(color, 0.85), board.get_rect(), 1)
        board.blit(txt, (5, 2))
        return board

    # -- steam puffs ----------------------------------------------------------

    def _update_steam(self, dt, temp_n, util):
        rate = 1.5 + temp_n * 16 + util * 4      # puffs / second, both towers
        if dt > 0 and random.random() < rate * dt:
            dx, dy, h = random.choice(self.towers)
            self.steam.append([self.cx + dx + random.uniform(-5, 5),
                               self.cy + dy - h - 3,
                               random.uniform(2, 9),
                               -random.uniform(14, 24 + 34 * temp_n),
                               0.0, random.uniform(2.0, 3.4),
                               random.uniform(3, 7)])
        alive = []
        for p in self.steam:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[2] += 4.0 * dt                     # wind drift
            p[4] += dt
            if p[4] < p[5]:
                alive.append(p)
        self.steam = alive

    # -- one cooling tower ----------------------------------------------------

    def _tower(self, surf, t, x, base_y, h, temp_n, alarm):
        left, right = [], []
        for i in range(6):
            u = i / 5.0
            w = lerp(21, 15, u) - 6 * math.sin(u * math.pi)   # hyperboloid
            y = base_y - u * h
            left.append((x - w, y))
            right.append((x + w, y))
        pygame.draw.polygon(surf, mix((15, 18, 33), GPU_COLOR, 0.06),
                            left + right[::-1])
        pygame.draw.lines(surf, (30, 36, 60), False, left, 1)
        pygame.draw.lines(surf, (52, 60, 94), False, right, 1)
        # mouth + heat glow rising out of the throat
        rim = pygame.Rect(0, 0, 30, 9)
        rim.center = (x, base_y - h)
        pygame.draw.ellipse(surf, (8, 10, 20), rim)
        pygame.draw.ellipse(surf, col_scale(GPU_COLOR, 0.35), rim, 1)
        blit_glow(surf, rim.center, 13, gpu_temp_color(temp_n),
                  0.12 + 0.38 * temp_n)
        # red strobes when the core runs critical
        if alarm > 0.02 and math.sin(t * 10 + x) > 0:
            pygame.draw.circle(surf, STRESS_COLOR, (x, base_y - h - 5), 2)
            blit_glow(surf, (x, base_y - h - 5), 11, STRESS_COLOR, alarm)

    # -- full reactor ---------------------------------------------------------

    def draw(self, surf, t, activity, stress):
        util = activity
        temp_n = self.city.gtemp_n if self.city else 0.0
        vram_n = self.city.gvram_n if self.city else 0.0
        core_c = gpu_temp_color(temp_n)
        alarm = clamp((temp_n - 0.80) / 0.20)
        dt = 0.0 if self._last_t is None else clamp(t - self._last_t, 0.0, 0.1)
        self._last_t = t
        cx, cy = self.cx, self.cy

        # cooling towers behind the core, plus their steam
        for dx, dy, h in self.towers:
            self._tower(surf, t, cx + dx, cy + dy, h, temp_n, alarm)
        self._update_steam(dt, temp_n, util)
        for x, y, _, _, age, life, size in self.steam:
            f = 1.0 - age / life
            blit_glow(surf, (x, y), int(size + age * 7), (150, 160, 185),
                      0.20 * f * (0.35 + 0.65 * temp_n))

        # containment pad + ring wall (an open iso cylinder)
        pad = pygame.Rect(0, 0, 168, 82)
        pad.center = (cx, cy + 2)
        pygame.draw.ellipse(surf, (14, 17, 32), pad)
        pygame.draw.ellipse(surf, col_scale(GPU_COLOR, 0.28 + 0.30 * util),
                            pad, 1)
        base = pygame.Rect(0, 0, 112, 54)
        base.center = (cx, cy - 4)
        top = base.move(0, -24)
        wallc = mix((16, 19, 36), GPU_COLOR, 0.09 + 0.08 * util)
        pygame.draw.rect(surf, wallc,
                         (base.left, top.centery, base.width,
                          base.centery - top.centery))
        pygame.draw.ellipse(surf, wallc, base)
        pygame.draw.ellipse(surf, (9, 11, 23), top)             # open mouth
        blit_glow(surf, top.center, 42, core_c, 0.10 + 0.35 * util)
        pygame.draw.ellipse(surf, col_scale(GPU_COLOR, 0.40 + 0.45 * util),
                            top, 2)

        # VRAM fuel rods standing in the ring
        lit = int(round(vram_n * self.RODS))
        for i in range(self.RODS):
            a = math.tau * i / self.RODS + 0.4
            rx = cx + 40 * math.cos(a)
            ry = top.centery + 4 + 17 * math.sin(a)
            if i < lit:
                pygame.draw.line(surf, col_scale(GPU_COLOR, 0.9),
                                 (rx, ry), (rx, ry - 15), 3)
                blit_glow(surf, (rx, ry - 8), 7, GPU_COLOR, 0.5)
            else:
                pygame.draw.line(surf, (30, 27, 46), (rx, ry), (rx, ry - 15), 3)

        # plasma core: column + floating orb, pulsing with load
        pulse = 0.5 + 0.5 * math.sin(t * (1.5 + util * 9.0) + self.phase)
        core_y = cy - 62 - 4 * pulse
        r = 9 + 7 * util + 3 * pulse * util
        pygame.draw.line(surf, col_scale(core_c, 0.30 + 0.55 * util),
                         (cx, top.centery + 2), (cx, core_y), 3)
        blit_glow(surf, (cx, (top.centery + core_y) / 2), 16, core_c,
                  0.06 + 0.28 * util)
        blit_glow(surf, (cx, core_y), int(r * 3.1), core_c,
                  0.30 + 0.50 * (0.35 + 0.65 * util) * (0.6 + 0.4 * pulse))
        pygame.draw.circle(surf, col_scale(core_c, 0.55 + 0.45 * pulse),
                           (cx, int(core_y)), int(r))
        pygame.draw.circle(surf,
                           mix(core_c, (255, 255, 255), 0.45 + 0.4 * pulse),
                           (cx, int(core_y)), max(2, int(r * 0.45)))

        # charge particles orbiting the core
        n_orb = 2 + int(util * 5)
        for i in range(n_orb):
            a = t * (1.6 + util * 4.5) + i * math.tau / n_orb + self.phase
            ox = cx + math.cos(a) * (r + 15)
            oy = core_y + math.sin(a) * (r + 15) * 0.38
            pygame.draw.circle(surf, mix(core_c, (255, 255, 255), 0.5),
                               (int(ox), int(oy)), 2)
            blit_glow(surf, (ox, oy), 6, core_c, 0.5)

        # crackling arcs from the orb down to the containment rim
        self.arcs = [[pts, life - dt * 5] for pts, life in self.arcs
                     if life > dt * 5]
        if util > 0.45 and random.random() < dt * (2 + 9 * util):
            ang = random.uniform(0, math.tau)
            ax = cx + 52 * math.cos(ang)
            ay = top.centery + 23 * math.sin(ang)
            mid = ((cx + ax) / 2 + random.uniform(-9, 9),
                   (core_y + ay) / 2 + random.uniform(-9, 9))
            self.arcs.append([[(cx, core_y), mid, (ax, ay)], 1.0])
        for pts, life in self.arcs:
            pygame.draw.lines(surf, col_scale(mix(core_c, (255, 255, 255),
                                                  0.4), life), False, pts, 1)

        # critical-temperature alarm: rim strobe over the whole ring
        if alarm > 0.02 and math.sin(t * 10) > 0:
            pygame.draw.ellipse(surf, col_scale(STRESS_COLOR,
                                                0.4 + 0.6 * alarm), pad, 2)
            blit_glow(surf, top.center, 60, STRESS_COLOR, 0.45 * alarm)

        # neon site sign (flips to OVERHEAT while critical)
        sign = self.warn_sign if (alarm > 0.02 and int(t * 3) % 2) else self.sign
        sc = STRESS_COLOR if sign is self.warn_sign else GPU_COLOR
        px, py = cx + 58, cy + 12
        sw, sh = sign.get_size()
        by = py - 48
        pygame.draw.line(surf, (60, 70, 100), (px, py), (px, by + sh))
        surf.blit(sign, (px - sw // 2, by))
        blit_glow(surf, (px, by + sh // 2), sw, sc, 0.22 + 0.28 * util)

        # wet reflection of the core in the sea below the platform
        blit_glow(surf, (cx, cy + 66), 26, core_c, 0.10 + 0.22 * util)


# ----------------------------------------------------------------------------
# Roads, pods & fleets
# ----------------------------------------------------------------------------

class Path:
    """Polyline (optionally a loop) in grid coordinates; pos() walks it."""

    def __init__(self, pts, loop=False):
        self.loop = loop
        self.pts = list(pts) + ([pts[0]] if loop else [])
        self.seg = []
        self.total = 0.0
        for a, b in zip(self.pts, self.pts[1:]):
            length = math.hypot(b[0] - a[0], b[1] - a[1])
            self.seg.append((a, b, length))
            self.total += length

    def pos(self, s):
        """Distance along path -> (gx, gy, dir_gx, dir_gy)."""
        if self.loop:
            s %= self.total
        else:
            s = clamp(s, 0.0, self.total)
        for a, b, length in self.seg:
            if s <= length or (a, b, length) is self.seg[-1]:
                u = clamp(s / length) if length else 0.0
                return (lerp(a[0], b[0], u), lerp(a[1], b[1], u),
                        (b[0] - a[0]) / length, (b[1] - a[1]) / length)
            s -= length


class Pod:
    __slots__ = ("s", "speed", "phase", "trail", "emergency")

    def __init__(self, s, speed, emergency=False):
        self.s = s
        self.speed = speed
        self.phase = random.uniform(0, math.tau)
        self.trail = deque(maxlen=12)
        self.emergency = emergency


class _PodSprite:
    """One frame of one pod, ready for the depth-sorted draw pass."""

    __slots__ = ("key", "fleet", "pod", "gx", "gy", "dx", "dy")

    def __init__(self, fleet, pod, gx, gy, dx, dy):
        self.key = gx + gy + 0.9
        self.fleet = fleet
        self.pod = pod
        self.gx, self.gy, self.dx, self.dy = gx, gy, dx, dy

    def draw(self, surf, t):
        self.fleet.draw_pod(surf, t, self.pod, self.gx, self.gy,
                            self.dx, self.dy)


class Fleet:
    """Vehicles on one path; count and speed follow a metric intensity."""

    def __init__(self, path, color, metric, speed_range, min_count, max_count,
                 style="pod", trails=False):
        self.path = path
        self.color = color
        self.metric = metric
        self.speed_range = speed_range      # grid units / second
        self.min_count, self.max_count = min_count, max_count
        self.style = style
        self.trails = trails
        self.pods = []
        self.emergency_cooldown = random.uniform(2, 6)

    def _spawn(self, at_edge, emergency=False):
        s = 0.0 if (at_edge and not self.path.loop) \
            else random.uniform(0, self.path.total)
        speed = random.uniform(*self.speed_range) * (1.7 if emergency else 1.0)
        return Pod(s, speed, emergency)

    def update(self, dt, intensity, stress):
        target = int(round(self.min_count
                           + intensity * (self.max_count - self.min_count)
                           + stress * 1.5))
        while len(self.pods) < target:
            self.pods.append(self._spawn(at_edge=len(self.pods) > 2))

        # emergency pods scream through when the city is stressed
        self.emergency_cooldown -= dt
        if stress > 0.62 and self.emergency_cooldown <= 0 and self.style == "pod":
            if not any(p.emergency for p in self.pods):
                self.pods.append(self._spawn(at_edge=True, emergency=True))
            self.emergency_cooldown = random.uniform(4, 9)

        mult = 0.65 + 0.85 * intensity + 0.3 * stress
        alive = []
        for p in self.pods:
            p.s += p.speed * mult * dt
            if not self.path.loop and p.s >= self.path.total:
                if p.emergency or len(self.pods) > target:
                    continue                 # leaves the island
                p.s = 0.0
                p.trail.clear()
            alive.append(p)
        self.pods = alive

    def collect(self, out):
        for p in self.pods:
            gx, gy, dx, dy = self.path.pos(p.s)
            out.append(_PodSprite(self, p, gx, gy, dx, dy))

    def draw_pod(self, surf, t, pod, gx, gy, dx, dy):
        x, y = iso(gx, gy, 4)
        color = self.color
        if pod.emergency:
            flash = int(t * 9 + pod.phase) % 2
            color = STRESS_COLOR if flash else (70, 130, 255)
            blit_glow(surf, (x, y), 20, color, 0.9)

        if self.trails:
            pod.trail.append((x, y))
            n = len(pod.trail)
            if n > 2:
                for i, (tx, ty) in enumerate(pod.trail):
                    blit_glow(surf, (tx, ty), 6, color, (i / n) ** 2 * 0.45)

        # screen-space heading along the road
        sdx, sdy = (dx - dy) * HW, (dx + dy) * HH
        norm = math.hypot(sdx, sdy) or 1.0
        sdx, sdy = sdx / norm, sdy / norm
        half = (9 if self.style == "truck" else 6 if self.style == "pod" else 4.5)
        bob = math.sin(t * 5 + pod.phase) * 0.4
        tail = (x - sdx * half, y - sdy * half + bob)
        nose = (x + sdx * half, y + sdy * half + bob)

        # hull + neon canopy stripe + headlight
        pygame.draw.line(surf, mix((12, 14, 26), color, 0.30), tail, nose,
                         7 if self.style == "truck" else 5)
        pygame.draw.line(surf, col_scale(color, 0.95),
                         (tail[0], tail[1] - 2), (nose[0], nose[1] - 2), 2)
        if self.style == "truck":
            pygame.draw.line(surf, col_scale(color, 0.5),
                             ((tail[0] + x) / 2, (tail[1] + y) / 2 + bob),
                             (x, y + bob), 5)
        pygame.draw.circle(surf, (255, 255, 235),
                           (int(nose[0]), int(nose[1])), 1)
        blit_glow(surf, (x, y + bob), 10 if self.style != "mini" else 7,
                  color, 0.5)

        # wet-street reflection streak beneath the pod
        pygame.draw.line(surf, col_scale(color, 0.14),
                         (x, y + 5), (x, y + 13))
        blit_glow(surf, (x, y + 9), 7, color, 0.20)


def bake_road(bg, path, color):
    """Static dark asphalt band with neon edge lines, baked once."""
    pts = [iso(p[0], p[1]) for p in path.pts]
    closed = path.loop
    if closed:
        pts = pts[:-1]
    pygame.draw.lines(bg, (9, 11, 20), closed, pts, 13)
    for off in (-6, 6):
        shifted = [(x, y + off) for x, y in pts]
        pygame.draw.lines(bg, col_scale(color, 0.30), closed, shifted, 1)
    # support pillars where the highway leaves the island platform
    for a, b, length in path.seg:
        steps = max(1, int(length))
        for i in range(steps + 1):
            u = i / steps
            gx, gy = lerp(a[0], b[0], u), lerp(a[1], b[1], u)
            if not on_island(gx, gy):
                x, y = iso(gx, gy)
                pygame.draw.line(bg, (22, 27, 46), (x, y + 6), (x, y + 34), 2)
                pygame.draw.line(bg, col_scale(color, 0.18),
                                 (x, y + 34), (x, y + 44), 1)


def draw_road_flow(surf, path, color, intensity, t, direction=1):
    """Animated neon dashes streaming along the road."""
    gap = 1.5
    speed = (2.2 + 6.0 * intensity) * direction
    s = (t * speed) % gap
    c = col_scale(color, 0.30 + 0.55 * intensity)
    while s < path.total:
        gx, gy, _, _ = path.pos(s)
        gx2, gy2, _, _ = path.pos(min(s + 0.45, path.total))
        pygame.draw.line(surf, c, iso(gx, gy, 1), iso(gx2, gy2, 1), 2)
        s += gap


# ----------------------------------------------------------------------------
# Sky / weather / stress actors
# ----------------------------------------------------------------------------

class Drone:
    def __init__(self):
        self.dir = random.choice((-1, 1))
        self.x = 20 if self.dir > 0 else 960
        self.y = random.uniform(50, 130)
        self.speed = random.uniform(40, 85)
        self.phase = random.uniform(0, math.tau)

    def update(self, dt):
        self.x += self.dir * self.speed * dt

    def offscreen(self):
        return self.x < -20 or self.x > 1000

    def draw(self, surf, t):
        y = self.y + math.sin(t * 1.7 + self.phase) * 5
        pygame.draw.rect(surf, (30, 34, 48), (int(self.x - 5), int(y - 2), 10, 4),
                         border_radius=2)
        pygame.draw.line(surf, (55, 60, 80), (self.x - 8, y - 3), (self.x - 3, y - 1))
        pygame.draw.line(surf, (55, 60, 80), (self.x + 8, y - 3), (self.x + 3, y - 1))
        flash = int(t * 7 + self.phase) % 2
        c = STRESS_COLOR if flash else (70, 130, 255)
        pygame.draw.circle(surf, c, (int(self.x), int(y - 3)), 2)
        blit_glow(surf, (self.x, y - 3), 12, c, 0.8)
        beam = pygame.Surface((36, 60), pygame.SRCALPHA)
        pygame.draw.polygon(beam, (*STRESS_COLOR, 18), [(18, 0), (0, 60), (36, 60)])
        surf.blit(beam, (int(self.x - 18), int(y)))


class Rain:
    def __init__(self):
        self.drops = []

    def update(self, dt, intensity):
        want = int(intensity * 190)
        while len(self.drops) < want:
            self.drops.append([random.uniform(0, WIDTH), random.uniform(-60, HEIGHT),
                               random.uniform(420, 640)])
        if len(self.drops) > want:
            del self.drops[want:]
        for d in self.drops:
            d[1] += d[2] * dt
            d[0] -= d[2] * 0.18 * dt
            if d[1] > HEIGHT + 10:
                d[0] = random.uniform(0, WIDTH + 120)
                d[1] = random.uniform(-80, -10)

    def draw(self, surf):
        for x, y, s in self.drops:
            f = s / 640
            pygame.draw.line(surf, (int(58 * f), int(78 * f), int(130 * f)),
                             (x, y), (x - 2.4, y - 13))


class Lightning:
    def __init__(self):
        self.flash = 0.0
        self.bolt = []
        self.cooldown = 3.0

    def update(self, dt, stress):
        self.flash = max(0.0, self.flash - dt * 3.2)
        self.cooldown -= dt
        if stress > 0.72 and self.cooldown <= 0 and random.random() < dt * 0.6:
            self.trigger()

    def trigger(self):
        self.flash = 1.0
        self.cooldown = random.uniform(2.5, 7.0)
        x = random.uniform(150, 850)
        y = 20
        self.bolt = [(x, y)]
        while y < 320:
            y += random.uniform(18, 40)
            x += random.uniform(-26, 26)
            self.bolt.append((x, y))

    def draw(self, surf):
        if self.flash <= 0:
            return
        overlay = pygame.Surface((WIDTH, HEIGHT))
        overlay.fill(col_scale((90, 105, 160), self.flash * 0.45))
        surf.blit(overlay, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
        if self.flash > 0.55 and len(self.bolt) > 1:
            pygame.draw.lines(surf, (200, 215, 255), False, self.bolt, 3)
            pygame.draw.lines(surf, (255, 255, 255), False, self.bolt, 1)
            for p in self.bolt[::2]:
                blit_glow(surf, p, 16, (150, 170, 255), self.flash * 0.8)


class Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "color", "size")

    def __init__(self, x, y, vx, vy, life, color, size=2):
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.life = self.max_life = life
        self.color = color
        self.size = size


# ----------------------------------------------------------------------------
# The city
# ----------------------------------------------------------------------------

class City:
    def __init__(self):
        random.seed(7)   # stable, hand-tuned layout

        # -- roads: two expressways cross the island, loops wrap districts --
        self.dl_path = Path([(-3.0, 10.5), (23.0, 10.5)])          # download
        self.ul_path = Path([(10.7, 23.0), (10.7, -3.0)])          # upload
        self.ring_path = Path([(0.6, 0.6), (19.4, 0.6),
                               (19.4, 19.4), (0.6, 19.4)], loop=True)
        self.cpu_loop = Path([(11.0, 0.8), (17.8, 0.8),
                              (17.8, 8.6), (11.0, 8.6)], loop=True)
        self.disk_loop = Path([(1.0, 11.4), (9.6, 11.4),
                               (9.6, 18.8), (1.0, 18.8)], loop=True)
        # energy conduit: reactor platform -> city (flow runs toward town)
        self.conduit_path = Path([(25.6, 16.6), (20.1, 13.0)])

        scene = []

        # RAM memory spires - back-left quarter, tall and tight
        ram_spots = [(3.6, 1.6), (5.9, 1.8), (8.2, 1.6),
                     (3.8, 4.2), (6.1, 4.4), (8.4, 4.2),
                     (4.0, 6.6), (6.3, 6.8), (8.2, 6.6)]
        for i, (gx, gy) in enumerate(ram_spots):
            h = random.randint(110, 190) + (22 if i == 4 else 0)
            scene.append(IsoBuilding(gx, gy, 1.8, 1.8, h, RAM_COLOR, "ram",
                                     "RAM" if i == 1 else None))

        # CPU processing towers - back-right quarter
        cpu_spots = [(11.8, 1.6), (14.1, 1.8), (16.4, 1.6),
                     (12.0, 4.2), (14.3, 4.4), (16.6, 4.2),
                     (12.2, 6.6), (14.5, 6.8), (16.4, 6.6)]
        for i, (gx, gy) in enumerate(cpu_spots):
            h = random.randint(60, 132)
            scene.append(IsoBuilding(gx, gy, 1.8, 1.8, h, CPU_COLOR, "cpu",
                                     "CPU" if i == 1 else None))

        # Disk storage docks - front-left quarter
        for gx, gy in ((2.0, 12.0), (5.3, 12.2), (2.3, 15.4), (5.7, 15.7)):
            scene.append(IsoWarehouse(gx, gy))
        scene.append(IsoBuilding(8.1, 12.3, 1.4, 1.4, 56, DISK_COLOR,
                                 "disk", "DISK"))
        scene.append(Crane(9.0, 15.0))
        scene.append(Crane(4.9, 14.5, height=76, jib=56, flip=True))

        # Data quarter - front-right, mixed blue/purple blocks by the ramps
        for gx, gy, h, c, m, sg in (
                (12.2, 12.0, 74, DOWN_COLOR, "dl", "DOWN"),
                (14.6, 12.2, 52, UP_COLOR, "ul", None),
                (16.8, 12.0, 66, DOWN_COLOR, "dl", None),
                (12.4, 14.6, 46, UP_COLOR, "ul", "UP"),
                (14.8, 14.8, 88, UP_COLOR, "ul", None),
                (17.0, 14.6, 40, DOWN_COLOR, "dl", None),
                (13.0, 17.0, 58, DOWN_COLOR, "dl", None),
                (15.6, 17.2, 44, UP_COLOR, "ul", None)):
            scene.append(IsoBuilding(gx, gy, 1.6, 1.6, h, c, m, sg))

        # streetlights hugging the expressways
        for gx in (1.5, 4.5, 7.5, 13.5, 16.5):
            scene.append(Streetlight(gx, 9.6, DOWN_COLOR, "dl"))
        for gy in (2.5, 5.5, 12.5, 15.5, 18.5):
            scene.append(Streetlight(11.7, gy, UP_COLOR, "ul"))

        # GPU fusion reactor on its satellite platform (front-right)
        self.reactor = Reactor()
        self.reactor.city = self
        scene.append(self.reactor)

        self.scene = sorted(scene, key=lambda o: o.key)

        self.fleets = [
            Fleet(self.dl_path, DOWN_COLOR, "dl", (5.5, 10.0), 1, 10,
                  trails=True),
            Fleet(self.ul_path, UP_COLOR, "ul", (5.0, 9.0), 1, 9,
                  trails=True),
            Fleet(self.cpu_loop, CPU_COLOR, "cpu", (2.5, 5.0), 1, 9,
                  style="mini"),
            Fleet(self.disk_loop, DISK_COLOR, "disk", (1.3, 2.6), 0, 6,
                  style="truck"),
            Fleet(self.ring_path, (150, 190, 235), "st", (2.0, 3.5), 1, 3,
                  style="mini"),
        ]

        self.background = self._build_background()
        self.vignette = self._build_vignette()
        random.seed()    # back to true randomness for live effects

        self.particles = []
        self.drones = []
        self.rain = Rain()
        self.lightning = Lightning()

        # smoothed display metrics
        self.cpu = self.ram = 0.0
        self.dl = self.ul = self.dr = self.dw = 0.0
        self.gpu = self.gtemp = self.gvu = self.gvt = 0.0
        self.gtemp_n = self.gvram_n = 0.0
        self.gpu_available = True      # App flips this off if no NVIDIA GPU
        self.stress = 0.0
        self.spike = 0.0
        self.n = dict(cpu=0.0, ram=0.0, dl=0.0, ul=0.0, disk=0.0, gpu=0.0)

    # -- static art ----------------------------------------------------------

    def _build_background(self):
        bg = pygame.Surface((WIDTH, HEIGHT))
        for y in range(HEIGHT):
            bg.fill(mix(COL_BG_TOP, COL_BG_BOT, y / HEIGHT), (0, y, WIDTH, 1))
        # stars
        for _ in range(140):
            x = random.randint(0, WIDTH - 1)
            y = random.randint(0, 260)
            b = random.randint(40, 130)
            bg.set_at((x, y), (b, b, min(255, b + 30)))

        # distant silhouette skyline peeking behind the island's back edges
        x = 90
        while x < 910:
            w = random.randint(20, 46)
            h = random.randint(26, 96)
            base = 152 + abs(x + w / 2 - ISO_OX) * 0.5
            pygame.draw.rect(bg, (13, 16, 33), (x, int(base - h), w, h))
            x += w + random.randint(2, 12)

        # the island platform ------------------------------------------------
        PT, PR = iso(0, 0), iso(GRID_N, 0)
        PB, PL = iso(GRID_N, GRID_N), iso(0, GRID_N)
        SD = PLAT_SIDE
        # slab sides
        pygame.draw.polygon(bg, (8, 10, 20),
                            [PL, PB, (PB[0], PB[1] + SD), (PL[0], PL[1] + SD)])
        pygame.draw.polygon(bg, (11, 13, 25),
                            [PB, PR, (PR[0], PR[1] + SD), (PB[0], PB[1] + SD)])
        # slab top
        pygame.draw.polygon(bg, (13, 16, 30), [PT, PR, PB, PL])
        for i in range(0, GRID_N + 1, 2):
            pygame.draw.line(bg, (20, 26, 48), iso(i, 0), iso(i, GRID_N))
            pygame.draw.line(bg, (20, 26, 48), iso(0, i), iso(GRID_N, i))
        pygame.draw.lines(bg, (52, 70, 116), True, [PT, PR, PB, PL], 1)
        # neon strips along the slab edge (cyan left / orange right)
        pygame.draw.line(bg, col_scale(RAM_COLOR, 0.35), PL, PB)
        pygame.draw.line(bg, col_scale(CPU_COLOR, 0.35), PB, PR)
        pygame.draw.line(bg, col_scale(RAM_COLOR, 0.14),
                         (PL[0], PL[1] + SD), (PB[0], PB[1] + SD))
        pygame.draw.line(bg, col_scale(CPU_COLOR, 0.14),
                         (PB[0], PB[1] + SD), (PR[0], PR[1] + SD))

        # district ground tints baked into the slab
        blit_glow(bg, iso(6, 4), 150, RAM_COLOR, 0.10)
        blit_glow(bg, iso(14, 4), 150, CPU_COLOR, 0.10)
        blit_glow(bg, iso(5, 15), 130, DISK_COLOR, 0.08)
        blit_glow(bg, iso(15, 15), 130, mix(DOWN_COLOR, UP_COLOR, 0.5), 0.08)

        # roads (dark beds + neon edges + highway pillars off the slab)
        bake_road(bg, self.ring_path, (100, 130, 180))
        bake_road(bg, self.cpu_loop, CPU_COLOR)
        bake_road(bg, self.disk_loop, DISK_COLOR)
        bake_road(bg, self.dl_path, DOWN_COLOR)
        bake_road(bg, self.ul_path, UP_COLOR)

        # wet reflection plane under the island
        for i, yy in enumerate(range(int(PB[1]) + SD + 6, HEIGHT - 6, 7)):
            f = max(0.0, 1.0 - i / 22)
            pygame.draw.line(bg, mix((11, 14, 32), (20, 27, 54), f),
                             (PL[0] + i * 6, yy), (PR[0] - i * 6, yy))

        # GPU reactor satellite platform + energy conduit (front-right) -------
        bake_road(bg, self.conduit_path, GPU_COLOR)
        RT, RR = iso(24, 15), iso(30, 15)
        RB2, RL2 = iso(30, 21), iso(24, 21)
        SD2 = 18
        pygame.draw.polygon(bg, (8, 10, 20),
                            [RL2, RB2, (RB2[0], RB2[1] + SD2),
                             (RL2[0], RL2[1] + SD2)])
        pygame.draw.polygon(bg, (11, 13, 25),
                            [RB2, RR, (RR[0], RR[1] + SD2),
                             (RB2[0], RB2[1] + SD2)])
        pygame.draw.polygon(bg, (13, 16, 30), [RT, RR, RB2, RL2])
        for i in (2, 4):
            pygame.draw.line(bg, (20, 26, 48), iso(24 + i, 15), iso(24 + i, 21))
            pygame.draw.line(bg, (20, 26, 48), iso(24, 15 + i), iso(30, 15 + i))
        pygame.draw.lines(bg, (52, 70, 116), True, [RT, RR, RB2, RL2], 1)
        pygame.draw.line(bg, col_scale(GPU_COLOR, 0.35), RL2, RB2)
        pygame.draw.line(bg, col_scale(GPU_COLOR, 0.35), RB2, RR)
        pygame.draw.line(bg, col_scale(GPU_COLOR, 0.14),
                         (RL2[0], RL2[1] + SD2), (RB2[0], RB2[1] + SD2))
        pygame.draw.line(bg, col_scale(GPU_COLOR, 0.14),
                         (RB2[0], RB2[1] + SD2), (RR[0], RR[1] + SD2))
        blit_glow(bg, iso(27, 18), 110, GPU_COLOR, 0.10)
        blit_glow(bg, (RB2[0], RB2[1] + 40), 120, GPU_COLOR, 0.05)

        blit_glow(bg, (PB[0], PB[1] + 60), 190, RAM_COLOR, 0.05)
        blit_glow(bg, (PB[0] - 180, PB[1] + 40), 150, DISK_COLOR, 0.04)
        blit_glow(bg, (PB[0] + 180, PB[1] + 40), 150, CPU_COLOR, 0.05)
        blit_glow(bg, (PB[0], PB[1] + 30), 260, (40, 60, 130), 0.18)
        return bg

    def _build_vignette(self):
        v = pygame.Surface((WIDTH, HEIGHT))
        depth = 90
        for i in range(depth):
            f = ((depth - i) / depth) ** 2
            c = col_scale(STRESS_COLOR, f * 0.40)
            pygame.draw.rect(v, c, (i, i, WIDTH - 2 * i, HEIGHT - 2 * i), 1)
        return v

    # -- simulation ----------------------------------------------------------

    def trigger_stress(self):
        self.spike = random.uniform(0.55, 1.0)

    def update(self, dt, t, raw):
        cpu, ram, dl, ul, dr, dw, gpu, gtemp, gvu, gvt = raw
        s = clamp(dt * 3.2)          # smoothing factor
        self.cpu = lerp(self.cpu, cpu, s)
        self.ram = lerp(self.ram, ram, s)
        self.dl = lerp(self.dl, dl, s)
        self.ul = lerp(self.ul, ul, s)
        self.dr = lerp(self.dr, dr, s)
        self.dw = lerp(self.dw, dw, s)
        self.gpu = lerp(self.gpu, gpu, s)
        self.gtemp = lerp(self.gtemp, gtemp, s)
        self.gvu = lerp(self.gvu, gvu, s)
        self.gvt = gvt               # capacity: no smoothing needed

        self.spike = max(0.0, self.spike - dt * 0.075)

        cpu_n = clamp(self.cpu / 100 + self.spike * 0.5)
        ram_n = clamp(self.ram / 100 + self.spike * 0.3)
        dl_n = clamp(soft_norm(self.dl, 2.5 * MB) + self.spike * 0.45)
        ul_n = clamp(soft_norm(self.ul, 1.2 * MB) + self.spike * 0.45)
        disk_n = clamp(soft_norm(self.dr + self.dw, 24 * MB) + self.spike * 0.45)
        gpu_n = clamp(self.gpu / 100 + self.spike * 0.4)
        # ~30 C reads as cold, ~92 C as critical
        self.gtemp_n = clamp((self.gtemp - 30.0) / 62.0 + self.spike * 0.25)
        self.gvram_n = clamp(self.gvu / self.gvt) if self.gvt > 0 else 0.0
        self.n = dict(cpu=cpu_n, ram=ram_n, dl=dl_n, ul=ul_n, disk=disk_n,
                      gpu=gpu_n)

        stress_target = clamp(0.40 * cpu_n + 0.22 * ram_n
                              + 0.20 * max(gpu_n, self.gtemp_n)
                              + 0.14 * disk_n
                              + 0.10 * max(dl_n, ul_n) + self.spike * 0.8)
        self.stress = lerp(self.stress, stress_target, clamp(dt * 1.6))
        st = self.stress

        for fleet in self.fleets:
            inten = st if fleet.metric == "st" else self.n[fleet.metric]
            fleet.update(dt, inten, st)

        # data sparks racing along the expressways
        if random.random() < dl_n * dt * 45:
            dx, dy = 0.894, 0.447
            speed = random.uniform(280, 500)
            x, y = iso(-2.8, 10.5, 4)
            self.particles.append(Particle(
                x, y, dx * speed, dy * speed, 1.8, DOWN_COLOR,
                random.choice((1, 2, 2))))
        if random.random() < ul_n * dt * 30:
            dx, dy = 0.894, -0.447
            speed = random.uniform(260, 460)
            x, y = iso(10.7, 22.5, 4)
            self.particles.append(Particle(
                x, y, dx * speed, dy * speed, 1.8, UP_COLOR, 1))
        alive = []
        for p in self.particles:
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.life -= dt
            if p.life > 0 and -20 < p.x < 990 and -20 < p.y < HEIGHT:
                alive.append(p)
        self.particles = alive

        # stress actors
        want_drones = int(clamp((st - 0.45) / 0.55) * 4)
        self.drones = [d for d in self.drones if not d.offscreen()]
        while len(self.drones) < want_drones:
            self.drones.append(Drone())
        for d in self.drones:
            d.update(dt)
        self.rain.update(dt, clamp((st - 0.48) / 0.5))
        self.lightning.update(dt, st)

    # -- rendering -----------------------------------------------------------

    def draw(self, surf, t):
        n, st = self.n, self.stress
        surf.blit(self.background, (0, 0))

        # animated traffic-flow dashes on every road
        draw_road_flow(surf, self.dl_path, DOWN_COLOR, n["dl"], t)
        draw_road_flow(surf, self.ul_path, UP_COLOR, n["ul"], t)
        draw_road_flow(surf, self.cpu_loop, CPU_COLOR, n["cpu"] * 0.8, t)
        draw_road_flow(surf, self.disk_loop, DISK_COLOR, n["disk"] * 0.8, t)
        # reactor power surging along the conduit into the city
        draw_road_flow(surf, self.conduit_path, GPU_COLOR, n["gpu"], t)

        # central interchange pulse where the two expressways cross
        beat = 0.5 + 0.5 * math.sin(t * (2 + n["cpu"] * 5))
        blit_glow(surf, iso(10.7, 10.5), 18, mix(DOWN_COLOR, UP_COLOR, 0.5),
                  0.15 + 0.45 * max(n["dl"], n["ul"]) * beat)

        # platform edge turns into a red warning ring under stress
        ring = clamp((st - 0.45) / 0.55)
        if ring > 0.03:
            pulse = 0.6 + 0.4 * math.sin(t * 4)
            corners = [iso(0, 0), iso(GRID_N, 0), iso(GRID_N, GRID_N),
                       iso(0, GRID_N)]
            pygame.draw.lines(surf, col_scale(STRESS_COLOR, ring * pulse * 0.8),
                              True, corners, 2)
            for cpt in corners:
                blit_glow(surf, cpt, 18, STRESS_COLOR, ring * pulse * 0.5)

        # depth-sorted scene: back objects first, front objects last
        sprites = list(self.scene)
        for fleet in self.fleets:
            fleet.collect(sprites)
        sprites.sort(key=lambda o: o.key)
        for obj in sprites:
            if isinstance(obj, _PodSprite):
                obj.draw(surf, t)
            else:
                obj.draw(surf, t, n[obj.metric], st)

        # airborne data sparks
        for p in self.particles:
            f = clamp(p.life / p.max_life)
            pygame.draw.circle(surf, col_scale(p.color, 0.4 + 0.6 * f),
                               (int(p.x), int(p.y)), p.size)
            if p.size > 1:
                blit_glow(surf, (p.x, p.y), 6, p.color, 0.5 * f)

        for d in self.drones:
            d.draw(surf, t)
        self.rain.draw(surf)
        self.lightning.draw(surf)

        # red stress vignette
        red = clamp((st - 0.55) / 0.45)
        if red > 0.02:
            pulse = 0.72 + 0.28 * math.sin(t * 3.4)
            tinted = self.vignette.copy()
            tinted.fill(col_scale((255, 255, 255), red * pulse),
                        special_flags=pygame.BLEND_RGB_MULT)
            surf.blit(tinted, (0, 0), special_flags=pygame.BLEND_RGB_ADD)


# ----------------------------------------------------------------------------
# HUD
# ----------------------------------------------------------------------------

class HUD:
    def __init__(self, rect):
        self.rect = rect
        self.f_title = sysfont(22, bold=True)
        self.f_sub = sysfont(13)
        self.f_label = sysfont(14, bold=True)
        self.f_value = sysfont(16, bold=True)
        self.f_big = sysfont(16, bold=True)

    def draw(self, screen, t, city, live_mode, paused, fps):
        w, h = self.rect.size
        p = pygame.Surface((w, h), pygame.SRCALPHA)
        p.fill((7, 11, 24, 242))
        pygame.draw.rect(p, (*COL_PANEL_EDGE, 130), (0, 0, w, h), 1)

        # corner brackets
        bl = 16
        for cx, cy, dx, dy in ((0, 0, 1, 1), (w - 1, 0, -1, 1),
                               (0, h - 1, 1, -1), (w - 1, h - 1, -1, -1)):
            pygame.draw.line(p, (*COL_PANEL_EDGE, 255), (cx, cy), (cx + dx * bl, cy), 2)
            pygame.draw.line(p, (*COL_PANEL_EDGE, 255), (cx, cy), (cx, cy + dy * bl), 2)

        # header
        title = self.f_title.render("CITY PULSE", True, (225, 245, 255))
        p.blit(title, (18, 20))
        sub = self.f_sub.render("SYSTEM TELEMETRY UPLINK", True, COL_TEXT_DIM)
        p.blit(sub, (18, 46))
        pygame.draw.line(p, (*COL_PANEL_EDGE, 170), (18, 62), (w - 18, 62))
        sweep = 18 + ((t * 60) % (w - 36))
        pygame.draw.line(p, (255, 255, 255, 200), (sweep, 61), (sweep + 14, 61), 2)

        # mode line
        blink = math.sin(t * 4) > 0
        mode_col = (90, 255, 140) if live_mode else (255, 210, 80)
        mode_txt = "LIVE TELEMETRY" if live_mode else "DEMO SIGNAL"
        if blink:
            pygame.draw.circle(p, mode_col, (24, 80), 3)
        p.blit(self.f_sub.render(mode_txt, True, mode_col), (34, 74))
        fps_s = self.f_sub.render(f"{fps:3.0f} FPS", True, COL_TEXT_DIM)
        p.blit(fps_s, (w - 18 - fps_s.get_width(), 74))

        # metric rows
        n = city.n
        gpu_ok = city.gpu_available or not live_mode
        gb = KB * MB
        rows = [
            ("CPU LOAD",  f"{city.cpu:4.0f} %",      n["cpu"],  CPU_COLOR),
            ("MEMORY",    f"{city.ram:4.0f} %",      n["ram"],  RAM_COLOR),
            ("GPU LOAD",  f"{city.gpu:4.0f} %" if gpu_ok else "  --",
             n["gpu"] if gpu_ok else 0.0,                       GPU_COLOR),
            ("GPU CORE",  f"{city.gtemp:4.0f} °C" if gpu_ok else "  --",
             city.gtemp_n if gpu_ok else 0.0,
             gpu_temp_color(city.gtemp_n)),
            ("GPU VRAM",
             f"{city.gvu / gb:4.1f}/{city.gvt / gb:.1f} GB" if gpu_ok
             else "  --",
             city.gvram_n if gpu_ok else 0.0,                   GPU_COLOR),
            ("DOWNLINK",  fmt_speed(city.dl),        n["dl"],   DOWN_COLOR),
            ("UPLINK",    fmt_speed(city.ul),        n["ul"],   UP_COLOR),
            ("DISK READ", fmt_speed(city.dr),        n["disk"], DISK_COLOR),
            ("DISK WRITE", fmt_speed(city.dw),
             clamp(soft_norm(city.dw, 20 * MB)),                DISK_COLOR),
        ]
        y = 104
        for label, value, frac, color in rows:
            self._row(p, t, y, w, label, value, frac, color)
            y += 52

        # stress meter -------------------------------------------------------
        y += 6
        p.blit(self.f_label.render("SYSTEM STRESS", True,
                                   mix((235, 244, 255), STRESS_COLOR, 0.30)),
               (18, y))
        st = city.stress
        status, scol = self._status(st)
        stxt = self.f_big.render(status, True, scol)
        if st < 0.75 or math.sin(t * 8) > -0.2:
            p.blit(stxt, (w - 18 - stxt.get_width(), y - 2))
        y += 22
        segs = 22
        seg_w = (w - 36 - (segs - 1) * 3) / segs
        lit = int(round(st * segs))
        for i in range(segs):
            f = i / (segs - 1)
            color = mix((80, 255, 140), (255, 210, 60), clamp(f / 0.6)) if f < 0.6 \
                else mix((255, 210, 60), STRESS_COLOR, clamp((f - 0.6) / 0.4))
            x = 18 + i * (seg_w + 3)
            r = pygame.Rect(int(x), y, int(seg_w), 14)
            if i < lit:
                hot = st > 0.78 and i > segs * 0.7 and math.sin(t * 9) > 0
                pygame.draw.rect(p, (255, 255, 255) if hot else color, r)
            else:
                pygame.draw.rect(p, (*col_scale(color, 0.18), 255), r)
                pygame.draw.rect(p, (*col_scale(color, 0.35), 255), r, 1)
        y += 26
        p.blit(self.f_sub.render(f"STRESS INDEX {st * 100:3.0f}", True, COL_TEXT_DIM),
               (18, y))

        # controls ------------------------------------------------------------
        y = h - 118
        pygame.draw.line(p, (*COL_PANEL_EDGE, 90), (18, y), (w - 18, y))
        y += 10
        for key, action in (("ESC", "SHUT DOWN"), ("SPACE", "PAUSE / RESUME"),
                            ("M", "LIVE / DEMO FEED"), ("R", "STRESS SURGE TEST")):
            k = self.f_sub.render(key, True, (165, 225, 255))
            pygame.draw.rect(p, (30, 52, 80, 220), (18, y - 2, 54, 18), border_radius=3)
            pygame.draw.rect(p, (*COL_PANEL_EDGE, 120), (18, y - 2, 54, 18), 1,
                             border_radius=3)
            p.blit(k, (18 + 27 - k.get_width() // 2, y))
            p.blit(self.f_sub.render(action, True, COL_TEXT_DIM), (82, y))
            y += 25

        screen.blit(p, self.rect.topleft)
        blit_glow(screen, self.rect.midtop, 60, COL_PANEL_EDGE, 0.10)

        if paused:
            self._pause_overlay(screen, t)

    def _row(self, p, t, y, w, label, value, frac, color):
        lab_col = mix((235, 244, 255), color, 0.30)
        p.blit(self.f_label.render(label, True, lab_col), (18, y))
        val = self.f_value.render(value, True, (245, 250, 255))
        p.blit(val, (w - 18 - val.get_width(), y - 2))
        bar = pygame.Rect(18, y + 21, w - 36, 9)
        pygame.draw.rect(p, (16, 22, 40, 255), bar, border_radius=4)
        pygame.draw.rect(p, (*col_scale(color, 0.35), 255), bar, 1, border_radius=4)
        fill_w = int(bar.width * clamp(frac))
        if fill_w > 2:
            fill = pygame.Rect(bar.x, bar.y, fill_w, bar.height)
            pygame.draw.rect(p, (*col_scale(color, 0.75), 255), fill, border_radius=4)
            pygame.draw.rect(p, (*color, 255),
                             (fill.x, fill.y + 1, fill.width, 3), border_radius=2)
            # glowing tip
            tipx = bar.x + fill_w
            pygame.draw.circle(p, (*color, 255), (tipx, bar.centery), 3)
            pygame.draw.circle(p, (255, 255, 255, 180), (tipx, bar.centery), 1)
        # ticks
        for i in range(1, 4):
            tx = bar.x + bar.width * i // 4
            pygame.draw.line(p, (0, 0, 0, 120), (tx, bar.y + 1), (tx, bar.bottom - 2))

    @staticmethod
    def _status(st):
        if st < 0.25:
            return "CALM", (90, 255, 140)
        if st < 0.5:
            return "STEADY", (140, 230, 255)
        if st < 0.75:
            return "BUSY", (255, 210, 60)
        return "OVERLOAD", STRESS_COLOR

    def _pause_overlay(self, screen, t):
        dim = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        dim.fill((4, 6, 14, 130))
        screen.blit(dim, (0, 0))
        txt = self.f_title.render("· · ·  SIMULATION PAUSED  · · ·", True,
                                  (200, 230, 255))
        x = WIDTH // 2 - txt.get_width() // 2
        screen.blit(txt, (x, HEIGHT // 2 - 14))
        pygame.draw.line(screen, COL_PANEL_EDGE, (x - 30, HEIGHT // 2 + 16),
                         (x + txt.get_width() + 30, HEIGHT // 2 + 16))


# ----------------------------------------------------------------------------
# Application
# ----------------------------------------------------------------------------

DISTRICT_LABELS = [
    ("MEMORY SPIRES · RAM", (400, 14), RAM_COLOR),
    ("PROCESSING GRID · CPU", (716, 124), CPU_COLOR),
    ("STORAGE DOCKS · DISK", (58, 330), DISK_COLOR),
    ("DOWNLINK EXPRESSWAY", (56, 214), DOWN_COLOR),
    ("UPLINK EXPRESSWAY", (128, 546), UP_COLOR),
    ("FUSION REACTOR · GPU", (836, 592), GPU_COLOR),
]


class App:
    def __init__(self, smoke_dir=None):
        self.smoke_dir = smoke_dir
        if smoke_dir:
            os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        pygame.init()
        pygame.display.set_caption("City Pulse Simulator")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_icon(self._make_icon())
        self.clock = pygame.time.Clock()
        self.city = City()
        self.hud = HUD(HUD_RECT)
        self.metrics = MetricsProvider()
        self.gpu_metrics = GpuMetrics()
        self.city.gpu_available = self.gpu_metrics.available
        self.demo = DemoMetrics()
        self.live_mode = self.metrics.available and smoke_dir is None
        if not self.metrics.available:
            print("psutil unavailable - running in demo mode. "
                  "Install it with: pip install psutil")
        if not self.gpu_metrics.available:
            print("No NVIDIA GPU telemetry found - the reactor idles cold "
                  "in live mode. Install it with: pip install nvidia-ml-py")
        self.f_label = sysfont(11, bold=True)
        self.paused = False
        self.t = 0.0

    @staticmethod
    def _make_icon():
        icon = pygame.Surface((32, 32))
        icon.fill((8, 10, 24))
        for x, h, c in ((3, 16, CPU_COLOR), (10, 24, RAM_COLOR), (18, 12, DISK_COLOR),
                        (24, 20, UP_COLOR)):
            pygame.draw.rect(icon, c, (x, 30 - h, 6, h))
        pygame.draw.line(icon, DOWN_COLOR, (0, 30), (32, 30), 2)
        return icon

    def run(self):
        frame = 0
        running = True
        while running:
            if self.smoke_dir:
                dt = 1 / 60
                self.clock.tick()
            else:
                dt = min(self.clock.tick(FPS) / 1000.0, 0.05)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key == pygame.K_SPACE:
                        self.paused = not self.paused
                    elif event.key == pygame.K_m:
                        self.live_mode = not self.live_mode
                        if self.live_mode and not self.metrics.available:
                            self.live_mode = False
                    elif event.key == pygame.K_r:
                        self.city.trigger_stress()

            if not self.paused:
                self.t += dt
                if self.live_mode:
                    self.metrics.update(dt)
                    self.gpu_metrics.update(dt)
                    g = self.gpu_metrics
                    raw = (self.metrics.cpu, self.metrics.ram, self.metrics.dl,
                           self.metrics.ul, self.metrics.disk_r, self.metrics.disk_w,
                           g.util, g.temp, g.vram_used, g.vram_total)
                else:
                    raw = self.demo.sample(self.t)
                self.city.update(dt, self.t, raw)

            self.city.draw(self.screen, self.t)
            for text, pos, color in DISTRICT_LABELS:
                label = self.f_label.render(text, True, col_scale(color, 0.85))
                self.screen.blit(label, pos)
                pygame.draw.line(self.screen, col_scale(color, 0.4),
                                 (pos[0], pos[1] + 12),
                                 (pos[0] + label.get_width(), pos[1] + 12))
            self.hud.draw(self.screen, self.t, self.city, self.live_mode,
                          self.paused, self.clock.get_fps())
            pygame.display.flip()

            if self.smoke_dir:
                frame += 1
                if frame == 240:
                    pygame.image.save(self.screen,
                                      os.path.join(self.smoke_dir, "shot_calm.png"))
                    self.city.trigger_stress()
                    self.city.lightning.trigger()
                elif frame == 420:
                    pygame.image.save(self.screen,
                                      os.path.join(self.smoke_dir, "shot_stress.png"))
                    print("SMOKE OK")
                    running = False

        pygame.quit()


def main():
    smoke_dir = None
    if "--smoke" in sys.argv:
        i = sys.argv.index("--smoke")
        smoke_dir = sys.argv[i + 1] if len(sys.argv) > i + 1 else "."
        os.makedirs(smoke_dir, exist_ok=True)
    App(smoke_dir=smoke_dir).run()


if __name__ == "__main__":
    main()
