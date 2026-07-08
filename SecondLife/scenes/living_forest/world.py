"""LivingForest world systems — noise, lighting, seasons, weather, terrain,
sky, and the ForestWorld orchestrator that ties them together with the
entities from ``entities.py``. Ported ~as-is from the standalone app; only
the top-level pygame window/event-loop (now ``LivingForestScene``) was
removed and camera zoom/pan now uses the shared ``Camera2D``.
"""
import math
import random

import pygame
import pygame.gfxdraw as gfx

from shared.camera.camera2d import Camera2D
from shared.renderer.glow import glow

from .common import (DAY_LEN, ELEV, GRID, H, HH, HW, MAX_TREES, OX, OY,
                      SEASON_DAYS, SEASONS, SPEEDS, TAU, W, YEAR_DAYS, cadd,
                      clamp, clerp, cmul, fcircle, fell, fline, fpoly, gray,
                      isoS, key_lerp, lerp, smooth, year_lerp)
from .entities import (AUTUMN_PALS, Bee, Bird, Bush, Butterfly, Deer, Fern,
                        Firefly, Flower, Fox, GrassTuft, Mushroom, Particle,
                        Rabbit, RockBig, SeedFluff, Tree, Waterfall)


# ---------------------------------------------------------------------- noise
class Noise:
    def __init__(self, seed):
        rnd = random.Random(seed)
        self.vals = [rnd.random() for _ in range(512)]
        self.perm = list(range(256))
        rnd.shuffle(self.perm)
        self.perm += self.perm

    def _v(self, ix, iy):
        return self.vals[self.perm[(self.perm[ix & 255] + iy) & 255]]

    def n2(self, x, y):
        ix, iy = int(math.floor(x)), int(math.floor(y))
        fx, fy = x - ix, y - iy
        u, v = smooth(fx), smooth(fy)
        a = lerp(self._v(ix, iy), self._v(ix + 1, iy), u)
        b = lerp(self._v(ix, iy + 1), self._v(ix + 1, iy + 1), u)
        return lerp(a, b, v)

    def fbm(self, x, y, octaves=4, lac=2.0, gain=0.5):
        total, amp, norm = 0.0, 1.0, 0.0
        for _ in range(octaves):
            total += self.n2(x, y) * amp
            norm += amp
            x *= lac
            y *= lac
            amp *= gain
        return total / norm


def lerp2(p1, p2, t):
    return (p1[0] + (p2[0] - p1[0]) * t, p1[1] + (p2[1] - p1[1]) * t)


# ------------------------------------------------------------------- lighting
SKY_KEYS = [
    (0.00, ((10, 14, 36), (30, 40, 72))),
    (0.19, ((12, 18, 42), (38, 48, 82))),
    (0.245, ((54, 60, 112), (236, 152, 108))),
    (0.30, ((100, 156, 208), (250, 216, 164))),
    (0.42, ((108, 176, 228), (198, 232, 240))),
    (0.58, ((104, 172, 226), (196, 229, 238))),
    (0.69, ((96, 142, 205), (252, 198, 130))),
    (0.755, ((62, 62, 118), (242, 134, 96))),
    (0.82, ((16, 22, 50), (48, 56, 96))),
    (1.00, ((10, 14, 36), (30, 40, 72))),
]
AMB_KEYS = [
    (0.00, (76, 92, 152)),
    (0.19, (78, 94, 154)),
    (0.25, (255, 206, 166)),
    (0.32, (255, 240, 221)),
    (0.45, (255, 252, 245)),
    (0.60, (255, 250, 238)),
    (0.69, (255, 218, 164)),
    (0.755, (240, 152, 112)),
    (0.83, (88, 102, 162)),
    (1.00, (76, 92, 152)),
]
NIGHT_KEYS = [(0.0, 1.0), (0.20, 1.0), (0.29, 0.0), (0.71, 0.0), (0.80, 1.0), (1.0, 1.0)]
SUN_KEYS = [(0.0, 0.0), (0.24, 0.0), (0.33, 0.65), (0.5, 1.0), (0.67, 0.65), (0.76, 0.0), (1.0, 0.0)]


class LightingSystem:
    def __init__(self):
        self.update(0.4, None, None)

    def update(self, t, weather, season):
        self.t = t
        top, bot = key_lerp(SKY_KEYS, t)
        amb = key_lerp(AMB_KEYS, t)
        self.night = key_lerp(NIGHT_KEYS, t)
        sun = key_lerp(SUN_KEYS, t)
        cloud = weather.cloud if weather else 0.0
        rain = weather.rain if weather else 0.0
        fog = weather.fog if weather else 0.0
        top = clerp(top, cmul(gray(top), 0.92), cloud * 0.65)
        bot = clerp(bot, cmul(gray(bot), 0.94), cloud * 0.6)
        amb = clerp(amb, cmul(gray(amb), 0.84), cloud * 0.5)
        amb = cmul(amb, 1.0 - rain * 0.16)
        amb = clerp(amb, (168, 172, 184), fog * 0.28)
        if season is not None:
            amb = clerp(amb, (214, 226, 248), season.snow * 0.22 * (1 - self.night))
        self.sky_top, self.sky_bot = top, bot
        self.ambient = amb
        self.sun_strength = sun * (1.0 - cloud * 0.85) * (1.0 - rain * 0.8)
        dp = (t - 0.23) / (0.77 - 0.23)
        self.day_prog = clamp(dp, 0, 1)
        self.sun_vis = 1.0 if 0.0 < dp < 1.0 else 0.0
        self.sun_pos = (lerp(W * 0.16, W * 0.84, self.day_prog),
                        436 - math.sin(self.day_prog * math.pi) * 330)
        self.sun_h = math.sin(self.day_prog * math.pi)
        np_ = ((t - 0.77) % 1.0) / 0.46
        self.moon_vis = 1.0 if 0.0 < np_ < 1.0 else 0.0
        self.moon_pos = (lerp(W * 0.2, W * 0.8, clamp(np_, 0, 1)),
                         400 - math.sin(clamp(np_, 0, 1) * math.pi) * 290)
        self.moon_h = math.sin(clamp(np_, 0, 1) * math.pi)
        self.shadow_dx = lerp(-1.0, 1.0, self.day_prog) * 9.0
        lowsun = clamp(1.0 - abs(dp - 0.16) / 0.16, 0, 1) + clamp(1.0 - abs(dp - 0.84) / 0.16, 0, 1)
        self.ray_alpha = 26.0 * clamp(lowsun, 0, 1) * (1.0 - cloud) * (1.0 - fog) * (1 - rain)
        self.dawn_glow = clamp(1.0 - abs(t - 0.25) / 0.07, 0, 1) + clamp(1.0 - abs(t - 0.755) / 0.07, 0, 1)


# --------------------------------------------------------------------- season
GRASS_YEAR = [(112, 175, 88), (92, 158, 74), (158, 138, 70), (124, 128, 96)]
FLOWER_YEAR = [1.0, 0.7, 0.3, 0.0]
LEAF_KEYS = [(0.0, 0.55), (0.06, 0.92), (0.12, 1.0), (0.55, 1.0), (0.65, 0.85),
             (0.71, 0.4), (0.75, 0.06), (0.96, 0.06), (1.0, 0.55)]
TEMP_YEAR = [12.0, 24.0, 10.0, -4.0]

OAK_PAL = {
    "spring": ((58, 128, 62), (92, 168, 82), (140, 204, 108)),
    "summer": ((44, 110, 52), (74, 148, 68), (118, 186, 92)),
    "winter": ((60, 90, 60), (80, 110, 74), (110, 140, 96)),
}
BIRCH_PAL = {
    "spring": ((88, 148, 66), (124, 184, 84), (168, 216, 110)),
    "summer": ((70, 132, 58), (104, 168, 76), (150, 202, 100)),
    "winter": ((80, 110, 66), (104, 136, 80), (136, 168, 100)),
}
PINE_PAL = {
    "spring": ((28, 84, 66), (44, 112, 82), (74, 146, 102)),
    "summer": ((24, 78, 62), (38, 104, 76), (66, 138, 96)),
    "winter": ((26, 68, 60), (40, 92, 74), (64, 120, 92)),
}


