"""Perspective-projection highway + vehicles, ported from index.html's canvas
renderer to Pygame draw calls. The 3D-ish look (a single vanishing point, cars
scaling and slowing as they recede) is the same trick the original used —
world coordinates (x sideways, z depth) projected through one camera above
the road. Neon glow/shadow effects use the shared glow cache instead of
canvas ``shadowBlur``, and canvas gradients are approximated with flat/banded
fills since Pygame has no built-in gradient brush."""
import math
import random
from collections import deque

import pygame

from shared.renderer.glow import blit_glow
from shared.utils.color import mix
from shared.utils.mathutil import clamp

from .traffic import PROTOCOLS

W, H = 1280, 800
Z_NEAR, Z_FAR = 1.0, 26.0
LANES_DOWN = (-6.4, -4.4, -2.4)   # oncoming traffic = download
LANES_UP = (2.4, 4.4, 6.4)        # traffic moving away = upload
ROAD_EDGE, MEDIAN = 7.7, 1.3
MAX_VEHICLES = 240

HORIZON_Y = H * 0.36
CAM_Y = H * 1.18
CX = W / 2
PPU = min(W, H * 1.6) * 0.07

NEON_CYAN = (0, 229, 255)
NEON_MAGENTA = (255, 45, 149)


def project(x, z):
    s = Z_NEAR / z
    return (CX + x * PPU * s, HORIZON_Y + (CAM_Y - HORIZON_Y) * s, s)


def _vehicle_type(size_bytes):
    if size_bytes < 150:
        return dict(br=0.85, lg=1.5, speed_mul=1.3, style="mini")
    if size_bytes < 800:
        return dict(br=1.1, lg=2.4, speed_mul=1.0, style="car")
    if size_bytes < 1300:
        return dict(br=1.2, lg=3.4, speed_mul=0.85, style="bus")
    return dict(br=1.35, lg=4.8, speed_mul=0.72, style="truck")


class Vehicle:
    __slots__ = ("lane", "z", "down", "v", "br", "lg", "style", "color")

    def __init__(self, lane, z, down, v, br, lg, style, color):
        self.lane, self.z, self.down = lane, z, down
        self.v, self.br, self.lg, self.style, self.color = v, br, lg, style, color


