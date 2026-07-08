"""City Pulse — the procedural isometric city, ported ~as-is from the
standalone CityPulseSimulator. Only the math/color/glow/font/iso-projection
plumbing was swapped for the shared implementations; the buildings, roads,
fleets, weather and stress logic are unchanged."""
import math
import random
from collections import deque

import pygame

from shared.renderer.fonts import sysfont
from shared.renderer.glow import blit_glow
from shared.renderer.iso import IsoGrid
from shared.utils.color import col_scale, mix
from shared.utils.mathutil import clamp, lerp, soft_norm

WIDTH, HEIGHT = 1280, 800

KB = 1024.0
MB = KB * 1024.0

COL_BG_TOP = (5, 7, 18)
COL_BG_BOT = (11, 14, 32)

CPU_COLOR = (255, 122, 24)
RAM_COLOR = (0, 224, 255)
DOWN_COLOR = (52, 130, 255)
UP_COLOR = (178, 74, 255)
DISK_COLOR = (128, 255, 64)
STRESS_COLOR = (255, 46, 64)

TILE_W, TILE_H = 44, 22
HW, HH = TILE_W // 2, TILE_H // 2
GRID_N = 20
ISO_OX, ISO_OY = 496, 150
PLAT_SIDE = 26

_GRID = IsoGrid(ISO_OX, ISO_OY, HW, HH)
iso = _GRID.project
box_points = _GRID.box_points


def on_island(gx, gy):
    return 0.0 <= gx <= GRID_N and 0.0 <= gy <= GRID_N