class SeasonSystem:
    def __init__(self, start_year=0.05):
        self.year = start_year
        self.snow = 0.0
        self.ice = 0.0
        self._refresh()

    def _refresh(self):
        s = (self.year * 4.0) % 4.0
        self.idx = int(s)
        self.progress = s - self.idx
        self.name = SEASONS[self.idx]
        self.flowerf = year_lerp(FLOWER_YEAR, self.year)
        self.temp_base = year_lerp(TEMP_YEAR, self.year)
        self.leaf = key_lerp(LEAF_KEYS, self.year)
        self.autumn_fall = clamp(1.0 - abs(self.year - 0.66) / 0.12, 0, 1)

    def update(self, sdt, forest):
        self.year = ((forest.day + forest.tday) / YEAR_DAYS) % 1.0
        self._refresh()
        target = 1.0 if (self.idx == 3 and forest.temp < 2.5) else 0.0
        rate = (2.6 if forest.weather.rain > 0.2 else 1.2) if target > self.snow else 1.0
        step = rate * (sdt / DAY_LEN)
        self.snow = clamp(self.snow + (step if target > self.snow else -step), 0, 1)
        self.ice = clamp(self.snow * 1.35 - 0.15, 0, 1)

    def grass_color(self):
        return year_lerp(GRASS_YEAR, self.year)

    def canopy(self, kind, autumn_idx, huev):
        if kind == "pine":
            pal = PINE_PAL
        elif kind == "birch":
            pal = BIRCH_PAL
        else:
            pal = OAK_PAL
        aut = AUTUMN_PALS[autumn_idx % len(AUTUMN_PALS)] if kind != "pine" else pal["summer"]
        if kind == "birch":
            aut = AUTUMN_PALS[2]
        seq = [pal["spring"], pal["summer"], aut, pal["winter"]]
        dark = year_lerp([p[0] for p in seq], self.year)
        mid = year_lerp([p[1] for p in seq], self.year)
        hi = year_lerp([p[2] for p in seq], self.year)
        return (cadd(dark, huev), cadd(mid, huev), cadd(hi, huev))


# -------------------------------------------------------------------- weather
WEATHER_KINDS = {
    "Sunny":      dict(cloud=0.10, wind=0.16, rain=0.0, fog=0.0),
    "Cloudy":     dict(cloud=0.72, wind=0.30, rain=0.0, fog=0.05),
    "Windy":      dict(cloud=0.38, wind=0.95, rain=0.0, fog=0.0),
    "Rain":       dict(cloud=0.82, wind=0.42, rain=0.45, fog=0.10),
    "Heavy Rain": dict(cloud=0.94, wind=0.62, rain=1.0, fog=0.18),
    "Fog":        dict(cloud=0.55, wind=0.08, rain=0.0, fog=1.0),
    "Storm":      dict(cloud=1.0, wind=1.0, rain=1.0, fog=0.08),
}
WEATHER_NEXT = {
    "Sunny":      [("Sunny", 3.0), ("Cloudy", 2.0), ("Windy", 1.1), ("Fog", 0.45)],
    "Cloudy":     [("Sunny", 2.0), ("Cloudy", 1.4), ("Rain", 1.6), ("Windy", 0.9), ("Fog", 0.7)],
    "Windy":      [("Sunny", 1.6), ("Cloudy", 1.4), ("Storm", 0.45)],
    "Rain":       [("Cloudy", 1.6), ("Heavy Rain", 1.0), ("Sunny", 0.8), ("Fog", 0.5)],
    "Heavy Rain": [("Rain", 1.5), ("Storm", 0.9), ("Cloudy", 0.8)],
    "Fog":        [("Cloudy", 1.3), ("Sunny", 1.0), ("Rain", 0.5)],
    "Storm":      [("Heavy Rain", 1.2), ("Rain", 1.0), ("Cloudy", 0.5)],
}


class WeatherSystem:
    def __init__(self, forest, forced=None):
        self.f = forest
        self.forced = forced
        self.kind = forced or "Sunny"
        p = WEATHER_KINDS[self.kind]
        self.cloud, self.windv, self.rain, self.fog = p["cloud"], p["wind"], p["rain"], p["fog"]
        self.timer = forest.rng.uniform(30, 70)
        self.flash = 0.0
        self.bolts = []
        self.bolt_timer = 6.0

    def _pick_next(self):
        season = self.f.season.idx
        opts = []
        for kind, wgt in WEATHER_NEXT[self.kind]:
            if season == 3 and kind == "Storm":
                wgt *= 0.25
            if season == 2:
                if kind in ("Fog", "Rain"):
                    wgt *= 1.6
            if season == 1 and kind == "Sunny":
                wgt *= 1.5
            opts.append((kind, wgt))
        total = sum(w for _, w in opts)
        r = self.f.rng.uniform(0, total)
        for kind, wgt in opts:
            r -= wgt
            if r <= 0:
                return kind
        return opts[-1][0]

    def update(self, sdt):
        if not self.forced:
            self.timer -= sdt
            if self.timer <= 0:
                self.kind = self._pick_next()
                self.timer = self.f.rng.uniform(35, 85)
        tgt = WEATHER_KINDS[self.kind]
        k = clamp(sdt / 9.0, 0, 1)
        self.cloud += (tgt["cloud"] - self.cloud) * k
        self.windv += (tgt["wind"] - self.windv) * k
        self.rain += (tgt["rain"] - self.rain) * k
        self.fog += (tgt["fog"] - self.fog) * k
        self.flash = max(0.0, self.flash - sdt * 4.5)
        self.bolts = [(pts, ttl - sdt) for pts, ttl in self.bolts if ttl - sdt > 0]
        if self.kind == "Storm" and self.rain > 0.6:
            self.bolt_timer -= sdt
            if self.bolt_timer <= 0:
                self.bolt_timer = self.f.rng.uniform(2.5, 9.0)
                self.flash = 1.0
                x = self.f.rng.uniform(W * 0.2, W * 0.8)
                y = 30.0
                pts = [(x, y)]
                ty = self.f.rng.uniform(360, 520)
                while y < ty:
                    y += self.f.rng.uniform(26, 60)
                    x += self.f.rng.uniform(-38, 38)
                    pts.append((x, y))
                self.bolts.append((pts, 0.22))

    def display_name(self):
        if self.f.season.snow > 0.35 or (self.f.season.idx == 3 and self.f.temp < 1):
            if self.kind == "Heavy Rain":
                return "Heavy Snow"
            if self.kind in ("Rain", "Storm"):
                return "Snowfall"
        return self.kind