def _build_background():
    """Sky, stars, the glowing vanishing point, horizon line, and ground —
    baked once since none of it depends on scroll position."""
    bg = pygame.Surface((W, H))
    sky_top, sky_mid, sky_bot = (2, 3, 10), (10, 16, 48), (39, 16, 74)
    band = int(HORIZON_Y * 1.25) + 2
    for y in range(band):
        f = y / max(1, band - 1)
        col = mix(sky_top, sky_mid, f / 0.72) if f < 0.72 else mix(sky_mid, sky_bot, (f - 0.72) / 0.28)
        bg.fill(col, (0, y, W, 1))
    rng = random.Random(4)
    for _ in range(W // 5):
        y = rng.uniform(0, HORIZON_Y * 0.92)
        b = 0.25 + rng.random() * 0.65
        col = (159, 220, 255) if rng.random() > 0.85 else (223, 233, 255)
        bg.set_at((int(rng.uniform(0, W)), int(y)), tuple(int(c * b) for c in col))
    blit_glow(bg, (CX, HORIZON_Y), int(W * 0.22), NEON_CYAN, 0.35)
    blit_glow(bg, (CX, HORIZON_Y), int(W * 0.34), NEON_MAGENTA, 0.16)
    pygame.draw.line(bg, NEON_CYAN, (0, HORIZON_Y), (W, HORIZON_Y), 2)
    blit_glow(bg, (CX, HORIZON_Y), 40, NEON_CYAN, 0.5)
    ground_top, ground_bot = (11, 8, 32), (4, 6, 15)
    for y in range(int(HORIZON_Y), H):
        f = (y - HORIZON_Y) / max(1, H - HORIZON_Y)
        bg.fill(mix(ground_top, ground_bot, f), (0, y, W, 1))
    return bg


def _draw_road(surf, scroll):
    for x in range(-34, 35, 4):  # step ~3.6, integer-friendly
        x = x * 0.9
        if abs(x) < ROAD_EDGE + 1.5:
            continue
        a = project(x, Z_NEAR * 0.92)
        b = project(x, Z_FAR * 3)
        pygame.draw.line(surf, (0, 40, 51), (a[0], a[1]), (b[0], b[1]), 1)

    step = 2.4
    off = scroll % step
    z = Z_NEAR + (step - off)
    while z < Z_FAR * 2.2:
        p = project(0, z)
        alpha = clamp(0.13 * min(p[2] * 2, 1))
        if alpha > 0.02 and 0 <= p[1] <= H:
            line_col = mix((3, 5, 12), NEON_CYAN, alpha)
            pygame.draw.line(surf, line_col, (0, p[1]), (W, p[1]), 1)
        z += step

    nl = project(-ROAD_EDGE, Z_NEAR * 0.9)
    nr = project(ROAD_EDGE, Z_NEAR * 0.9)
    fl = project(-ROAD_EDGE, Z_FAR * 4)
    fr = project(ROAD_EDGE, Z_FAR * 4)
    pygame.draw.polygon(surf, (9, 11, 22), [nl[:2], fl[:2], fr[:2], nr[:2]])

    for edge_x in (-ROAD_EDGE, ROAD_EDGE):
        a, b = project(edge_x, Z_NEAR * 0.9), project(edge_x, Z_FAR * 4)
        pygame.draw.line(surf, NEON_CYAN, a[:2], b[:2], 2)
    blit_glow(surf, project(-ROAD_EDGE, 3)[:2], 30, NEON_CYAN, 0.35)
    blit_glow(surf, project(ROAD_EDGE, 3)[:2], 30, NEON_CYAN, 0.35)
    for med_x in (-MEDIAN, MEDIAN):
        a, b = project(med_x, Z_NEAR * 0.9), project(med_x, Z_FAR * 4)
        pygame.draw.line(surf, NEON_MAGENTA, a[:2], b[:2], 2)

    dash, gap = 1.5, 2.2
    cycle = dash + gap
    doff = scroll % cycle
    for lane_x in (-5.4, -3.4, 3.4, 5.4):
        z = Z_NEAR + (cycle - doff)
        while z < Z_FAR * 1.6:
            a = project(lane_x, z)
            b = project(lane_x, min(z + dash, Z_FAR * 1.6))
            alpha = clamp(0.5 * min(a[2] * 1.6, 1))
            if alpha > 0.03:
                col = mix((9, 11, 22), (190, 240, 255), alpha)
                width = max(1, int(3.2 * a[2]))
                pygame.draw.line(surf, col, a[:2], b[:2], width)
            z += cycle


class HighwayRenderer:
    def __init__(self, particle_scale=1.0):
        self.particle_scale = particle_scale
        self.background = _build_background()
        self.vehicles = []
        self.pending = deque()
        self.scroll = 0.0
        self.skipped = 0

    def spawn(self, pkt):
        cap = max(60, int(MAX_VEHICLES * self.particle_scale))
        if len(self.vehicles) >= cap:
            self.skipped += 1
            return
        down = pkt["d"] == 0
        lanes = LANES_DOWN if down else LANES_UP
        vt = _vehicle_type(pkt["s"])
        color = PROTOCOLS.get(pkt["p"], PROTOCOLS["other"])["color"]
        order = (0, 1, 2) if vt["speed_mul"] > 1 else (2, 1, 0) if vt["speed_mul"] < 0.9 else (1, 0, 2)
        start_z = Z_FAR if down else Z_NEAR * 1.05
        for i in order:
            lane = lanes[2 - i] if down else lanes[i]
            collision = any(
                v.lane == lane and v.down == down
                and abs(v.z - start_z) < (v.lg + vt["lg"]) * 0.7 + 0.8
                for v in self.vehicles)
            if not collision:
                base = (4.5 + random.uniform(0, 1.4)) * vt["speed_mul"] * (1 + i * 0.12)
                speed = base * (1.45 if down else 1.0)
                self.vehicles.append(Vehicle(lane, start_z, down, speed,
                                             vt["br"], vt["lg"], vt["style"], color))
                return
        if len(self.pending) < 140:
            self.pending.append(pkt)
        else:
            self.skipped += 1

    def update(self, dt, new_packets):
        self.scroll += dt * 6.5
        for _ in range(6):
            if not self.pending:
                break
            self.spawn(self.pending.popleft())
        for pkt in new_packets:
            self.spawn(pkt)

        for v in self.vehicles:
            v.z += -v.v * dt if v.down else v.v * dt
        self.vehicles = [v for v in self.vehicles
                          if not ((v.down and v.z < Z_NEAR * 0.55) or (not v.down and v.z > Z_FAR))]
        self.vehicles.sort(key=lambda v: -v.z)

    def _draw_vehicle(self, surf, v):
        p = project(v.lane, v.z)
        if p[2] < 0.045:
            pygame.draw.circle(surf, v.color, (int(p[0]), int(p[1])), 1)
            return
        x0, y0, s = p
        br = v.br * PPU * s
        lg = v.lg * PPU * s * 0.55
        x, y = x0 - br / 2, y0 - lg

        trail_z = v.z + (2.6 if v.down else -1.4) * v.lg * 0.45
        tp = project(v.lane, max(trail_z, Z_NEAR * 0.92))
        steps = 4
        for i in range(steps):
            t = (i + 1) / steps
            tx = x0 + (tp[0] - x0) * t
            ty = (y0 - lg * 0.4) + (tp[1] - (y0 - lg * 0.4)) * t
            blit_glow(surf, (tx, ty), max(2, br * 0.22), v.color, 0.35 * (1 - t))

        pygame.draw.ellipse(surf, mix((5, 6, 12), v.color, 0.32),
                            (x0 - br * 0.78, y0 + br * 0.08 - br * 0.26, br * 1.56, br * 0.52))

        body_rect = pygame.Rect(int(x), int(y), max(2, int(br)), max(2, int(lg)))
        radius = max(1, int(br * 0.28))
        pygame.draw.rect(surf, (10, 13, 22), body_rect, border_radius=radius)
        pygame.draw.rect(surf, v.color, body_rect, max(1, int(1.4 * s * 2)), border_radius=radius)
        blit_glow(surf, body_rect.center, max(br, lg) * 0.9, v.color, clamp(0.5 * s * 3))

        accent = (*v.color, 140)
        cab = pygame.Surface(body_rect.size, pygame.SRCALPHA)
        if v.style == "truck":
            cab_h = max(1, int(lg * 0.2))
            cab_y = body_rect.height - cab_h - int(br * 0.1) if v.down else int(br * 0.1)
            pygame.draw.rect(cab, (160, 235, 255, 70),
                             (int(br * 0.16), cab_y, max(1, int(br * 0.68)), cab_h))
        else:
            pygame.draw.rect(cab, (160, 235, 255, 70),
                             (int(br * 0.18), int(lg * 0.32), max(1, int(br * 0.64)),
                              max(1, int(lg * 0.34))), border_radius=max(1, int(br * 0.18)))
        surf.blit(cab, body_rect.topleft)

        lamp_y = y + lg - br * 0.14
        lamp_r = max(1, br * 0.1)
        lamp_col = (255, 247, 214) if v.down else (255, 59, 48)
        for lx in (x + br * 0.22, x + br * 0.78):
            pygame.draw.circle(surf, lamp_col, (int(lx), int(lamp_y)), int(lamp_r))
        blit_glow(surf, (x0, lamp_y), max(4, br * 0.5), lamp_col, clamp(0.5 * s * 2))

        if v.down and s > 0.42:
            blit_glow(surf, (x0, y + lg * 0.3), br * 2.0, (255, 247, 214), 0.10)

    def draw(self, surf):
        surf.blit(self.background, (0, 0))
        _draw_road(surf, self.scroll)
        for v in self.vehicles:
            self._draw_vehicle(surf, v)