def fmt_speed(bps):
    if bps >= MB:
        return f"{bps / MB:5.1f} MB/s"
    if bps >= KB:
        return f"{bps / KB:5.0f} KB/s"
    return f"{bps:5.0f}  B/s"


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
        self.key = gx + gy + w + d
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

        pygame.draw.polygon(surf, (7, 9, 17), [
            self.D, self.C, (self.C[0] - 18, self.C[1] + 9),
            (self.D[0] - 18, self.D[1] + 9)])

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

        if self.metric == "ram" and activity > 0.12:
            span = self.h - 8
            v = (t * (24 + 70 * activity) + self.phase * 40) % span
            pa = (self.B[0], self.B[1] - 4 - v)
            pb = (self.C[0], self.C[1] - 4 - v)
            pygame.draw.line(surf, col_scale(c, 0.3 + 0.5 * activity), pa, pb)
            blit_glow(surf, ((pa[0] + pb[0]) // 2, (pa[1] + pb[1]) // 2),
                      8, c, 0.4 * activity)

        if glowf > 0.15:
            fx, fy = self.C
            pygame.draw.line(surf, col_scale(c, 0.10 + 0.18 * glowf),
                             (fx, fy + 2), (fx, fy + 9 + int(8 * glowf)))
            blit_glow(surf, (fx, fy + 6), 10, c, 0.16 * glowf)

        if self.antenna:
            ax, ay = self.roof_c
            pygame.draw.line(surf, col_scale(c, 0.5), (ax, ay), (ax, ay - 13))
            beat = 0.5 + 0.5 * math.sin(t * 2.4 + self.phase)
            if beat > 0.55:
                bc = STRESS_COLOR if (stress > 0.6 or is_cpu) else c
                pygame.draw.circle(surf, bc, (ax, ay - 14), 2)
                blit_glow(surf, (ax, ay - 14), 8, bc, beat * 0.8)

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
        self.door = []
        for u in (0.30, 0.72):
            x = lerp(self.B[0], self.C[0], u)
            y = lerp(self.B[1], self.C[1], u)
            self.door.append((x, y))
        self.door_h = h - 8
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

        for (_, _, cc, cd, cat, cbt, cct, cdt) in self.crates:
            pygame.draw.polygon(surf, mix((13, 17, 22), c, 0.10),
                                [cdt, cct, cc, cd])
            pygame.draw.polygon(surf, mix((16, 21, 28), c, 0.16),
                                [cat, cbt, cct, cdt])
            pygame.draw.lines(surf, col_scale(c, 0.4), True,
                              [cat, cbt, cct, cdt], 1)

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
        self.speed_range = speed_range
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
                    continue
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

        sdx, sdy = (dx - dy) * HW, (dx + dy) * HH
        norm = math.hypot(sdx, sdy) or 1.0
        sdx, sdy = sdx / norm, sdy / norm
        half = (9 if self.style == "truck" else 6 if self.style == "pod" else 4.5)
        bob = math.sin(t * 5 + pod.phase) * 0.4
        tail = (x - sdx * half, y - sdy * half + bob)
        nose = (x + sdx * half, y + sdy * half + bob)

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
    def __init__(self, particle_scale=1.0):
        self.particle_scale = particle_scale
        random.seed(7)

        self.dl_path = Path([(-3.0, 10.5), (23.0, 10.5)])
        self.ul_path = Path([(10.7, 23.0), (10.7, -3.0)])
        self.ring_path = Path([(0.6, 0.6), (19.4, 0.6),
                               (19.4, 19.4), (0.6, 19.4)], loop=True)
        self.cpu_loop = Path([(11.0, 0.8), (17.8, 0.8),
                              (17.8, 8.6), (11.0, 8.6)], loop=True)
        self.disk_loop = Path([(1.0, 11.4), (9.6, 11.4),
                               (9.6, 18.8), (1.0, 18.8)], loop=True)

        scene = []

        ram_spots = [(3.6, 1.6), (5.9, 1.8), (8.2, 1.6),
                     (3.8, 4.2), (6.1, 4.4), (8.4, 4.2),
                     (4.0, 6.6), (6.3, 6.8), (8.2, 6.6)]
        for i, (gx, gy) in enumerate(ram_spots):
            h = random.randint(110, 190) + (22 if i == 4 else 0)
            scene.append(IsoBuilding(gx, gy, 1.8, 1.8, h, RAM_COLOR, "ram",
                                     "RAM" if i == 1 else None))

        cpu_spots = [(11.8, 1.6), (14.1, 1.8), (16.4, 1.6),
                     (12.0, 4.2), (14.3, 4.4), (16.6, 4.2),
                     (12.2, 6.6), (14.5, 6.8), (16.4, 6.6)]
        for i, (gx, gy) in enumerate(cpu_spots):
            h = random.randint(60, 132)
            scene.append(IsoBuilding(gx, gy, 1.8, 1.8, h, CPU_COLOR, "cpu",
                                     "CPU" if i == 1 else None))

        for gx, gy in ((2.0, 12.0), (5.3, 12.2), (2.3, 15.4), (5.7, 15.7)):
            scene.append(IsoWarehouse(gx, gy))
        scene.append(IsoBuilding(8.1, 12.3, 1.4, 1.4, 56, DISK_COLOR,
                                 "disk", "DISK"))
        scene.append(Crane(9.0, 15.0))
        scene.append(Crane(4.9, 14.5, height=76, jib=56, flip=True))

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

        for gx in (1.5, 4.5, 7.5, 13.5, 16.5):
            scene.append(Streetlight(gx, 9.6, DOWN_COLOR, "dl"))
        for gy in (2.5, 5.5, 12.5, 15.5, 18.5):
            scene.append(Streetlight(11.7, gy, UP_COLOR, "ul"))

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
        random.seed()

        self.particles = []
        self.drones = []
        self.rain = Rain()
        self.lightning = Lightning()

        self.cpu = self.ram = 0.0
        self.dl = self.ul = self.dr = self.dw = 0.0
        self.stress = 0.0
        self.spike = 0.0
        self.n = dict(cpu=0.0, ram=0.0, dl=0.0, ul=0.0, disk=0.0)

    def _build_background(self):
        bg = pygame.Surface((WIDTH, HEIGHT))
        for y in range(HEIGHT):
            bg.fill(mix(COL_BG_TOP, COL_BG_BOT, y / HEIGHT), (0, y, WIDTH, 1))
        for _ in range(140):
            x = random.randint(0, WIDTH - 1)
            y = random.randint(0, 260)
            b = random.randint(40, 130)
            bg.set_at((x, y), (b, b, min(255, b + 30)))

        x = 90
        while x < 910:
            w = random.randint(20, 46)
            h = random.randint(26, 96)
            base = 152 + abs(x + w / 2 - ISO_OX) * 0.5
            pygame.draw.rect(bg, (13, 16, 33), (x, int(base - h), w, h))
            x += w + random.randint(2, 12)

        PT, PR = iso(0, 0), iso(GRID_N, 0)
        PB, PL = iso(GRID_N, GRID_N), iso(0, GRID_N)
        SD = PLAT_SIDE
        pygame.draw.polygon(bg, (8, 10, 20),
                            [PL, PB, (PB[0], PB[1] + SD), (PL[0], PL[1] + SD)])
        pygame.draw.polygon(bg, (11, 13, 25),
                            [PB, PR, (PR[0], PR[1] + SD), (PB[0], PB[1] + SD)])
        pygame.draw.polygon(bg, (13, 16, 30), [PT, PR, PB, PL])
        for i in range(0, GRID_N + 1, 2):
            pygame.draw.line(bg, (20, 26, 48), iso(i, 0), iso(i, GRID_N))
            pygame.draw.line(bg, (20, 26, 48), iso(0, i), iso(GRID_N, i))
        pygame.draw.lines(bg, (52, 70, 116), True, [PT, PR, PB, PL], 1)
        pygame.draw.line(bg, col_scale(RAM_COLOR, 0.35), PL, PB)
        pygame.draw.line(bg, col_scale(CPU_COLOR, 0.35), PB, PR)
        pygame.draw.line(bg, col_scale(RAM_COLOR, 0.14),
                         (PL[0], PL[1] + SD), (PB[0], PB[1] + SD))
        pygame.draw.line(bg, col_scale(CPU_COLOR, 0.14),
                         (PB[0], PB[1] + SD), (PR[0], PR[1] + SD))

        blit_glow(bg, iso(6, 4), 150, RAM_COLOR, 0.10)
        blit_glow(bg, iso(14, 4), 150, CPU_COLOR, 0.10)
        blit_glow(bg, iso(5, 15), 130, DISK_COLOR, 0.08)
        blit_glow(bg, iso(15, 15), 130, mix(DOWN_COLOR, UP_COLOR, 0.5), 0.08)

        bake_road(bg, self.ring_path, (100, 130, 180))
        bake_road(bg, self.cpu_loop, CPU_COLOR)
        bake_road(bg, self.disk_loop, DISK_COLOR)
        bake_road(bg, self.dl_path, DOWN_COLOR)
        bake_road(bg, self.ul_path, UP_COLOR)

        for i, yy in enumerate(range(int(PB[1]) + SD + 6, HEIGHT - 6, 7)):
            f = max(0.0, 1.0 - i / 22)
            pygame.draw.line(bg, mix((11, 14, 32), (20, 27, 54), f),
                             (PL[0] + i * 6, yy), (PR[0] - i * 6, yy))
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

    def trigger_stress(self):
        self.spike = random.uniform(0.55, 1.0)

    def update(self, dt, t, raw):
        cpu, ram, dl, ul, dr, dw = raw
        s = clamp(dt * 3.2)
        self.cpu = lerp(self.cpu, cpu, s)
        self.ram = lerp(self.ram, ram, s)
        self.dl = lerp(self.dl, dl, s)
        self.ul = lerp(self.ul, ul, s)
        self.dr = lerp(self.dr, dr, s)
        self.dw = lerp(self.dw, dw, s)

        self.spike = max(0.0, self.spike - dt * 0.075)

        cpu_n = clamp(self.cpu / 100 + self.spike * 0.5)
        ram_n = clamp(self.ram / 100 + self.spike * 0.3)
        dl_n = clamp(soft_norm(self.dl, 2.5 * MB) + self.spike * 0.45)
        ul_n = clamp(soft_norm(self.ul, 1.2 * MB) + self.spike * 0.45)
        disk_n = clamp(soft_norm(self.dr + self.dw, 24 * MB) + self.spike * 0.45)
        self.n = dict(cpu=cpu_n, ram=ram_n, dl=dl_n, ul=ul_n, disk=disk_n)

        stress_target = clamp(0.5 * cpu_n + 0.28 * ram_n + 0.18 * disk_n
                              + 0.12 * max(dl_n, ul_n) + self.spike * 0.8)
        self.stress = lerp(self.stress, stress_target, clamp(dt * 1.6))
        st = self.stress

        for fleet in self.fleets:
            inten = st if fleet.metric == "st" else self.n[fleet.metric]
            fleet.update(dt, inten, st)

        ps = self.particle_scale
        if random.random() < dl_n * dt * 45 * ps:
            dx, dy = 0.894, 0.447
            speed = random.uniform(280, 500)
            x, y = iso(-2.8, 10.5, 4)
            self.particles.append(Particle(
                x, y, dx * speed, dy * speed, 1.8, DOWN_COLOR,
                random.choice((1, 2, 2))))
        if random.random() < ul_n * dt * 30 * ps:
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

        want_drones = int(clamp((st - 0.45) / 0.55) * 4)
        self.drones = [d for d in self.drones if not d.offscreen()]
        while len(self.drones) < want_drones:
            self.drones.append(Drone())
        for d in self.drones:
            d.update(dt)
        self.rain.update(dt, clamp((st - 0.48) / 0.5) * ps)
        self.lightning.update(dt, st)

    def draw(self, surf, t):
        n, st = self.n, self.stress
        surf.blit(self.background, (0, 0))

        draw_road_flow(surf, self.dl_path, DOWN_COLOR, n["dl"], t)
        draw_road_flow(surf, self.ul_path, UP_COLOR, n["ul"], t)
        draw_road_flow(surf, self.cpu_loop, CPU_COLOR, n["cpu"] * 0.8, t)
        draw_road_flow(surf, self.disk_loop, DISK_COLOR, n["disk"] * 0.8, t)

        beat = 0.5 + 0.5 * math.sin(t * (2 + n["cpu"] * 5))
        blit_glow(surf, iso(10.7, 10.5), 18, mix(DOWN_COLOR, UP_COLOR, 0.5),
                  0.15 + 0.45 * max(n["dl"], n["ul"]) * beat)

        ring = clamp((st - 0.45) / 0.55)
        if ring > 0.03:
            pulse = 0.6 + 0.4 * math.sin(t * 4)
            corners = [iso(0, 0), iso(GRID_N, 0), iso(GRID_N, GRID_N),
                       iso(0, GRID_N)]
            pygame.draw.lines(surf, col_scale(STRESS_COLOR, ring * pulse * 0.8),
                              True, corners, 2)
            for cpt in corners:
                blit_glow(surf, cpt, 18, STRESS_COLOR, ring * pulse * 0.5)

        sprites = list(self.scene)
        for fleet in self.fleets:
            fleet.collect(sprites)
        sprites.sort(key=lambda o: o.key)
        for obj in sprites:
            if isinstance(obj, _PodSprite):
                obj.draw(surf, t)
            else:
                obj.draw(surf, t, n[obj.metric], st)

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

        red = clamp((st - 0.55) / 0.45)
        if red > 0.02:
            pulse = 0.72 + 0.28 * math.sin(t * 3.4)
            tinted = self.vignette.copy()
            tinted.fill(col_scale((255, 255, 255), red * pulse),
                        special_flags=pygame.BLEND_RGB_MULT)
            surf.blit(tinted, (0, 0), special_flags=pygame.BLEND_RGB_ADD)


DISTRICT_LABELS = [
    ("MEMORY SPIRES · RAM", (400, 14), RAM_COLOR),
    ("PROCESSING GRID · CPU", (716, 124), CPU_COLOR),
    ("STORAGE DOCKS · DISK", (58, 330), DISK_COLOR),
    ("DOWNLINK EXPRESSWAY", (56, 214), DOWN_COLOR),
    ("UPLINK EXPRESSWAY", (128, 546), UP_COLOR),
]