# -------------------------------------------------------------------- terrain
class Terrain:
    def __init__(self, forest, seed):
        self.f = forest
        self.seed = seed
        self.gen()
        self.surface = None
        self._job = None
        self._pend = None
        self._pkey = None
        self._ptimer = 0.0
        self.puddles = {}
        self.ripples = []
        P = self._params()
        self._pkey = self._param_key(P)
        for _ in self._render(P):
            pass
        self._build_water_static()

    def add_ripple(self):
        if self.wtiles and self.f.season.ice < 0.5:
            gx, gy, pts, cx, cy = self.f.rng.choice(self.wtiles)
            self.ripples.append([cx, cy, 0.0])

    def gen(self):
        n1 = Noise(self.seed)
        n2 = Noise(self.seed * 7 + 3)
        n3 = Noise(self.seed * 13 + 5)
        self.n2 = n2
        G = GRID
        self.land = [[False] * G for _ in range(G)]
        self.elev = [[0] * G for _ in range(G)]
        self.water = [[False] * G for _ in range(G)]
        self.moist = [[0.0] * G for _ in range(G)]
        self.gnoise = [[0.0] * G for _ in range(G)]
        self.rand01 = [[0.0] * G for _ in range(G)]
        rr = random.Random(self.seed * 3 + 1)
        c = G / 2.0
        for x in range(G):
            for y in range(G):
                dx = (x + 0.5 - c) / (G * 0.47)
                dy = (y + 0.5 - c) / (G * 0.47)
                r = math.hypot(dx, dy)
                coast = n3.fbm(x * 0.16 + 7.7, y * 0.16 + 2.3, 3) - 0.5
                landv = 1.0 - r + coast * 0.5
                self.land[x][y] = landv > 0.14
                h = n1.fbm(x * 0.11 + 50, y * 0.11 + 50, 4)
                hn = clamp(h * 0.9 + clamp(landv, 0, 1) * 0.55 - 0.30, 0, 1.2)
                self.elev[x][y] = int(clamp(hn * 5.6, 0, 4))
                self.gnoise[x][y] = n2.fbm(x * 0.3, y * 0.3, 3)
                self.rand01[x][y] = rr.random()
        for _ in range(2):
            for x in range(G):
                for y in range(G):
                    cnt = sum(1 for ax, ay in ((x-1, y), (x+1, y), (x, y-1), (x, y+1))
                              if 0 <= ax < G and 0 <= ay < G and self.land[ax][ay])
                    if self.land[x][y] and cnt < 2:
                        self.land[x][y] = False
                    elif not self.land[x][y] and cnt == 4:
                        self.land[x][y] = True
        self._edge_dist()
        self._carve_pond(rr, n3)
        self._carve_stream(rr, n3)
        self._moisture(n3)
        self.cliffd = [[int(56 + n2.fbm(x * 0.35 + 3, y * 0.35 + 9, 3) * 56 + self.elev[x][y] * ELEV)
                        for y in range(G)] for x in range(G)]
        self.land_list = [(x, y) for x in range(G) for y in range(G)
                          if self.land[x][y] and not self.water[x][y]]
        self.draw_order = sorted(
            [(x, y) for x in range(G) for y in range(G) if self.land[x][y]],
            key=lambda t: t[0] + t[1])
        self._place_decor(rr)

    def _edge_dist(self):
        G = GRID
        self.edged = [[99] * G for _ in range(G)]
        q = []
        for x in range(G):
            for y in range(G):
                if not self.land[x][y]:
                    self.edged[x][y] = 0
                    q.append((x, y))
                elif x in (0, G - 1) or y in (0, G - 1):
                    self.edged[x][y] = 1
                    q.append((x, y))
        i = 0
        while i < len(q):
            x, y = q[i]
            i += 1
            d = self.edged[x][y]
            for ax, ay in ((x-1, y), (x+1, y), (x, y-1), (x, y+1)):
                if 0 <= ax < G and 0 <= ay < G and self.edged[ax][ay] > d + 1:
                    self.edged[ax][ay] = d + 1
                    q.append((ax, ay))

    def _carve_pond(self, rr, n3):
        G = GRID
        cands = [(x, y) for x in range(G) for y in range(G)
                 if self.land[x][y] and self.edged[x][y] >= 4 and self.elev[x][y] <= 1]
        if not cands:
            cands = [(x, y) for x in range(G) for y in range(G)
                     if self.land[x][y] and self.edged[x][y] >= 4]
        if not cands:
            self.pond_c = None
            return
        px, py = rr.choice(cands)
        self.pond_c = (px + 0.5, py + 0.5)
        for x in range(G):
            for y in range(G):
                d = math.hypot(x - px, y - py)
                warp = (n3.fbm(x * 0.4 + 40, y * 0.4 + 40, 2) - 0.5) * 1.6
                if d + warp < 2.5 and self.land[x][y] and self.edged[x][y] >= 3:
                    self.water[x][y] = True
                    self.elev[x][y] = 0
        for x in range(G):
            for y in range(G):
                if self.land[x][y] and not self.water[x][y]:
                    near = any(0 <= ax < G and 0 <= ay < G and self.water[ax][ay]
                               for ax, ay in ((x-1, y), (x+1, y), (x, y-1), (x, y+1),
                                              (x-1, y-1), (x+1, y+1), (x-1, y+1), (x+1, y-1)))
                    if near:
                        self.elev[x][y] = min(self.elev[x][y], 1)

    def _carve_stream(self, rr, n3):
        self.stream = []
        self.waterfall = None
        if not self.pond_c:
            return
        G = GRID
        cx, cy = self.pond_c
        vx, vy = (G - 2) - cx + rr.uniform(-4, 4), (G - 2) - cy + rr.uniform(-4, 4)
        m = math.hypot(vx, vy)
        if m < 0.5:
            vx, vy = 0.707, 0.707
        else:
            vx, vy = vx / m, vy / m
        best, bs = None, -1e9
        for x in range(G):
            for y in range(G):
                if self.water[x][y]:
                    s = (x - cx) * vx + (y - cy) * vy
                    if s > bs:
                        bs, best = s, (x, y)
        x, y = best
        pe = 0
        for _ in range(26):
            opts = []
            for ax, ay in ((x-1, y), (x+1, y), (x, y-1), (x, y+1)):
                if not (0 <= ax < G and 0 <= ay < G) or not self.land[ax][ay]:
                    self.waterfall = (x, y, ax - x, ay - y)
                    opts = None
                    break
                if self.water[ax][ay]:
                    continue
                score = ((ax - cx) * vx + (ay - cy) * vy) + rr.uniform(0, 1.4)
                score += (pe - self.elev[ax][ay]) * 0.8
                opts.append((score, ax, ay))
            if opts is None or not opts:
                break
            opts.sort(reverse=True)
            _, x, y = opts[0]
            self.water[x][y] = True
            self.elev[x][y] = min(self.elev[x][y], pe)
            pe = self.elev[x][y]
            self.stream.append((x, y))

    def _moisture(self, n3):
        G = GRID
        q = []
        dist = [[9] * G for _ in range(G)]
        for x in range(G):
            for y in range(G):
                if self.water[x][y]:
                    dist[x][y] = 0
                    q.append((x, y))
        i = 0
        while i < len(q):
            x, y = q[i]
            i += 1
            d = dist[x][y]
            if d >= 5:
                continue
            for ax, ay in ((x-1, y), (x+1, y), (x, y-1), (x, y+1)):
                if 0 <= ax < G and 0 <= ay < G and dist[ax][ay] > d + 1:
                    dist[ax][ay] = d + 1
                    q.append((ax, ay))
        for x in range(G):
            for y in range(G):
                near = clamp(1.0 - dist[x][y] / 5.0, 0, 1)
                self.moist[x][y] = clamp(near * 0.7 + n3.fbm(x * 0.2 + 90, y * 0.2 + 90, 3) * 0.5, 0, 1)

    def _place_decor(self, rr):
        self.decor = {}
        for (x, y) in self.land_list:
            if rr.random() < 0.09 and self.edged[x][y] >= 2:
                self.decor.setdefault((x, y), []).append(
                    ("peb", rr.random(), rr.random(), rr.randint(0, 9999)))
        good = [t for t in self.land_list if self.edged[t[0]][t[1]] >= 3]
        for _ in range(6):
            if good:
                t = rr.choice(good)
                self.decor.setdefault(t, []).append(("stump", rr.random(), rr.random(), rr.randint(0, 9999)))
        for _ in range(5):
            if good:
                t = rr.choice(good)
                self.decor.setdefault(t, []).append(("log", rr.random(), rr.uniform(0, TAU), rr.randint(0, 9999)))

    def walkable(self, gx, gy):
        x, y = int(gx), int(gy)
        return 0 <= x < GRID and 0 <= y < GRID and self.land[x][y] and not self.water[x][y]

    def elev_px(self, fx, fy):
        gx = clamp(fx - 0.5, 0.0, GRID - 1.001)
        gy = clamp(fy - 0.5, 0.0, GRID - 1.001)
        x0, y0 = int(gx), int(gy)
        tx, ty = gx - x0, gy - y0

        def e(x, y):
            x, y = clamp(x, 0, GRID - 1), clamp(y, 0, GRID - 1)
            if not self.land[x][y] or self.water[x][y]:
                return 0
            return self.elev[x][y]
        a = lerp(e(x0, y0), e(x0 + 1, y0), tx)
        b = lerp(e(x0, y0 + 1), e(x0 + 1, y0 + 1), tx)
        return lerp(a, b, ty) * ELEV

    def _params(self):
        f = self.f
        grass = f.season.grass_color()
        return dict(grass=grass, lip=cadd(grass, 20), snow=round(f.season.snow, 2),
                    autumn=f.season.autumn_fall)

    def _param_key(self, P):
        g = P["grass"]
        return (g[0] // 5, g[1] // 5, g[2] // 5, int(P["snow"] * 8))

    def tick(self, sdt, rdt):
        f = self.f
        self._ptimer -= rdt
        if self._ptimer <= 0 and self._job is None:
            self._ptimer = 0.6
            P = self._params()
            key = self._param_key(P)
            if key != self._pkey:
                self._pkey = key
                self._job = self._render(P)
        if self._job is not None:
            try:
                for _ in range(2):
                    next(self._job)
            except StopIteration:
                self._job = None
        wet = f.weather.rain > 0.3 and f.season.snow < 0.5
        if wet and f.rng.random() < rdt * 3.0 and len(self.puddles) < 26:
            t = f.rng.choice(self.land_list)
            self.puddles[t] = self.puddles.get(t, 0.0)
        for t in list(self.puddles):
            self.puddles[t] += (rdt * 0.25 if wet else -rdt * 0.05)
            if self.puddles[t] > 1.0:
                self.puddles[t] = 1.0
            elif self.puddles[t] < 0.02 and not wet:
                del self.puddles[t]
        self.ripples = [[x, y, a + rdt] for x, y, a in self.ripples if a + rdt < 1.2]
        if f.rng.random() < rdt * (1.2 + f.weather.rain * 14):
            self.add_ripple()

    def _render(self, P):
        surf = pygame.Surface((W, H), pygame.SRCALPHA)
        cnt = 0
        for (gx, gy) in self.draw_order:
            self._draw_tile(surf, gx, gy, P)
            for d in self.decor.get((gx, gy), ()):
                self._draw_decor(surf, gx, gy, d, P)
            cnt += 1
            if cnt % 130 == 0:
                yield None
        self.surface = surf

    def _draw_tile(self, s, gx, gy, P):
        e = self.elev[gx][gy]
        wat = self.water[gx][gy]
        zt = e * ELEV
        h = self.rand01[gx][gy]
        A = isoS(gx, gy, zt)
        B = isoS(gx + 1, gy, zt)
        C = isoS(gx + 1, gy + 1, zt)
        D = isoS(gx, gy + 1, zt)
        moist = self.moist[gx][gy]
        for (p1, p2), (nx, ny), lit in (((B, C), (gx + 1, gy), 0.62), ((C, D), (gx, gy + 1), 0.88)):
            if 0 <= nx < GRID and 0 <= ny < GRID and self.land[nx][ny]:
                if self.water[nx][ny]:
                    drop = zt - self.elev[nx][ny] * ELEV + 7
                    if drop > 0:
                        col = cmul((172, 150, 106), lit * (0.9 + h * 0.2))
                        fpoly(s, (p1, p2, (p2[0], p2[1] + drop), (p1[0], p1[1] + drop)), col)
                elif self.elev[nx][ny] < e and not wat:
                    self._step_face(s, p1, p2, (e - self.elev[nx][ny]) * ELEV, lit, h, P)
            else:
                self._cliff_face(s, p1, p2, zt + self.cliffd[gx][gy], lit, h, moist, P, gx, gy)
        if wat:
            fpoly(s, (A, B, C, D), (24, 50, 64))
            return
        g = P["grass"]
        v = (self.gnoise[gx][gy] - 0.5) * 36
        col = cadd(g, v + e * 5)
        col = cmul(col, 1.0 - moist * 0.10)
        near_w = any(0 <= ax < GRID and 0 <= ay < GRID and self.water[ax][ay]
                     for ax, ay in ((gx-1, gy), (gx+1, gy), (gx, gy-1), (gx, gy+1)))
        if near_w:
            col = clerp(col, (176, 158, 116), 0.4)
        snowc = clamp(P["snow"] * 1.45 - h * 0.5, 0, 1)
        col = clerp(col, (233, 240, 249), snowc)
        fpoly(s, (A, B, C, D), col)
        if gy > 0 and self.land[gx][gy - 1] and self.elev[gx][gy - 1] > e:
            fpoly(s, (A, B, lerp2(B, D, 0.18), lerp2(A, C, 0.18)), (20, 30, 24, 46))
        if gx > 0 and self.land[gx - 1][gy] and self.elev[gx - 1][gy] > e:
            fpoly(s, (A, D, lerp2(D, B, 0.18), lerp2(A, C, 0.18)), (20, 30, 24, 40))
        fr = gx + 1 >= GRID or not self.land[gx + 1][gy] or self.elev[gx + 1][gy] < e \
            if gx + 1 < GRID else True
        fl = gy + 1 >= GRID or not self.land[gx][gy + 1] or self.elev[gx][gy + 1] < e \
            if gy + 1 < GRID else True
        if fr:
            fline(s, B, C, cadd(col, 22) + (170,), 1)
        if fl:
            fline(s, C, D, cadd(col, 22) + (170,), 1)
        rr = random.Random(int(h * 100000) + gx * 57 + gy)
        cx4 = (A[0] + C[0]) / 2
        cy4 = (A[1] + C[1]) / 2
        if snowc < 0.5:
            for _ in range(2):
                px = cx4 + rr.uniform(-8.8, 8.8)
                py = cy4 + rr.uniform(-4.4, 4.4)
                dv = rr.choice((-26, -18, 20))
                fline(s, (px, py), (px + rr.uniform(-2, 2), py - rr.uniform(1, 3)),
                      cadd(col, dv) + (200,), 1)
        else:
            for _ in range(2):
                px = cx4 + rr.uniform(-8, 8)
                py = cy4 + rr.uniform(-4, 4)
                fcircle(s, px, py, 1, (255, 255, 255, 130))

    def _step_face(self, s, p1, p2, drop, lit, h, P):
        col = cmul((124, 94, 64), lit * (0.9 + h * 0.2))
        fpoly(s, (p1, p2, (p2[0], p2[1] + drop), (p1[0], p1[1] + drop)), col)
        lip = clerp(P["lip"], (238, 244, 250), clamp(P["snow"] * 1.3, 0, 1))
        fline(s, p1, p2, cmul(lip, lit + 0.12), 2)

    def _cliff_face(self, s, p1, p2, drop, lit, h, moist, P, gx, gy):
        rr = random.Random(int(h * 100000) + gx * 131 + gy * 7)
        strata = ((0.00, 0.12, (98, 76, 54)),
                  (0.12, 0.44, (128, 96, 66)),
                  (0.44, 0.74, (108, 80, 56)),
                  (0.74, 1.00, (106, 92, 82)))
        for f0, f1, col in strata:
            col = cmul(col, lit * (0.92 + rr.random() * 0.14))
            if f1 >= 1.0:
                jag = rr.uniform(8, 26)
                pts = ((p1[0], p1[1] + drop * f0), (p2[0], p2[1] + drop * f0),
                       (p2[0], p2[1] + drop), ((p1[0] + p2[0]) / 2, p2[1] + drop + jag),
                       (p1[0], p1[1] + drop))
            else:
                pts = ((p1[0], p1[1] + drop * f0), (p2[0], p2[1] + drop * f0),
                       (p2[0], p2[1] + drop * f1), (p1[0], p1[1] + drop * f1))
            fpoly(s, pts, col)
        for _ in range(rr.randint(0, 2)):
            rx = lerp(p1[0], p2[0], rr.uniform(0.2, 0.8))
            ry = lerp(p1[1], p2[1], rr.uniform(0.2, 0.8)) + drop * rr.uniform(0.25, 0.85)
            rw = rr.uniform(2, 5)
            fell(s, rx, ry, rw, rw * 0.7, cmul((132, 128, 132), lit))
            fell(s, rx - rw * 0.3, ry - rw * 0.3, rw * 0.5, rw * 0.35, cmul((160, 156, 158), lit))
        if rr.random() < 0.45:
            rx = lerp(p1[0], p2[0], rr.uniform(0.25, 0.75))
            ry = lerp(p1[1], p2[1], rr.uniform(0.25, 0.75)) + 2
            px, py = rx, ry
            for i in range(4):
                nx2 = px + rr.uniform(-3, 3)
                ny2 = py + drop * 0.06
                fline(s, (px, py), (nx2, ny2), cmul((70, 50, 36), lit), 1)
                px, py = nx2, ny2
        if moist > 0.4:
            for _ in range(3):
                mx = lerp(p1[0], p2[0], rr.random())
                my = lerp(p1[1], p2[1], rr.random()) + rr.uniform(2, drop * 0.12)
                fcircle(s, mx, my, rr.uniform(1, 2), cmul((92, 140, 70), lit + 0.1))
        lip = clerp(P["lip"], (240, 246, 252), clamp(P["snow"] * 1.3, 0, 1))
        fline(s, p1, p2, cmul(lip, lit + 0.1), 2)
        for _ in range(3):
            t = rr.random()
            bx = lerp(p1[0], p2[0], t)
            by = lerp(p1[1], p2[1], t) + 1
            fline(s, (bx, by), (bx + rr.uniform(-2, 2), by + rr.uniform(3, 6)),
                  cmul(lip, lit * 0.9), 1)

    def _draw_decor(self, s, gx, gy, d, P):
        kind = d[0]
        zt = self.elev[gx][gy] * ELEV
        snow = P["snow"]
        if kind == "peb":
            _, u, v, sd = d
            px, py = isoS(gx + 0.2 + u * 0.6, gy + 0.2 + v * 0.6, zt)
            rr = random.Random(sd)
            for _ in range(rr.randint(1, 3)):
                ox, oy = rr.uniform(-4, 4), rr.uniform(-2, 2)
                r = rr.uniform(1.5, 3)
                fell(s, px + ox, py + oy, r, r * 0.7, (118, 116, 122))
                fell(s, px + ox - r * 0.3, py + oy - r * 0.3, r * 0.5, r * 0.35,
                     clerp((150, 148, 152), (235, 240, 246), snow))
        elif kind == "stump":
            _, u, v, sd = d
            px, py = isoS(gx + 0.5, gy + 0.5, zt)
            hgt = 7
            pygame.draw.rect(s, (96, 70, 50), (int(px - 6), int(py - hgt), 12, hgt))
            fell(s, px, py, 6.5, 3.4, (86, 62, 44))
            top = clerp((196, 166, 118), (238, 242, 248), snow)
            fell(s, px, py - hgt, 6.5, 3.4, top)
            gfx.ellipse(s, int(px), int(py - hgt), 4, 2, (150, 122, 82, 220))
            gfx.ellipse(s, int(px), int(py - hgt), 2, 1, (150, 122, 82, 220))
        elif kind == "log":
            _, u, ang, sd = d
            px, py = isoS(gx + 0.5, gy + 0.5, zt)
            rr = random.Random(sd)
            L = rr.uniform(18, 28)
            dx, dy = math.cos(ang), math.sin(ang) * 0.5
            x1, y1 = px - dx * L / 2, py - dy * L / 2
            x2, y2 = px + dx * L / 2, py + dy * L / 2
            nx, ny = -dy, dx * 0.5
            wdt = 4.5
            fpoly(s, ((x1 + nx * wdt, y1 + ny * wdt), (x2 + nx * wdt, y2 + ny * wdt),
                      (x2 - nx * wdt, y2 - ny * wdt), (x1 - nx * wdt, y1 - ny * wdt)),
                  (104, 78, 56))
            fpoly(s, ((x1 + nx * wdt, y1 + ny * wdt - 2), (x2 + nx * wdt, y2 + ny * wdt - 2),
                      (x2, y2 - wdt), (x1, y1 - wdt)), (126, 96, 68))
            fell(s, x2, y2, 4, 3, (172, 142, 100))
            gfx.ellipse(s, int(x2), int(y2), 2, 1, (130, 104, 72, 220))
            for _ in range(3):
                t = rr.random()
                fcircle(s, lerp(x1, x2, t), lerp(y1, y2, t) - 3, 1.5, (94, 138, 74))
            if snow > 0.2:
                fline(s, (x1, y1 - wdt), (x2, y2 - wdt),
                      (240, 245, 250, int(200 * clamp(snow * 1.4, 0, 1))), 3)

    def _build_water_static(self):
        self.wtiles = []
        minx, miny, maxx, maxy = 1e9, 1e9, -1e9, -1e9
        for x in range(GRID):
            for y in range(GRID):
                if self.water[x][y]:
                    z = self.elev[x][y] * ELEV + 3
                    pts = [isoS(x, y, z), isoS(x + 1, y, z), isoS(x + 1, y + 1, z), isoS(x, y + 1, z)]
                    for p in pts:
                        minx, miny = min(minx, p[0]), min(miny, p[1])
                        maxx, maxy = max(maxx, p[0]), max(maxy, p[1])
                    self.wtiles.append((x, y, pts, 0, 0))
        if not self.wtiles:
            self.wbox = pygame.Rect(0, 0, 1, 1)
            self.wmask = pygame.Surface((1, 1), pygame.SRCALPHA)
            self._wl = pygame.Surface((1, 1), pygame.SRCALPHA)
            self.stream_pts = []
            return
        self.wbox = pygame.Rect(int(minx) - 3, int(miny) - 3,
                                int(maxx - minx) + 6, int(maxy - miny) + 6)
        ox, oy = self.wbox.x, self.wbox.y
        tiles = []
        self.wmask = pygame.Surface(self.wbox.size, pygame.SRCALPHA)
        for x, y, pts, _, _ in self.wtiles:
            rel = [(p[0] - ox, p[1] - oy) for p in pts]
            cx = sum(p[0] for p in rel) / 4
            cy = sum(p[1] for p in rel) / 4
            tiles.append((x, y, rel, cx, cy))
            fpoly(self.wmask, rel, (255, 255, 255, 255))
        self.wtiles = tiles
        self._wl = pygame.Surface(self.wbox.size, pygame.SRCALPHA)
        self.stream_pts = []
        for (x, y) in self.stream:
            z = self.elev[x][y] * ELEV + 3
            p = isoS(x + 0.5, y + 0.5, z)
            self.stream_pts.append((p[0] - ox, p[1] - oy))
        if self.pond_c:
            p = isoS(self.pond_c[0], self.pond_c[1], 3)
            self.pond_scr = (p[0] - ox, p[1] - oy)
        else:
            self.pond_scr = (0, 0)

    def draw_water(self, scene, f):
        for (x, y), amt in self.puddles.items():
            if self.water[x][y]:
                continue
            zt = self.elev[x][y] * ELEV
            cx, cy = f.iso(x + 0.5, y + 0.5, zt - 1)
            sc = 0.25 + 0.55 * amt
            pts = ((cx, cy - HH * sc), (cx + HW * sc, cy), (cx, cy + HH * sc), (cx - HW * sc, cy))
            fpoly(scene, pts, (128, 158, 182, int(95 * amt)))
            fell(scene, cx - 2, cy - 1, HW * sc * 0.4, HH * sc * 0.32,
                 (208, 226, 238, int(70 * amt)))
        if not self.wtiles:
            return
        wl = self._wl
        wl.fill((0, 0, 0, 0))
        ice = f.season.ice
        base = clerp((58, 126, 158), (88, 110, 132), f.weather.cloud * 0.6)
        base = clerp(base, (176, 200, 214), ice)
        for i, (gx, gy, pts, cx, cy) in enumerate(self.wtiles):
            b = 1.0 + 0.06 * math.sin(f.anim_t * 1.3 + gx * 1.7 + gy * 2.3)
            fpoly(wl, pts, cmul(base, b))
        if ice < 0.6:
            for i, (gx, gy, pts, cx, cy) in enumerate(self.wtiles):
                if i % 3 == 0:
                    ph = f.anim_t * 2.1 + i * 1.31
                    ox2 = math.sin(ph) * 6
                    oy2 = math.cos(ph * 0.7) * 2
                    fline(wl, (cx - 5 + ox2, cy + oy2), (cx + 4 + ox2, cy + oy2 * 0.5),
                          (188, 224, 238, 110), 1)
            for j, (sx, sy) in enumerate(self.stream_pts):
                a = int(130 * max(0.0, math.sin(f.anim_t * 3.0 - j * 1.1)))
                if a > 8:
                    fcircle(wl, sx + math.sin(j * 9.7) * 4, sy + math.cos(j * 5.1) * 2, 1,
                            (208, 232, 240, a))
        else:
            rr = random.Random(self.seed)
            px2, py2 = self.pond_scr
            for _ in range(4):
                x1 = px2 + rr.uniform(-30, 30)
                y1 = py2 + rr.uniform(-14, 14)
                fline(wl, (x1, y1), (x1 + rr.uniform(-18, 18), y1 + rr.uniform(-7, 7)),
                      (222, 236, 244, 90), 1)
            fell(wl, px2 - 8, py2 - 4, 26, 10, (255, 255, 255, 26))
        for x2, y2, age in self.ripples:
            fr = age / 1.2
            a = int(120 * (1 - fr))
            if a > 6:
                    gfx.ellipse(wl, int(x2), int(y2), max(1, int(fr * 18)), max(1, int(fr * 8)),
                            (214, 236, 244, a))
        for tr in (f.pond_trees if ice < 0.5 else ()):
            if tr.refl is not None and not tr.dead:
                bx, by = isoS(tr.gx, tr.gy, self.elev_px(tr.gx, tr.gy))
                wsp = tr.refl.get_width()
                wl.blit(tr.refl, (bx - self.wbox.x - wsp // 2, by - self.wbox.y + 1))
        px2, py2 = self.pond_scr
        if f.light.night > 0.5 and f.weather.cloud < 0.7 and ice < 0.6:
            shim = 0.7 + 0.3 * math.sin(f.anim_t * 2.7)
            fell(wl, px2, py2, 22, 5, (196, 214, 240, int(60 * shim * f.light.night)))
            fell(wl, px2, py2, 9, 2.4, (238, 244, 252, int(110 * shim * f.light.night)))
        elif f.light.sun_strength > 0.4 and ice < 0.6:
            shim = 0.6 + 0.4 * math.sin(f.anim_t * 3.3)
            fell(wl, px2 + math.sin(f.anim_t * 0.7) * 6, py2, 14, 3,
                 (255, 246, 214, int(52 * shim)))
        wl.blit(self.wmask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        scene.blit(wl, (self.wbox.x, self.wbox.y + f.bob))


# ------------------------------------------------------------------------ sky
class Cloud:
    def __init__(self, rng):
        self.speed = rng.uniform(0.6, 1.5)
        self.y = rng.uniform(20, 210)
        self.thr = rng.uniform(0.0, 0.6)
        w = int(rng.uniform(150, 300))
        h = int(w * 0.34) + 16
        self.w = w
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        n = rng.randint(5, 8)
        for i in range(n):
            cxp = rng.uniform(w * 0.14, w * 0.86)
            cyp = h * 0.62 + rng.uniform(-4, 6)
            r = rng.uniform(w * 0.1, w * 0.2)
            fell(surf, cxp, cyp + 5, r * 1.1, r * 0.5, (198, 206, 226, 255))
        for i in range(n):
            cxp = rng.uniform(w * 0.14, w * 0.86)
            cyp = h * 0.55 + rng.uniform(-8, 4)
            r = rng.uniform(w * 0.09, w * 0.19)
            fell(surf, cxp, cyp, r, r * 0.62, (250, 252, 255, 255))
        self.surf = surf
        self.x = rng.uniform(-w, W)

    def update(self, rdt, wind):
        self.x += (5 + wind * 48) * self.speed * rdt
        if self.x > W + 60:
            self.x = -self.w - random.uniform(0, 120)

    def vis(self, f):
        return clamp(f.weather.cloud * 1.7 - self.thr, 0, 1)

    def draw(self, s, f):
        v = self.vis(f)
        if v <= 0.03:
            return
        self.surf.set_alpha(int(215 * v))
        s.blit(self.surf, (int(self.x), int(self.y + math.sin(f.anim_t * 0.1 + self.thr * 9) * 3)))


class FogBand:
    def __init__(self, rng, i):
        self.y = 300 + i * 90 + rng.uniform(-20, 20)
        self.speed = rng.uniform(6, 14) * (1 if i % 2 == 0 else -1)
        self.i = i
        surf = pygame.Surface((W, 90), pygame.SRCALPHA)
        for _ in range(46):
            fell(surf, rng.uniform(0, W), rng.uniform(18, 72),
                 rng.uniform(50, 110), rng.uniform(9, 20), (235, 238, 244, 9))
        self.surf = surf
        self.x = rng.uniform(0, W)

    def draw(self, s, f):
        dawn_mist = clamp(1 - abs(f.light.t - 0.27) / 0.06, 0, 1) * 0.25
        d = clamp(f.weather.fog + dawn_mist, 0, 1)
        if d <= 0.02:
            return
        self.x = (self.x + self.speed * 0.016) % W
        a = int(190 * d * (0.65 + 0.35 * math.sin(f.anim_t * 0.13 + self.i * 2.4)))
        self.surf.set_alpha(clamp(a, 0, 255))
        x = int(self.x)
        s.blit(self.surf, (x - W, int(self.y)))
        s.blit(self.surf, (x, int(self.y)))


# --------------------------------------------------------------------- world
class ForestWorld:
    """Owns every simulation system and entity — everything the standalone
    ``LivingForest`` app class did, minus the pygame window/event loop, which
    now live in ``LivingForestScene``."""

    def __init__(self, args, particle_scale=1.0):
        self.args = args
        self.particle_scale = particle_scale
        self.scene = pygame.Surface((W, H)).convert()
        self.tint = pygame.Surface((W, H)).convert()
        self.mask_layer = pygame.Surface((W, H), pygame.SRCALPHA)
        self.camera = Camera2D(W, H, min_zoom=1.0, max_zoom=2.4, follow_speed=6.0)
        self.detail = 1.0
        self._fpst = 0.0
        self.paused = False
        self._build_static()
        self.reset(args.get("seed") or random.randint(1, 10 ** 6))

    def _build_static(self):
        rr = random.Random(42)
        self.stars = pygame.Surface((W, 270), pygame.SRCALPHA)
        for _ in range(150):
            x, y = rr.uniform(0, W), rr.uniform(0, 260)
            b = rr.randint(70, 220)
            r = 1 if rr.random() < 0.9 else 2
            fcircle(self.stars, x, y, r, (b, b, min(255, b + 25), 255))
        small = pygame.Surface((160, 100), pygame.SRCALPHA)
        for px in range(160):
            for py in range(100):
                dx, dy = (px - 80) / 80, (py - 50) / 50
                r = math.hypot(dx * 0.9, dy)
                a = int(clamp((r - 0.62) / 0.5, 0, 1) ** 2 * 88)
                if a:
                    small.set_at((px, py), (8, 10, 18, a))
        self.vignette = pygame.transform.smoothscale(small, (W, H))

    def iso(self, gx, gy, z=0.0):
        x, y = isoS(gx, gy, z)
        return (x, y + self.bob)

    def reset(self, seed):
        self.seed = seed
        self.rng = random.Random(seed)
        self.anim_t = 0.0
        self.wind_phase = 0.0
        self.bob = 0.0
        self.speed_i = 2
        self.paused = False
        self.day = 0
        tod = self.args.get("tod")
        self.tday = 0.34 if tod is None else tod
        a_season = self.args.get("season")
        if a_season:
            idx = [s.lower() for s in SEASONS].index(a_season.lower())
            self.day = int(idx * SEASON_DAYS + 1)
        self.temp = 15.0
        self.season = SeasonSystem(((self.day + self.tday) / YEAR_DAYS) % 1.0)
        if a_season and a_season.lower() == "winter":
            self.season.snow = 1.0
            self.season.ice = 1.0
            self.temp = -2.0
        self.weather = WeatherSystem(self, forced=self.args.get("weather"))
        self.light = LightingSystem()
        self.light.update(self.tday, self.weather, self.season)
        self.entities = []
        self.particles = []
        self.fireflies = []
        self.glow_req = []
        self.trees = []
        self.flowers = []
        self.grasses = []
        self.pond_trees = []
        self.tree_count = 0
        self.animal_count = 0
        self._cache_t = 0.0
        self._spawn_t = 0.0
        self.terrain = Terrain(self, seed)
        self._populate()
        self.clouds = [Cloud(self.rng) for _ in range(7)]
        self.fogbands = [FogBand(self.rng, i) for i in range(3)]
        self._refresh_lists()

    def _populate(self):
        t, rng = self.terrain, self.rng
        opens = [p for p in t.land_list if t.edged[p[0]][p[1]] >= 5]
        self.clearing = rng.choice(opens) if opens else (GRID // 2, GRID // 2)
        placed = []
        target = rng.randint(56, 70)
        for _ in range(4200):
            if len(placed) >= target:
                break
            x = rng.uniform(1.5, GRID - 1.5)
            y = rng.uniform(1.5, GRID - 1.5)
            if not t.walkable(x, y) or t.edged[int(x)][int(y)] < 2:
                continue
            if math.hypot(x - self.clearing[0], y - self.clearing[1]) < 3.4 and rng.random() < 0.92:
                continue
            if rng.random() > 0.2 + t.gnoise[int(x)][int(y)] * 0.9:
                continue
            if any((x - p[0]) ** 2 + (y - p[1]) ** 2 < 4.4 for p in placed):
                continue
            stage = rng.choices(("adult", "young", "old", "sapling"),
                                weights=(0.48, 0.22, 0.14, 0.16))[0]
            self.entities.append(Tree(self, x, y, stage=stage, warm=True))
            placed.append((x, y))
        self.trees = [e for e in self.entities if isinstance(e, Tree)]

        def scatter(cls, n, cond=None, mind=0.0):
            made = 0
            for _ in range(n * 30):
                if made >= n:
                    break
                x = rng.uniform(1.5, GRID - 1.5)
                y = rng.uniform(1.5, GRID - 1.5)
                if not t.walkable(x, y):
                    continue
                if cond and not cond(int(x), int(y)):
                    continue
                if mind and any((x - p[0]) ** 2 + (y - p[1]) ** 2 < mind * mind for p in placed):
                    continue
                self.entities.append(cls(self, x, y))
                made += 1
        scatter(Bush, 30, lambda x, y: t.edged[x][y] >= 2, 1.0)
        scatter(GrassTuft, 340)
        scatter(Fern, 52, lambda x, y: t.moist[x][y] > 0.42)
        scatter(Mushroom, 20, lambda x, y: t.moist[x][y] > 0.5)
        scatter(RockBig, 13, lambda x, y: t.edged[x][y] >= 2, 1.2)
        centers = [self.clearing]
        for _ in range(4):
            if opens:
                centers.append(rng.choice(t.land_list))
        for cx, cy in centers:
            for _ in range(26):
                x = cx + rng.gauss(0, 1.6)
                y = cy + rng.gauss(0, 1.6)
                if t.walkable(x, y):
                    fl = Flower(self, x, y)
                    fl.bloom = rng.uniform(0.3, 1.0)
                    self.entities.append(fl)
        if t.waterfall:
            self.entities.append(Waterfall(self, t.waterfall))
        for _ in range(5):
            self.entities.append(Rabbit(self))
        for _ in range(3):
            self.entities.append(Deer(self))
        for _ in range(2):
            self.entities.append(Fox(self))
        for _ in range(6):
            self.entities.append(Bird(self))
        for _ in range(8):
            self.entities.append(Butterfly(self))
        for _ in range(6):
            self.entities.append(Bee(self))
        self.fireflies = [Firefly(self) for _ in range(16)]

    def _refresh_lists(self):
        self.trees = [e for e in self.entities if isinstance(e, Tree) and not e.dead]
        self.flowers = [e for e in self.entities if isinstance(e, Flower) and not e.dead]
        self.grasses = [e for e in self.entities if isinstance(e, GrassTuft)]
        self.tree_count = len(self.trees)
        self.animal_count = (sum(1 for e in self.entities
                                 if isinstance(e, (Rabbit, Deer, Fox, Bird, Butterfly, Bee)))
                             + sum(1 for ff in self.fireflies if ff.vis > 0.1))
        if self.terrain.pond_c:
            px, py = self.terrain.pond_c
            self.pond_trees = [t for t in self.trees
                               if math.hypot(t.gx - px, t.gy - py) < 5.5 and t.canopy_r > 6]
        else:
            self.pond_trees = []

    # ------------------------------------------------------------- ecosystem
    def try_seed(self, tree):
        if len(self.trees) >= MAX_TREES or self.rng.random() < 0.2:
            return
        self.entities.append(SeedFluff(self, tree.gx + self.rng.uniform(-0.5, 0.5),
                                       tree.gy + self.rng.uniform(-0.5, 0.5),
                                       tree.trunk_h + tree.canopy_r))

    def plant_tree(self, gx, gy):
        t = self.terrain
        if len(self.trees) >= MAX_TREES:
            return
        if not t.walkable(gx, gy) or t.edged[int(gx)][int(gy)] < 2:
            return
        if any((gx - tr.gx) ** 2 + (gy - tr.gy) ** 2 < 2.2 for tr in self.trees):
            return
        tr = Tree(self, gx, gy, stage="seed")
        self.entities.append(tr)
        self.trees.append(tr)

    def _ambient_spawns(self, sdt):
        self._spawn_t += sdt
        if self._spawn_t < 2.0:
            return
        self._spawn_t = 0.0
        t, rng = self.terrain, self.rng
        if len(self.grasses) < 360 and self.grasses:
            g = rng.choice(self.grasses)
            x, y = g.gx + rng.uniform(-1.5, 1.5), g.gy + rng.uniform(-1.5, 1.5)
            if t.walkable(x, y):
                self.entities.append(GrassTuft(self, x, y))
        target = int(18 + 116 * self.season.flowerf)
        if len(self.flowers) < target:
            cx, cy = self.clearing if rng.random() < 0.4 else rng.choice(t.land_list)
            x, y = cx + rng.gauss(0, 1.8), cy + rng.gauss(0, 1.8)
            if t.walkable(x, y):
                self.entities.append(Flower(self, x, y))
        wet = self.weather.rain > 0.25 or self.season.idx == 2
        shroom_n = sum(1 for e in self.entities if isinstance(e, Mushroom))
        if wet and shroom_n < 30 and self.season.snow < 0.6 and rng.random() < 0.5:
            for _ in range(12):
                x, y = rng.uniform(2, GRID - 2), rng.uniform(2, GRID - 2)
                if t.walkable(x, y) and t.moist[int(x)][int(y)] > 0.45:
                    self.entities.append(Mushroom(self, x, y))
                    break
        if len(self.trees) < 44 and rng.random() < 0.35:
            for _ in range(20):
                x, y = rng.uniform(2, GRID - 2), rng.uniform(2, GRID - 2)
                if t.walkable(x, y) and t.edged[int(x)][int(y)] >= 2:
                    self.plant_tree(x, y)
                    break

    def _spawn_weather_particles(self, rdt):
        wt = self.weather
        t = self.terrain
        snowing = self.season.idx == 3 and self.temp < 1.5
        if wt.rain > 0.03 and t.land_list:
            n = wt.rain * (34 if snowing else 130) * rdt * self.particle_scale
            n = int(n) + (1 if self.rng.random() < n % 1 else 0)
            for _ in range(min(n, 14)):
                gx, gy = self.rng.choice(t.land_list)
                bx, by = self.iso(gx + self.rng.random(), gy + self.rng.random(),
                                  t.elev[gx][gy] * ELEV)
                if snowing:
                    self.particles.append(Particle(
                        "snow", bx + self.rng.uniform(-30, 30), by - self.rng.uniform(280, 460),
                        vx=wt.windv * 26, vy=self.rng.uniform(36, 66),
                        size=self.rng.choice((1, 1, 2)), gy=by, ph=self.rng.uniform(0, TAU),
                        col=(244, 248, 255)))
                else:
                    vy = self.rng.uniform(540, 660)
                    self.particles.append(Particle(
                        "rain", bx - wt.windv * 60, by - self.rng.uniform(300, 500),
                        vx=wt.windv * 90, vy=vy, gy=by))
                    if self.rng.random() < 0.06 * wt.rain:
                        self.terrain.add_ripple()
        if (wt.cloud < 0.4 and self.light.night < 0.3 and self.season.idx in (0, 1)
                and self.rng.random() < rdt * 3 and len(self.particles) < 700):
            gx, gy = self.rng.choice(t.land_list)
            bx, by = self.iso(gx, gy, t.elev[gx][gy] * ELEV)
            self.particles.append(Particle("mote", bx, by - self.rng.uniform(6, 60),
                                           vx=self.rng.uniform(-4, 4), vy=self.rng.uniform(-7, -2),
                                           ttl=self.rng.uniform(3, 7), ph=self.rng.uniform(0, TAU)))

    # ----------------------------------------------------------------- frame
    @property
    def speed(self):
        ov = self.args.get("speed")
        return ov if ov else SPEEDS[self.speed_i]

    def update(self, rdt):
        self.anim_t += rdt
        self.camera.update(rdt)
        sdt = 0.0 if self.paused else rdt * self.speed
        if self.args.get("tod") is None:
            self.tday += sdt / DAY_LEN
            if self.tday >= 1.0:
                self.tday -= 1.0
                self.day += 1
        diurnal = math.sin((self.tday - 0.33) * TAU) * 4.5
        self.temp = (self.season.temp_base + diurnal - self.weather.rain * 3
                     - self.weather.cloud * 2 + (2 if self.weather.kind == "Sunny" else 0))
        self.season.update(sdt, self)
        self.weather.update(sdt)
        self.light.update(self.tday, self.weather, self.season)
        self.wind_phase += rdt * (1.1 + self.weather.windv * 3.2)
        self.bob = math.sin(self.anim_t * 0.33) * 2.2
        self.terrain.tick(sdt, rdt)
        for e in self.entities:
            e.update(sdt)
        for ff in self.fireflies:
            ff.update(rdt)
        if any(e.dead for e in self.entities):
            self.entities = [e for e in self.entities if not e.dead]
        self._cache_t -= rdt
        if self._cache_t <= 0:
            self._cache_t = 1.0
            self._refresh_lists()
        self._ambient_spawns(sdt)
        if not self.paused:
            self._spawn_weather_particles(rdt)
            pdt = rdt * clamp(self.speed, 0.6, 1.6)
            spawned = []
            for p in self.particles:
                r = p.update(pdt, self)
                if r:
                    spawned.append(r)
            self.particles = [p for p in self.particles if p.ttl > 0][:900] + spawned
        for cl in self.clouds:
            cl.update(rdt, self.weather.windv)

    def draw(self):
        s = self.scene
        self.glow_req = []
        light = self.light
        for i in range(0, H, 4):
            fr = (i / H) ** 1.15
            s.fill(clerp(light.sky_top, light.sky_bot, fr), (0, i, W, 4))
        if light.sun_vis and light.night < 0.7:
            x, y = light.sun_pos
            fcircle(s, x, y, 22, (255, 244, 214))
            fcircle(s, x, y, 17, (255, 250, 234))
        if light.moon_vis and light.night > 0.25:
            x, y = light.moon_pos
            fcircle(s, x, y, 17, (222, 228, 242))
            fcircle(s, x - 5, y - 3, 4, (200, 206, 224))
            fcircle(s, x + 4, y + 5, 2.6, (204, 210, 226))
            fcircle(s, x + 6, y - 6, 2, (206, 212, 228))
        for cl in self.clouds:
            cl.draw(s, self)
        ib = 700 + self.bob
        for r, a in ((165, 30), (120, 22), (72, 18)):
            fell(s, OX, ib + 14, r * 1.7, r * 0.34, (8, 12, 24, a))
        for i, (ox, oy, sc2) in enumerate(((-215, -6, 1.0), (150, 16, 0.6), (-40, 38, 0.42))):
            rb = math.sin(self.anim_t * 0.4 + i * 2.4) * 4
            rx, ry = OX + ox, ib + oy + rb
            wr = 26 * sc2
            fpoly(s, ((rx - wr, ry), (rx - wr * 0.3, ry - wr * 0.55), (rx + wr * 0.6, ry - wr * 0.4),
                      (rx + wr, ry + wr * 0.1), (rx + wr * 0.3, ry + wr * 0.7),
                      (rx - wr * 0.6, ry + wr * 0.6)), (88, 84, 96))
            fpoly(s, ((rx - wr * 0.3, ry - wr * 0.55), (rx + wr * 0.6, ry - wr * 0.4),
                      (rx + wr * 0.1, ry - wr * 0.1), (rx - wr * 0.4, ry - wr * 0.16)),
                  (128, 126, 138))
            fcircle(s, rx - wr * 0.1, ry - wr * 0.3, wr * 0.14, (96, 138, 82))
        if self.terrain.surface:
            s.blit(self.terrain.surface, (0, self.bob))
        if light.sun_strength > 0.08 and self.weather.cloud > 0.04:
            ml = self.mask_layer
            ml.fill((0, 0, 0, 0))
            drew = False
            for cl in self.clouds:
                v = cl.vis(self)
                if v > 0.05:
                    fell(ml, cl.x + cl.w * 0.5, 330 + cl.y * 0.9,
                         cl.w * 0.55, cl.w * 0.16, (14, 22, 16, int(34 * v * light.sun_strength)))
                    drew = True
            if drew:
                ml.blit(self.terrain.surface, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
                s.blit(ml, (0, self.bob))
        self.terrain.draw_water(s, self)
        for e in sorted(self.entities, key=lambda e: e.depth):
            if self.detail < 0.95 and isinstance(e, (GrassTuft, Fern)) \
                    and (e.phase / TAU) > self.detail:
                continue
            e.draw(s)
        for p in self.particles:
            p.draw(s, self)
        for fb in self.fogbands:
            fb.draw(s, self)
        self.tint.fill(light.ambient)
        s.blit(self.tint, (0, 0), special_flags=pygame.BLEND_MULT)
        if light.dawn_glow > 0.04:
            gx2 = light.sun_pos[0] if light.sun_vis else OX
            g = glow(230, (66, 36, 14), clamp(light.dawn_glow, 0, 1))
            s.blit(g, (gx2 - 230, 380 - 230), special_flags=pygame.BLEND_RGB_ADD)
        if light.sun_vis and light.night < 0.6 and self.weather.cloud < 0.9:
            x, y = light.sun_pos
            inten = (1 - self.weather.cloud * 0.7) * clamp((light.sun_h - 0.2) / 0.3, 0, 1)
            if inten > 0.03:
                s.blit(glow(95, (60, 48, 26), inten), (x - 95, y - 95),
                       special_flags=pygame.BLEND_RGB_ADD)
        if light.moon_vis and light.night > 0.3:
            x, y = light.moon_pos
            rise = clamp((light.moon_h - 0.3) / 0.3, 0, 1)
            if rise > 0.03:
                s.blit(glow(70, (30, 38, 60), light.night * rise), (x - 70, y - 70),
                       special_flags=pygame.BLEND_RGB_ADD)
                fcircle(s, x, y, 15, (225, 231, 244, int(210 * rise)))
        if light.night > 0.08:
            tw = 0.82 + 0.18 * math.sin(self.anim_t * 1.7)
            self.stars.set_alpha(int(200 * light.night * tw))
            s.blit(self.stars, (0, 0))
        if light.ray_alpha > 1.5:
            sx, sy = light.sun_pos
            aim = math.atan2(470 - sy, OX - sx)
            for i in range(5):
                ang = aim + (i - 2) * 0.10 + math.sin(self.anim_t * 0.13 + i * 1.9) * 0.03
                dx2, dy2 = math.cos(ang), math.sin(ang)
                px2, py2 = -dy2, dx2
                w0, w1 = 5 + i * 2, 55 + i * 24
                L = 980
                a = light.ray_alpha * (0.4 + 0.6 * abs(math.sin(self.anim_t * 0.21 + i * 2.43)))
                fpoly(s, ((sx + px2 * w0, sy + py2 * w0), (sx - px2 * w0, sy - py2 * w0),
                          (sx + dx2 * L - px2 * w1, sy + dy2 * L - py2 * w1),
                          (sx + dx2 * L + px2 * w1, sy + dy2 * L + py2 * w1)),
                      (255, 226, 168, int(a)))
        for ff in self.fireflies:
            ff.glow_pass()
        for (x, y, r, col, inten) in self.glow_req:
            q = round(clamp(inten, 0, 1) * 6) / 6
            if q > 0.05:
                g = glow(int(r), col, q)
                s.blit(g, (x - int(r), y - int(r)), special_flags=pygame.BLEND_RGB_ADD)
        wt = self.weather
        if wt.bolts:
            for pts, ttl in wt.bolts:
                a = clamp(ttl / 0.22, 0, 1)
                ipts = [(int(p[0]), int(p[1])) for p in pts]
                pygame.draw.lines(s, (168, 178, 255), False, ipts, 4)
                pygame.draw.lines(s, (252, 252, 255), False, ipts, 2)
                ex, ey = ipts[-1]
                s.blit(glow(40, (90, 90, 140), a), (ex - 40, ey - 40),
                       special_flags=pygame.BLEND_RGB_ADD)
        if wt.flash > 0.01:
            f2 = wt.flash ** 2
            s.fill((int(88 * f2), int(92 * f2), int(118 * f2)),
                   special_flags=pygame.BLEND_RGB_ADD)
        s.blit(self.vignette, (0, 0))
        return s
