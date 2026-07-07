#!/usr/bin/env python3
"""
Living Forest — a living, procedurally generated isometric forest diorama.

A tiny floating island suspended in the sky, where trees sprout, grow old and
fall, animals wander, weather rolls through, days pass and seasons turn.
Everything on screen is drawn with pygame primitives — no assets, no sprites.

Controls:  SPACE pause · +/- speed · R new forest · arrows pan · wheel zoom · ESC quit
"""
import math
import random
import sys

import pygame
import pygame.gfxdraw as gfx

# ------------------------------------------------------------------ constants
W, H        = 1280, 760
GRID        = 34                 # tiles per side
HW, HH      = 16, 8              # half tile width / height (isometric diamond)
ELEV        = 9                  # pixels per elevation step
OX, OY      = W // 2, 146        # island origin on screen
DAY_LEN     = 120.0              # real seconds per in-game day at 1x speed
SEASON_DAYS = 4.0
YEAR_DAYS   = SEASON_DAYS * 4
SEASONS     = ("Spring", "Summer", "Autumn", "Winter")
MAX_TREES   = 100
TAU         = math.tau
SPEEDS      = (0.25, 0.5, 1.0, 2.0, 4.0, 8.0)


def isoS(gx, gy, z=0.0):
    """Static isometric projection (no island bob)."""
    return (OX + (gx - gy) * HW, OY + (gx + gy) * HH - z)


# ---------------------------------------------------------------------- utils
def clamp(v, a, b):
    return a if v < a else (b if v > b else v)


def lerp(a, b, t):
    return a + (b - a) * t


def smooth(t):
    return t * t * (3.0 - 2.0 * t)


def clerp(c1, c2, t):
    return (int(c1[0] + (c2[0] - c1[0]) * t),
            int(c1[1] + (c2[1] - c1[1]) * t),
            int(c1[2] + (c2[2] - c1[2]) * t))


def cmul(c, m):
    return (int(clamp(c[0] * m, 0, 255)),
            int(clamp(c[1] * m, 0, 255)),
            int(clamp(c[2] * m, 0, 255)))


def cadd(c, d):
    return (int(clamp(c[0] + d, 0, 255)),
            int(clamp(c[1] + d, 0, 255)),
            int(clamp(c[2] + d, 0, 255)))


def gray(c):
    g = (c[0] + c[1] + c[2]) // 3
    return (g, g, g)


def key_lerp(keys, t):
    """Interpolate through [(pos, value)] keyframes; values are colors or floats."""
    t %= 1.0
    for i in range(len(keys) - 1):
        t0, v0 = keys[i]
        t1, v1 = keys[i + 1]
        if t0 <= t <= t1:
            f = smooth((t - t0) / max(1e-6, t1 - t0))
            if isinstance(v0, (int, float)):
                return lerp(v0, v1, f)
            if isinstance(v0[0], tuple):
                return tuple(clerp(a, b, f) for a, b in zip(v0, v1))
            return clerp(v0, v1, f)
    return keys[-1][1]


def year_lerp(vals, yearpos):
    """4 seasonal values; hold for 70% of a season then blend into the next."""
    s = (yearpos * 4.0) % 4.0
    i = int(s)
    f = s - i
    a, b = vals[i], vals[(i + 1) % 4]
    k = smooth(clamp((f - 0.7) / 0.3, 0.0, 1.0))
    if isinstance(a, (int, float)):
        return lerp(a, b, k)
    return clerp(a, b, k)


# --------------------------------------------------------- alpha draw helpers
def fpoly(s, pts, col):
    ipts = [(int(p[0]), int(p[1])) for p in pts]
    if len(col) > 3 and col[3] < 255:
        gfx.filled_polygon(s, ipts, col)
    else:
        pygame.draw.polygon(s, col[:3], ipts)


def fell(s, cx, cy, rx, ry, col):
    rx, ry = max(1, int(rx)), max(1, int(ry))
    if len(col) > 3 and col[3] < 255:
        gfx.filled_ellipse(s, int(cx), int(cy), rx, ry, col)
    else:
        pygame.draw.ellipse(s, col[:3], (int(cx - rx), int(cy - ry), rx * 2, ry * 2))


def fcircle(s, cx, cy, r, col):
    fell(s, cx, cy, r, r, col)


def fline(s, p1, p2, col, width=1):
    if len(col) > 3 and col[3] < 255 and width <= 1:
        gfx.line(s, int(p1[0]), int(p1[1]), int(p2[0]), int(p2[1]), col)
    else:
        pygame.draw.line(s, col[:3], p1, p2, width)


# ----------------------------------------------------------------- glow cache
_glow_cache = {}


def glow(radius, color, intensity=1.0):
    """Additive glow sprite (blit with BLEND_RGB_ADD)."""
    radius = max(2, int(radius))
    key = (radius, color, round(intensity, 2))
    if key in _glow_cache:
        return _glow_cache[key]
    surf = pygame.Surface((radius * 2, radius * 2))
    for i in range(radius, 0, -1):
        f = (1.0 - i / radius) ** 2 * intensity
        pygame.draw.circle(surf, cmul(color, f), (radius, radius), i)
    _glow_cache[key] = surf
    return surf


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


# --------------------------------------------------------------------- camera
class Camera:
    def __init__(self):
        self.zoom, self.tzoom = 1.0, 1.0
        self.px, self.py = 0.0, 0.0
        self.tpx, self.tpy = 0.0, 0.0

    def update(self, rdt):
        k = clamp(rdt * 6.0, 0, 1)
        self.zoom += (self.tzoom - self.zoom) * k
        self.px += (self.tpx - self.px) * k
        self.py += (self.tpy - self.py) * k
        # keep the view inside the scene
        vw, vh = W / self.zoom, H / self.zoom
        mx, my = (W - vw) / 2, (H - vh) / 2
        self.tpx = clamp(self.tpx, -mx, mx)
        self.tpy = clamp(self.tpy, -my, my)

    def apply(self, scene, screen):
        if abs(self.zoom - 1.0) < 0.005 and abs(self.px) < 0.6 and abs(self.py) < 0.6:
            screen.blit(scene, (0, 0))
            return
        vw, vh = int(W / self.zoom), int(H / self.zoom)
        x = clamp(int(W / 2 + self.px - vw / 2), 0, W - vw)
        y = clamp(int(H / 2 + self.py - vh / 2), 0, H - vh)
        sub = scene.subsurface((x, y, vw, vh))
        screen.blit(pygame.transform.smoothscale(sub, (W, H)), (0, 0))


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
        # weather grading
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
        # sun / moon positions
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
        # god rays at low warm sun
        lowsun = clamp(1.0 - abs(dp - 0.16) / 0.16, 0, 1) + clamp(1.0 - abs(dp - 0.84) / 0.16, 0, 1)
        self.ray_alpha = 26.0 * clamp(lowsun, 0, 1) * (1.0 - cloud) * (1.0 - fog) * (1 - rain)
        self.dawn_glow = clamp(1.0 - abs(t - 0.25) / 0.07, 0, 1) + clamp(1.0 - abs(t - 0.755) / 0.07, 0, 1)


# --------------------------------------------------------------------- season
GRASS_YEAR = [(112, 175, 88), (92, 158, 74), (158, 138, 70), (124, 128, 96)]
FLOWER_YEAR = [1.0, 0.7, 0.3, 0.0]
LEAF_KEYS = [(0.0, 0.55), (0.06, 0.92), (0.12, 1.0), (0.55, 1.0), (0.65, 0.85),
             (0.71, 0.4), (0.75, 0.06), (0.96, 0.06), (1.0, 0.55)]
TEMP_YEAR = [12.0, 24.0, 10.0, -4.0]

# canopy palettes (dark, mid, highlight) per season; autumn resolved per-tree
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
AUTUMN_PALS = [
    ((150, 78, 34), (188, 106, 44), (224, 148, 66)),    # orange
    ((136, 52, 36), (176, 72, 44), (212, 108, 62)),     # red
    ((150, 116, 40), (192, 152, 52), (228, 196, 84)),   # gold
    ((122, 96, 44), (162, 132, 56), (204, 176, 88)),    # ochre
]


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
        c = year_lerp(GRASS_YEAR, self.year)
        return c

    def canopy(self, kind, autumn_idx, huev):
        if kind == "pine":
            pal = PINE_PAL
        elif kind == "birch":
            pal = BIRCH_PAL
        else:
            pal = OAK_PAL
        aut = AUTUMN_PALS[autumn_idx % len(AUTUMN_PALS)] if kind != "pine" else pal["summer"]
        if kind == "birch":
            aut = AUTUMN_PALS[2]  # birches always go gold
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
        self.bolts = []          # [pts, ttl]
        self.bolt_timer = 6.0

    def _pick_next(self):
        season = self.f.season.idx
        opts = []
        for kind, wgt in WEATHER_NEXT[self.kind]:
            if season == 3 and kind == "Storm":
                wgt *= 0.25
            if season == 2:      # autumn: moodier
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
        # lightning
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


# ------------------------------------------------------------------ particles
class Particle:
    __slots__ = ("kind", "x", "y", "vx", "vy", "ttl", "age", "size", "col", "gy", "ph")

    def __init__(self, kind, x, y, vx=0, vy=0, ttl=2.0, size=2, col=(255, 255, 255), gy=1e9, ph=0.0):
        self.kind, self.x, self.y = kind, x, y
        self.vx, self.vy = vx, vy
        self.ttl, self.age = ttl, 0.0
        self.size, self.col, self.gy, self.ph = size, col, gy, ph

    def update(self, dt, f):
        """Returns a spawned particle or None; sets ttl <= 0 when done."""
        self.age += dt
        k = self.kind
        if k == "rain":
            self.x += self.vx * dt
            self.y += self.vy * dt
            if self.y >= self.gy:
                self.ttl = 0
                return Particle("splash", self.x, self.gy, ttl=0.3, size=2)
        elif k == "snow":
            self.x += (self.vx + math.sin(self.age * 2.2 + self.ph) * 14) * dt
            self.y += self.vy * dt
            if self.y >= self.gy:
                self.kind = "settle"
                self.ttl = 1.6
                self.age = 0
        elif k in ("leaf", "petal"):
            self.x += (self.vx + math.sin(self.age * 3.0 + self.ph) * 22) * dt
            self.y += self.vy * dt
            self.ph += dt * 4
            if self.y >= self.gy:
                self.kind = "settle"
                self.ttl = 2.8
                self.age = 0
        elif k == "drop":
            self.vy += 500 * dt
            self.x += self.vx * dt
            self.y += self.vy * dt
            self.ttl -= dt
        elif k in ("splash", "settle", "mote", "spark"):
            self.x += self.vx * dt
            self.y += self.vy * dt
            self.ttl -= dt
        if k in ("rain", "snow", "leaf", "petal") and self.age > 14:
            self.ttl = 0
        return None

    def draw(self, s, f):
        k = self.kind
        if k == "rain":
            gfx.line(s, int(self.x), int(self.y),
                     int(self.x - self.vx * 0.014), int(self.y - 9), (170, 198, 228, 130))
        elif k == "snow":
            fcircle(s, self.x, self.y, self.size, (244, 248, 255, 210))
        elif k == "leaf":
            a = math.sin(self.age * 5 + self.ph)
            fline(s, (self.x - 2 * a, self.y - 1), (self.x + 2 * a, self.y + 1), self.col + (220,), 2)
        elif k == "petal":
            fcircle(s, self.x, self.y, 1, self.col + (200,))
        elif k == "splash":
            r = self.age * 26
            a = int(clamp(120 * (1 - self.age / 0.3), 0, 255))
            if a > 4:
                gfx.ellipse(s, int(self.x), int(self.y), max(1, int(r)), max(1, int(r * 0.42)),
                            (210, 230, 245, a))
        elif k == "settle":
            a = int(clamp(200 * (self.ttl / 2.8), 0, 255))
            fcircle(s, self.x, self.y, self.size, self.col + (a,))
        elif k == "mote":
            tw = 0.5 + 0.5 * math.sin(self.age * 2.4 + self.ph)
            a = int(90 * tw * clamp(self.ttl, 0, 1))
            if a > 4:
                fcircle(s, self.x, self.y, 1, (255, 244, 200, a))
        elif k == "drop":
            fcircle(s, self.x, self.y, 1, (214, 234, 246, int(clamp(self.ttl * 300, 0, 190))))

# -------------------------------------------------------------------- terrain
def lerp2(p1, p2, t):
    return (p1[0] + (p2[0] - p1[0]) * t, p1[1] + (p2[1] - p1[1]) * t)


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
        # synchronous first render
        P = self._params()
        self._pkey = self._param_key(P)
        for _ in self._render(P):
            pass
        self._build_water_static()

    def add_ripple(self):
        if self.wtiles and self.f.season.ice < 0.5:
            gx, gy, pts, cx, cy = self.f.rng.choice(self.wtiles)
            self.ripples.append([cx, cy, 0.0])

    # ------------------------------------------------------------- generation
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
        # remove lonely tiles / fill pinholes
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
        # soft banks
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
        # flow toward the front of the island so the waterfall faces the viewer
        vx, vy = (G - 2) - cx + rr.uniform(-4, 4), (G - 2) - cy + rr.uniform(-4, 4)
        m = math.hypot(vx, vy)
        if m < 0.5:
            vx, vy = 0.707, 0.707
        else:
            vx, vy = vx / m, vy / m
        # start at the pond tile most aligned with that direction
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
                    # reached the cliff edge — a waterfall!
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

    # ---------------------------------------------------------------- queries
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

    # -------------------------------------------------------------- rendering
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
        # puddles
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
        # ripples
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
        # ---- side faces
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
        # ---- top
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
        # ambient occlusion strips from taller neighbours behind
        if gy > 0 and self.land[gx][gy - 1] and self.elev[gx][gy - 1] > e:
            fpoly(s, (A, B, lerp2(B, D, 0.18), lerp2(A, C, 0.18)), (20, 30, 24, 46))
        if gx > 0 and self.land[gx - 1][gy] and self.elev[gx - 1][gy] > e:
            fpoly(s, (A, D, lerp2(D, B, 0.18), lerp2(A, C, 0.18)), (20, 30, 24, 40))
        # front lip highlight where the tile drops off
        fr = gx + 1 >= GRID or not self.land[gx + 1][gy] or self.elev[gx + 1][gy] < e \
            if gx + 1 < GRID else True
        fl = gy + 1 >= GRID or not self.land[gx][gy + 1] or self.elev[gx][gy + 1] < e \
            if gy + 1 < GRID else True
        if fr:
            fline(s, B, C, cadd(col, 22) + (170,), 1)
        if fl:
            fline(s, C, D, cadd(col, 22) + (170,), 1)
        # speckle detail
        rr = random.Random(int(h * 100000) + gx * 57 + gy)
        cx4 = (A[0] + C[0]) / 2
        cy4 = (A[1] + C[1]) / 2
        if snowc < 0.5:
            for _ in range(2):
                px = cx4 + rr.uniform(-HW * 0.55, HW * 0.55)
                py = cy4 + rr.uniform(-HH * 0.55, HH * 0.55)
                dv = rr.choice((-26, -18, 20))
                fline(s, (px, py), (px + rr.uniform(-2, 2), py - rr.uniform(1, 3)),
                      cadd(col, dv) + (200,), 1)
        else:
            for _ in range(2):
                px = cx4 + rr.uniform(-HW * 0.5, HW * 0.5)
                py = cy4 + rr.uniform(-HH * 0.5, HH * 0.5)
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
        # embedded rocks
        for _ in range(rr.randint(0, 2)):
            rx = lerp(p1[0], p2[0], rr.uniform(0.2, 0.8))
            ry = lerp(p1[1], p2[1], rr.uniform(0.2, 0.8)) + drop * rr.uniform(0.25, 0.85)
            rw = rr.uniform(2, 5)
            fell(s, rx, ry, rw, rw * 0.7, cmul((132, 128, 132), lit))
            fell(s, rx - rw * 0.3, ry - rw * 0.3, rw * 0.5, rw * 0.35, cmul((160, 156, 158), lit))
        # hanging roots
        if rr.random() < 0.45:
            rx = lerp(p1[0], p2[0], rr.uniform(0.25, 0.75))
            ry = lerp(p1[1], p2[1], rr.uniform(0.25, 0.75)) + 2
            px, py = rx, ry
            for i in range(4):
                nx2 = px + rr.uniform(-3, 3)
                ny2 = py + drop * 0.06
                fline(s, (px, py), (nx2, ny2), cmul((70, 50, 36), lit), 1)
                px, py = nx2, ny2
        # moss near the lip
        if moist > 0.4:
            for _ in range(3):
                mx = lerp(p1[0], p2[0], rr.random())
                my = lerp(p1[1], p2[1], rr.random()) + rr.uniform(2, drop * 0.12)
                fcircle(s, mx, my, rr.uniform(1, 2), cmul((92, 140, 70), lit + 0.1))
        # grass overhang at the lip
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

    # ------------------------------------------------------------------ water
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
        # puddles sit directly on grass tiles
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
            # drifting glints
            for i, (gx, gy, pts, cx, cy) in enumerate(self.wtiles):
                if i % 3 == 0:
                    ph = f.anim_t * 2.1 + i * 1.31
                    ox2 = math.sin(ph) * 6
                    oy2 = math.cos(ph * 0.7) * 2
                    fline(wl, (cx - 5 + ox2, cy + oy2), (cx + 4 + ox2, cy + oy2 * 0.5),
                          (188, 224, 238, 110), 1)
            # stream flow
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
        # ripples
        for x2, y2, age in self.ripples:
            fr = age / 1.2
            a = int(120 * (1 - fr))
            if a > 6:
                gfx.ellipse(wl, int(x2), int(y2), max(1, int(fr * 18)), max(1, int(fr * 8)),
                            (214, 236, 244, a))
        # tree reflections
        for tr in (f.pond_trees if ice < 0.5 else ()):
            if tr.refl is not None and not tr.dead:
                bx, by = isoS(tr.gx, tr.gy, self.elev_px(tr.gx, tr.gy))
                wsp = tr.refl.get_width()
                wl.blit(tr.refl, (bx - self.wbox.x - wsp // 2, by - self.wbox.y + 1))
        # moon / sun glint
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

# ------------------------------------------------------------------- entities
class Entity:
    def __init__(self, f, gx, gy):
        self.f = f
        self.gx, self.gy = gx, gy
        self.z = 0.0
        self.dead = False

    @property
    def depth(self):
        return self.gx + self.gy

    def pos(self):
        return self.f.iso(self.gx, self.gy, self.f.terrain.elev_px(self.gx, self.gy) + self.z)

    def base(self):
        return self.f.iso(self.gx, self.gy, self.f.terrain.elev_px(self.gx, self.gy))

    def update(self, sdt):
        pass

    def draw(self, s):
        pass


def draw_shadow(s, f, x, y, wdt, inten=1.0):
    a = int((13 + 46 * f.light.sun_strength) * inten)
    if a <= 2:
        return
    dx = f.light.shadow_dx * wdt * 0.045
    fell(s, x + dx, y + 1, wdt, max(2, wdt * 0.36), (22, 32, 26, a))


def swayv(f, phase, scale=1.0):
    return math.sin(f.wind_phase + phase) * (0.6 + 3.6 * f.weather.windv) * scale


# ----------------------------------------------------------------------- tree
TSTAGES = ("seed", "sapling", "young", "adult", "old", "dead", "decay")
TSCALE = dict(seed=0.06, sapling=0.30, young=0.62, adult=1.0, old=1.07, dead=1.05, decay=1.0)
TDUR = dict(seed=0.35, sapling=1.1, young=2.2, adult=9.0, old=4.5, dead=1.6, decay=0.9)


class Tree(Entity):
    def __init__(self, f, gx, gy, kind=None, stage="seed", warm=False):
        super().__init__(f, gx, gy)
        rng = f.rng
        if kind is None:
            e = f.terrain.elev[int(gx)][int(gy)]
            roll = rng.random() + e * 0.14
            kind = "pine" if roll > 0.95 else ("birch" if rng.random() < 0.22 else "oak")
        self.kind = kind
        self.sseed = rng.randint(0, 10 ** 6)
        self.sizevar = rng.uniform(0.82, 1.22)
        self.phase = rng.uniform(0, TAU)
        self.huev = rng.uniform(-12, 12)
        self.autumn_idx = rng.randint(0, 3)
        self.stage = stage
        self.st_age = rng.uniform(0, TDUR[stage] * 0.9) if warm else 0.0
        self.durs = {k: v * rng.uniform(0.8, 1.3) for k, v in TDUR.items()}
        self.seedt = rng.uniform(0.6, 2.0)
        self.trunk = None
        self.canopy = None
        self.refl = None
        self._key = None
        self._chk = rng.uniform(0, 1.5)
        self.fade = 1.0
        self.canopy_r = 0
        self.trunk_h = 0
        self._rebuild()

    def alive(self):
        return self.stage not in ("dead", "decay")

    def scale(self):
        i = TSTAGES.index(self.stage)
        s0 = TSCALE[self.stage]
        if self.stage in ("dead", "decay"):
            return s0
        s1 = TSCALE[TSTAGES[min(i + 1, 4)]]
        t = clamp(self.st_age / self.durs[self.stage], 0, 1)
        return lerp(s0, s1, t)

    def update(self, sdt):
        f = self.f
        dtd = sdt / DAY_LEN
        self.st_age += dtd
        if self.st_age > self.durs[self.stage]:
            i = TSTAGES.index(self.stage)
            if i + 1 >= len(TSTAGES):
                self.dead = True
                return
            self.stage = TSTAGES[i + 1]
            self.st_age = 0.0
            self._key = None
        if self.stage == "decay":
            self.fade = clamp(1.0 - self.st_age / self.durs["decay"], 0, 1)
        # seed drop
        if self.stage in ("adult", "old"):
            self.seedt -= dtd
            if self.seedt <= 0:
                self.seedt = f.rng.uniform(0.8, 2.4)
                f.try_seed(self)
        # falling leaves / petals
        if self.alive() and self.kind != "pine" and self.scale() > 0.4:
            aut = f.season.autumn_fall
            if aut > 0.05 and f.rng.random() < sdt * aut * 0.7:
                self._drop_leaf()
            if f.season.year < 0.1 and f.rng.random() < sdt * 0.12:
                self._drop_leaf(petal=True)
        self._chk -= sdt
        if self._chk <= 0:
            self._chk = 1.4 + (self.sseed % 100) * 0.01
            self._rebuild()

    def _drop_leaf(self, petal=False):
        f = self.f
        bx, by = self.base()
        r = self.canopy_r
        x = bx + f.rng.uniform(-r, r)
        y = by - self.trunk_h - f.rng.uniform(0, r)
        if petal:
            col = (244, 190, 205)
        else:
            col = AUTUMN_PALS[self.autumn_idx][1]
        f.particles.append(Particle("leaf" if not petal else "petal", x, y,
                                    vx=f.weather.windv * 26, vy=f.rng.uniform(20, 34),
                                    col=col, gy=by + f.rng.uniform(-3, 3),
                                    ph=f.rng.uniform(0, TAU)))

    def perch(self):
        rr = random.Random(self.sseed + 7)
        return (self.gx + rr.uniform(-0.3, 0.3), self.gy + rr.uniform(-0.3, 0.3),
                self.trunk_h + self.canopy_r * 0.9)

    # ------------------------------------------------------------ tree sprite
    def _rebuild(self):
        f = self.f
        sc = self.scale() * self.sizevar
        key = (self.stage, int(sc * 24), int(f.season.leaf * 8),
               int(f.season.snow * 6), int(f.season.year * 48))
        if key == self._key:
            return
        self._key = key
        if sc < 0.09:
            self.trunk = self.canopy = self.refl = None
            return
        if self.kind == "pine":
            self._build_pine(sc)
        else:
            self._build_leafy(sc)
        if self.canopy is not None:
            wdt, hgt = self.canopy.get_size()
            self.refl = pygame.transform.smoothscale(
                pygame.transform.flip(self.canopy, False, True), (wdt, max(2, int(hgt * 0.55))))
            self.refl.set_alpha(60)
        else:
            self.refl = None

    def _build_leafy(self, sc):
        f = self.f
        birch = self.kind == "birch"
        trunk_h = max(5, int((34 if not birch else 38) * sc))
        R = max(3, int((29 if not birch else 23) * sc))
        self.canopy_r = R
        self.trunk_h = trunk_h
        tw = max(2, int((6 if not birch else 4) * sc))
        tsw = tw * 2 + 10
        tsh = trunk_h + 4
        ts = pygame.Surface((tsw, tsh), pygame.SRCALPHA)
        cx = tsw // 2
        dead = not self.alive()
        tcol = (108, 100, 94) if dead else ((212, 210, 202) if birch else (98, 72, 52))
        fpoly(ts, ((cx - tw, tsh), (cx - max(1, tw * 0.45), 2),
                   (cx + max(1, tw * 0.45), 2), (cx + tw, tsh)), tcol)
        fpoly(ts, ((cx - tw, tsh), (cx - tw - 3, tsh), (cx - tw * 0.3, tsh - 4)), tcol)
        fpoly(ts, ((cx + tw, tsh), (cx + tw + 3, tsh), (cx + tw * 0.3, tsh - 4)), tcol)
        fline(ts, (cx - tw + 1, tsh - 2), (cx - max(1, tw * 0.4), 3), cmul(tcol, 0.7), 1)
        if birch and not dead:
            rr = random.Random(self.sseed)
            for _ in range(3):
                yy = rr.uniform(4, tsh - 4)
                fline(ts, (cx - tw * 0.6, yy), (cx + tw * 0.6, yy + 1), (60, 58, 54), 1)
        self.trunk = ts
        self.trunk_anchor = (cx, tsh)
        leaf = self.f.season.leaf
        rr = random.Random(self.sseed)
        cw = int(R * 2.9) + 8
        ch = int(R * 2.4) + 8
        cs = pygame.Surface((cw, ch), pygame.SRCALPHA)
        ccx, ccy = cw / 2, ch * 0.55
        if dead or leaf < 0.12:
            # bare branches (they still sway)
            n = 4 + int(sc * 3)
            bcol = (96, 88, 82) if dead else (98, 78, 60)
            snow = self.f.season.snow
            for i in range(n):
                a = -math.pi / 2 + rr.uniform(-1.1, 1.1)
                ln = R * rr.uniform(0.7, 1.3)
                x2 = ccx + math.cos(a) * ln
                y2 = ch - 2 + math.sin(a) * ln
                fline(cs, (ccx, ch - 2), (x2, y2), bcol, max(1, int(sc * 2)))
                x3 = x2 + math.cos(a + rr.uniform(-0.7, 0.7)) * ln * 0.5
                y3 = y2 + math.sin(a + rr.uniform(-0.7, 0.7)) * ln * 0.5
                fline(cs, (x2, y2), (x3, y3), bcol, 1)
                if snow > 0.15:
                    fline(cs, (x2 - 2, y2 - 1), (x2 + 2, y2 - 1),
                          (240, 246, 252, int(200 * snow)), 1)
            self.canopy = cs
            self.canopy_anchor = (ccx, ch - 2)
            return
        dark, mid, hi = self.f.season.canopy(self.kind, self.autumn_idx, self.huev)
        n = 4 + int(sc * 3)
        blobs = []
        for i in range(n):
            a = rr.uniform(0, TAU)
            d = rr.uniform(0, 0.72)
            bx = ccx + math.cos(a) * d * R * 0.95
            by = ccy + math.sin(a) * d * R * 0.45 - d * R * 0.1
            br = R * rr.uniform(0.42, 0.72) * (0.72 + 0.28 * leaf)
            blobs.append((by, bx, br, rr.random()))
        blobs.sort()
        snow = self.f.season.snow
        for by, bx, br, thr in blobs:
            if leaf < 0.5 and thr > leaf * 1.6:
                continue
            fell(cs, bx + 1.5, by + 2, br * 1.04, br * 0.86, dark)
            fell(cs, bx, by, br * 0.94, br * 0.78, mid)
            fell(cs, bx - br * 0.28, by - br * 0.3, br * 0.5, br * 0.4, hi)
            if snow > 0.12:
                fell(cs, bx, by - br * 0.42, br * 0.7, br * 0.26,
                     (240, 246, 252, int(210 * clamp(snow * 1.3, 0, 1))))
        # spring blossoms
        if self.f.season.year < 0.12 or self.f.season.year > 0.97:
            for _ in range(int(n * 2.5)):
                a = rr.uniform(0, TAU)
                d = rr.uniform(0, 0.8)
                fcircle(cs, ccx + math.cos(a) * d * R, ccy + math.sin(a) * d * R * 0.5 - 2,
                        max(1, int(sc * 2)), (247, 199, 210, 230))
        self.canopy = cs
        self.canopy_anchor = (ccx, ch * 0.72)

    def _build_pine(self, sc):
        R = max(3, int(19 * sc))
        hgt = int(56 * sc) + 8
        self.canopy_r = R
        self.trunk_h = max(3, int(9 * sc))
        tw = max(2, int(4 * sc))
        ts = pygame.Surface((tw * 2 + 6, self.trunk_h + 3), pygame.SRCALPHA)
        fpoly(ts, ((3, self.trunk_h + 3), (3 + tw * 2, self.trunk_h + 3),
                   (3 + tw * 1.6, 0), (3 + tw * 0.4, 0)), (90, 64, 46))
        self.trunk = ts
        self.trunk_anchor = (3 + tw, self.trunk_h + 3)
        dead = not self.alive()
        dark, mid, hi = self.f.season.canopy("pine", 0, self.huev)
        if dead:
            dark, mid, hi = (92, 84, 78), (108, 100, 92), (124, 116, 106)
        cw, ch = R * 2 + 8, hgt + 6
        cs = pygame.Surface((cw, ch), pygame.SRCALPHA)
        ccx = cw / 2
        tiers = 4
        snow = self.f.season.snow
        for i in range(tiers):
            fr = i / tiers
            wdt = R * (1.0 - fr * 0.66)
            y0 = ch - 2 - (hgt - 8) * fr
            y1 = y0 - (hgt / tiers) * 1.6
            fpoly(cs, ((ccx - wdt, y0), (ccx, y1), (ccx + wdt, y0)), dark)
            fpoly(cs, ((ccx - wdt * 0.85, y0 - 1), (ccx, y1 + 2), (ccx, y0 - 1)), mid)
            fline(cs, (ccx - wdt * 0.7, y0 - 2), (ccx, y1 + 3), hi, 1)
            if snow > 0.12:
                a = int(220 * clamp(snow * 1.3, 0, 1))
                fline(cs, (ccx - wdt * 0.9, y0 - 1), (ccx, y1 + 1), (242, 247, 252, a), 2)
                fline(cs, (ccx, y1 + 1), (ccx + wdt * 0.9, y0 - 1), (248, 251, 255, a), 1)
        self.canopy = cs
        self.canopy_anchor = (ccx, ch - 2)

    def draw(self, s):
        f = self.f
        bx, by = self.base()
        sc = self.scale() * self.sizevar
        if self.trunk is None:
            # a tiny sprout
            sw = swayv(f, self.phase, 0.4)
            fline(s, (bx, by), (bx + sw, by - 4), (96, 150, 70), 1)
            fcircle(s, bx + sw - 1, by - 4, 1, (128, 186, 92))
            fcircle(s, bx + sw + 1, by - 4, 1, (128, 186, 92))
            return
        if self.alive():
            draw_shadow(s, f, bx, by, self.canopy_r * 1.7 + 3, self.fade)
        if self.fade < 1.0:
            self.trunk.set_alpha(int(255 * self.fade))
            if self.canopy is not None:
                self.canopy.set_alpha(int(255 * self.fade))
        ta = self.trunk_anchor
        s.blit(self.trunk, (bx - ta[0], by - ta[1]))
        if self.canopy is not None:
            amp = 0.45 + 0.55 * clamp(sc, 0, 1)
            sw = swayv(f, self.phase, amp)
            swy = math.sin(f.wind_phase * 0.7 + self.phase) * 0.7
            ca = self.canopy_anchor
            s.blit(self.canopy, (bx - ca[0] + sw, by - self.trunk_h - ca[1] + swy))


class SeedFluff(Entity):
    """A drifting seed released by an old tree."""

    def __init__(self, f, gx, gy, z):
        super().__init__(f, gx, gy)
        self.z = z
        self.vx = f.rng.uniform(-0.25, 0.25) + f.weather.windv * 0.5
        self.vy = f.rng.uniform(-0.25, 0.25)
        self.ph = f.rng.uniform(0, TAU)

    def update(self, sdt):
        f = self.f
        self.gx += self.vx * sdt * 0.5
        self.gy += self.vy * sdt * 0.5
        self.z -= sdt * 9
        self.ph += sdt * 5
        if self.z <= 0:
            self.dead = True
            f.plant_tree(self.gx, self.gy)

    def draw(self, s):
        x, y = self.pos()
        x += math.sin(self.ph) * 2
        fcircle(s, x, y, 1, (244, 240, 224, 220))
        fline(s, (x, y), (x + 2, y - 2), (244, 240, 224, 130), 1)


class Waterfall(Entity):
    def __init__(self, f, info):
        x, y, dx, dy = info
        super().__init__(f, x + 0.5 + dx * 0.5, y + 0.5 + dy * 0.5)
        self.tz = f.terrain.elev[x][y] * ELEV
        self.ph = 0.0

    def update(self, sdt):
        f = self.f
        if f.season.ice > 0.6:
            return
        if f.rng.random() < sdt * 5:
            x, y = self.f.iso(self.gx, self.gy, self.tz)
            f.particles.append(Particle("drop", x + f.rng.uniform(-3, 3), y + 4,
                                        vx=f.rng.uniform(-6, 6), vy=60, ttl=1.4))

    def draw(self, s):
        f = self.f
        x, y = f.iso(self.gx, self.gy, self.tz - 2)
        if f.season.ice > 0.6:
            fpoly(s, ((x - 4, y), (x + 4, y), (x + 3, y + 40), (x - 3, y + 40)),
                  (208, 228, 240, 150))
            return
        L = 120
        for i in range(3):
            ox = (i - 1) * 3.0
            wob = math.sin(f.anim_t * 3.2 + i * 2.1) * 3
            a = 95 - i * 22
            fpoly(s, ((x + ox - 2.4, y), (x + ox + 2.4, y),
                      (x + ox + 3 + wob, y + L), (x + ox - 3 + wob, y + L)),
                  (206, 230, 242, a))
        for i in range(3):
            yy = (f.anim_t * 110 + i * 43) % L
            aa = int(150 * (1 - yy / L))
            fcircle(s, x + math.sin(i * 5.1) * 3, y + yy, 1, (240, 248, 252, aa))
        fell(s, x, y + 1, 6, 2.4, (236, 246, 250, 170))
        mist = 0.6 + 0.4 * math.sin(f.anim_t * 1.7)
        fell(s, x, y + L, 10, 5, (220, 235, 245, int(60 * mist)))


# ---------------------------------------------------------------------- flora
class Bush(Entity):
    def __init__(self, f, gx, gy):
        super().__init__(f, gx, gy)
        self.sseed = f.rng.randint(0, 10 ** 6)
        self.r = f.rng.uniform(4.5, 8)
        self.maxr = f.rng.uniform(9, 14)
        self.phase = f.rng.uniform(0, TAU)

    def update(self, sdt):
        self.r = min(self.maxr, self.r + sdt / DAY_LEN * 0.5)

    def draw(self, s):
        f = self.f
        bx, by = self.base()
        r = self.r
        draw_shadow(s, f, bx, by, r * 1.2, 0.7)
        dark, mid, hi = f.season.canopy("oak", 3, -8)
        rr = random.Random(self.sseed)
        sw = swayv(f, self.phase, 0.3)
        yr = f.season.year
        snow = f.season.snow
        for i in range(3):
            ox = rr.uniform(-r * 0.5, r * 0.5) + sw * (0.5 + i * 0.2)
            oy = rr.uniform(-r * 0.18, r * 0.18)
            br = r * rr.uniform(0.55, 0.8)
            fell(s, bx + ox + 1, by - br * 0.5 + oy + 1, br, br * 0.8, dark)
            fell(s, bx + ox, by - br * 0.55 + oy, br * 0.88, br * 0.72, mid)
            fell(s, bx + ox - br * 0.3, by - br * 0.8 + oy, br * 0.4, br * 0.3, hi)
            if snow > 0.12:
                fell(s, bx + ox, by - br * 0.85 + oy, br * 0.6, br * 0.2,
                     (240, 246, 252, int(200 * clamp(snow * 1.3, 0, 1))))
        if 0.28 < yr < 0.5 and snow < 0.2:      # summer berries
            for i in range(4):
                fcircle(s, bx + rr.uniform(-r * 0.6, r * 0.6) + sw,
                        by - r * 0.5 + rr.uniform(-r * 0.3, r * 0.3), 1, (198, 62, 66))
        elif yr < 0.1 and snow < 0.2:           # spring blooms
            for i in range(4):
                fcircle(s, bx + rr.uniform(-r * 0.6, r * 0.6) + sw,
                        by - r * 0.6 + rr.uniform(-r * 0.3, r * 0.3), 1, (246, 240, 244))


class GrassTuft(Entity):
    def __init__(self, f, gx, gy):
        super().__init__(f, gx, gy)
        rr = f.rng
        self.phase = rr.uniform(0, TAU)
        self.blades = [(rr.uniform(-3, 3), rr.uniform(5, 10), rr.uniform(-2, 2),
                        rr.uniform(-0.14, 0.14)) for _ in range(3)]

    def draw(self, s):
        f = self.f
        snow = f.season.snow
        bx, by = self.base()
        sw = swayv(f, self.phase + bx * 0.011, 1.4)
        g = f.season.grass_color()
        if snow > 0.7:
            fline(s, (bx, by), (bx + sw * 0.4, by - 4), (172, 176, 150, 190), 1)
            return
        for i, (dx, ln, bend, dv) in enumerate(self.blades):
            col = cadd(g, int(dv * 180) + 14)
            if snow > 0.2:
                col = clerp(col, (210, 214, 200), snow)
            tip = (bx + dx + bend + sw * (0.7 + i * 0.2), by - ln)
            fline(s, (bx + dx * 0.4, by), tip, col + (235,), 1)


class Flower(Entity):
    COLS = ((242, 122, 152), (250, 202, 92), (188, 142, 232), (246, 246, 240), (240, 152, 74))

    def __init__(self, f, gx, gy):
        super().__init__(f, gx, gy)
        self.col = f.rng.choice(self.COLS)
        self.h = f.rng.uniform(6, 10)
        self.phase = f.rng.uniform(0, TAU)
        self.bloom = 0.0

    def update(self, sdt):
        f = self.f
        if f.season.flowerf <= 0.02 or f.season.snow > 0.4:
            self.bloom -= sdt / DAY_LEN * 6
            if self.bloom <= 0:
                self.dead = True
            return
        self.bloom = clamp(self.bloom + sdt / DAY_LEN * 4, 0, 1)

    def draw(self, s):
        f = self.f
        bx, by = self.base()
        sw = swayv(f, self.phase, 0.9)
        tipx, tipy = bx + sw, by - self.h
        fline(s, (bx, by), (tipx, tipy), (68, 120, 58), 1)
        fline(s, (bx + sw * 0.4, by - self.h * 0.45),
              (bx + sw * 0.4 + 3, by - self.h * 0.45 - 1), (68, 120, 58), 1)
        b = self.bloom * clamp(f.season.flowerf * 2.2, 0, 1)
        if b < 0.1:
            fcircle(s, tipx, tipy, 1, cmul(self.col, 0.6))
            return
        day = 1.0 - f.light.night
        pr = (1.4 + 1.5 * b) * (0.65 + 0.35 * day)
        for i in range(4):
            a = i * TAU / 4 + 0.5
            fcircle(s, tipx + math.cos(a) * pr, tipy + math.sin(a) * pr * 0.7,
                    max(1, pr * 0.8), self.col)
        fcircle(s, tipx, tipy, max(1, pr * 0.55), (252, 220, 96))


class Fern(Entity):
    def __init__(self, f, gx, gy):
        super().__init__(f, gx, gy)
        rr = f.rng
        self.phase = rr.uniform(0, TAU)
        self.fronds = [(rr.uniform(-1.4, 1.4), rr.uniform(7, 13)) for _ in range(5)]

    def draw(self, s):
        f = self.f
        if f.season.snow > 0.55:
            return
        bx, by = self.base()
        yr = f.season.year
        col = year_lerp([(52, 118, 62), (44, 108, 56), (136, 104, 48), (96, 84, 52)], yr)
        sw = swayv(f, self.phase, 0.5)
        for dx, ln in self.fronds:
            mx = bx + dx * ln * 0.45 + sw * 0.5
            my = by - ln * 0.7
            ex = bx + dx * ln * 0.9 + sw
            ey = by - ln * 0.35
            fline(s, (bx, by), (mx, my), col, 1)
            fline(s, (mx, my), (ex, ey), col, 1)
            fline(s, (mx, my), (mx + dx, my - 2), cadd(col, 24), 1)


class Mushroom(Entity):
    def __init__(self, f, gx, gy):
        super().__init__(f, gx, gy)
        self.glowing = f.rng.random() < 0.45
        self.cap = (112, 194, 182) if self.glowing else (198, 74, 62)
        self.size = f.rng.uniform(0.7, 1.2)
        self.age_d = 0.0
        self.life = f.rng.uniform(3, 8)
        self.phase = f.rng.uniform(0, TAU)

    def update(self, sdt):
        self.age_d += sdt / DAY_LEN
        if self.age_d > self.life:
            self.dead = True

    def draw(self, s):
        f = self.f
        bx, by = self.base()
        grow = clamp(self.age_d * 6, 0.3, 1) * self.size
        hgt = 4.5 * grow
        cw = 4.6 * grow
        pygame.draw.rect(s, (224, 216, 198),
                         (int(bx - 1), int(by - hgt), max(1, int(2 * grow)), int(hgt)))
        fell(s, bx, by - hgt, cw, cw * 0.55, self.cap)
        fell(s, bx - cw * 0.3, by - hgt - cw * 0.15, cw * 0.4, cw * 0.2, cadd(self.cap, 34))
        if not self.glowing:
            fcircle(s, bx - 1, by - hgt - 1, 1, (244, 240, 236))
            fcircle(s, bx + 2, by - hgt, 1, (244, 240, 236))
        elif f.light.night > 0.4:
            pulse = 0.6 + 0.4 * math.sin(f.anim_t * 1.8 + self.phase)
            f.glow_req.append((bx, by - hgt, 9 + 3 * pulse, (46, 178, 152),
                               f.light.night * pulse * 0.8))


class RockBig(Entity):
    def __init__(self, f, gx, gy):
        super().__init__(f, gx, gy)
        rr = random.Random(f.rng.randint(0, 10 ** 6))
        self.rr = rr.randint(0, 10 ** 6)
        self.w = rr.uniform(8, 15)

    def draw(self, s):
        f = self.f
        bx, by = self.base()
        rr = random.Random(self.rr)
        wdt = self.w
        hgt = wdt * rr.uniform(0.65, 0.95)
        draw_shadow(s, f, bx, by + 1, wdt * 1.15, 0.8)
        snow = f.season.snow
        base_pts = [(bx - wdt, by - hgt * 0.25), (bx - wdt * 0.55, by - hgt),
                    (bx + wdt * 0.2, by - hgt * 1.05), (bx + wdt * 0.95, by - hgt * 0.45),
                    (bx + wdt * 0.8, by + hgt * 0.16), (bx - wdt * 0.5, by + hgt * 0.18)]
        fpoly(s, base_pts, (92, 90, 98))
        fpoly(s, ((bx - wdt * 0.55, by - hgt), (bx + wdt * 0.2, by - hgt * 1.05),
                  (bx + wdt * 0.5, by - hgt * 0.5), (bx - wdt * 0.3, by - hgt * 0.42)),
              (138, 136, 142))
        fpoly(s, ((bx - wdt, by - hgt * 0.25), (bx - wdt * 0.55, by - hgt),
                  (bx - wdt * 0.3, by - hgt * 0.42), (bx - wdt * 0.5, by + hgt * 0.1)),
              (116, 114, 122))
        fline(s, (bx - wdt * 0.3, by - hgt * 0.42), (bx - wdt * 0.1, by + hgt * 0.1),
              (78, 76, 84), 1)
        if snow > 0.12:
            fpoly(s, ((bx - wdt * 0.55, by - hgt), (bx + wdt * 0.2, by - hgt * 1.05),
                      (bx + wdt * 0.5, by - hgt * 0.5), (bx - wdt * 0.3, by - hgt * 0.42)),
                  (240, 245, 251, int(220 * clamp(snow * 1.3, 0, 1))))
        for _ in range(2):
            fcircle(s, bx + rr.uniform(-wdt * 0.5, wdt * 0.4),
                    by - hgt * rr.uniform(0.1, 0.5), 1.4, (96, 138, 76))


# ---------------------------------------------------------------------- fauna
class Animal(Entity):
    SPEED = 1.0
    RANGE = 5.0
    IDLE = (2.0, 7.0)

    def __init__(self, f, gx=None, gy=None):
        if gx is None:
            for _ in range(60):
                x = f.rng.uniform(3, GRID - 3)
                y = f.rng.uniform(3, GRID - 3)
                if f.terrain.walkable(x, y) and f.terrain.edged[int(x)][int(y)] >= 2:
                    gx, gy = x, y
                    break
            else:
                gx, gy = GRID / 2, GRID / 2
        super().__init__(f, gx, gy)
        self.state = "idle"
        self.timer = f.rng.uniform(0.5, 4)
        self.tx, self.ty = gx, gy
        self.fc = 1
        self.wphase = f.rng.uniform(0, TAU)
        self.wt = 0.0

    def pick_target(self):
        f = self.f
        for _ in range(14):
            a = f.rng.uniform(0, TAU)
            d = f.rng.uniform(1.2, self.RANGE)
            tx, ty = self.gx + math.cos(a) * d, self.gy + math.sin(a) * d
            if f.terrain.walkable(tx, ty) and f.terrain.edged[int(tx)][int(ty)] >= 2:
                return tx, ty
        return None

    def update(self, sdt):
        f = self.f
        self.wt += sdt
        if self.state == "idle":
            self.timer -= sdt
            if self.timer <= 0:
                t = self.pick_target()
                if t:
                    self.tx, self.ty = t
                    self.state = "walk"
                else:
                    self.timer = 2
        else:
            dx, dy = self.tx - self.gx, self.ty - self.gy
            dist = math.hypot(dx, dy)
            step = self.SPEED * sdt
            if dist < max(step, 0.05):
                self.state = "idle"
                self.timer = f.rng.uniform(*self.IDLE)
            else:
                nx = self.gx + dx / dist * step
                ny = self.gy + dy / dist * step
                if f.terrain.walkable(nx + dx / dist * 0.4, ny + dy / dist * 0.4):
                    self.gx, self.gy = nx, ny
                else:
                    self.state = "idle"
                    self.timer = f.rng.uniform(1, 3)
                sdx = (dx - dy)
                if abs(sdx) > 0.05:
                    self.fc = 1 if sdx > 0 else -1
                self.wphase += sdt * self.SPEED * 6


class Rabbit(Animal):
    SPEED = 1.7
    RANGE = 4.0
    IDLE = (1.5, 6.0)

    def draw(self, s):
        f = self.f
        x, y = self.pos()
        hop = abs(math.sin(self.wphase * 1.7)) * 3.2 if self.state == "walk" else 0
        draw_shadow(s, f, x, y, 5, 0.8)
        col = clerp((176, 156, 136), (226, 226, 230), f.season.snow)
        yb = y - 3 - hop
        fell(s, x, yb, 4.6, 3.2, col)
        fell(s, x + 3.4 * self.fc, yb - 2.4, 2.6, 2.2, col)
        er = -0.4 if self.state == "walk" else 0
        fline(s, (x + 3 * self.fc, yb - 4), (x + (3 + er) * self.fc, yb - 8), col, 2)
        fline(s, (x + 4.4 * self.fc, yb - 4), (x + (4.6 + er) * self.fc, yb - 7.6), col, 2)
        fcircle(s, x - 4 * self.fc, yb + 0.5, 1.4, (246, 246, 248))
        fcircle(s, x + 4.6 * self.fc, yb - 2.6, 1, (30, 26, 24))


class Deer(Animal):
    SPEED = 0.55
    RANGE = 7.0
    IDLE = (4.0, 12.0)

    def __init__(self, f):
        super().__init__(f)
        self.buck = f.rng.random() < 0.5

    def draw(self, s):
        f = self.f
        x, y = self.pos()
        draw_shadow(s, f, x, y, 8, 0.9)
        col = (152, 114, 78)
        yb = y - 8
        lw = math.sin(self.wphase) * 2.2 if self.state == "walk" else 0
        for i, ox in enumerate((-5, -2.6, 2.6, 5)):
            lx = x + ox + (lw if i % 2 == 0 else -lw) * 0.5
            fline(s, (x + ox, yb + 2), (lx, y), (118, 88, 60), 1)
        fell(s, x, yb, 7.5, 4.2, col)
        graze = self.state == "idle" and (self.wt % 9) < 4
        hx = x + 7 * self.fc
        hy = yb - 5 if not graze else yb + 3
        fline(s, (x + 5 * self.fc, yb - 2), (hx, hy), col, 3)
        fell(s, hx + self.fc, hy, 2.6, 1.9, col)
        if self.buck:
            fline(s, (hx, hy - 2), (hx - 2 * self.fc, hy - 6), (206, 186, 150), 1)
            fline(s, (hx + self.fc, hy - 2), (hx + 3 * self.fc, hy - 6), (206, 186, 150), 1)
        fcircle(s, x - 7 * self.fc, yb - 1, 1.4, (238, 234, 226))


class Fox(Animal):
    SPEED = 1.15
    IDLE = (1.0, 4.0)

    def __init__(self, f):
        super().__init__(f)
        self.wps = []
        c = GRID / 2
        for i in range(9):
            a = i / 9 * TAU
            r = GRID * 0.29
            x, y = c + math.cos(a) * r, c + math.sin(a) * r * 0.9
            if f.terrain.walkable(x, y):
                self.wps.append((x, y))
        self.wpi = 0

    def pick_target(self):
        if not self.wps:
            return super().pick_target()
        self.wpi = (self.wpi + 1) % len(self.wps)
        t = self.wps[self.wpi]
        return (t[0] + self.f.rng.uniform(-1.4, 1.4), t[1] + self.f.rng.uniform(-1.4, 1.4))

    def draw(self, s):
        f = self.f
        x, y = self.pos()
        draw_shadow(s, f, x, y, 6, 0.85)
        col = (216, 122, 58)
        yb = y - 4
        lw = math.sin(self.wphase) * 1.6 if self.state == "walk" else 0
        fline(s, (x - 3, yb + 2), (x - 3 + lw, y), (150, 84, 40), 1)
        fline(s, (x + 3, yb + 2), (x + 3 - lw, y), (150, 84, 40), 1)
        tb = math.sin(self.wt * 3 + self.wphase) * 1.2
        fell(s, x - 7 * self.fc, yb - 1 + tb * 0.4, 4, 1.9, col)
        fcircle(s, x - 10 * self.fc, yb - 1 + tb * 0.6, 1.6, (246, 242, 236))
        fell(s, x, yb, 6, 3, col)
        fell(s, x + 5.4 * self.fc, yb - 2.2, 2.4, 2, col)
        fpoly(s, ((x + 4.4 * self.fc, yb - 3.6), (x + 3.6 * self.fc, yb - 6.4),
                  (x + 5.4 * self.fc, yb - 4.4)), (190, 100, 44))
        fpoly(s, ((x + 6.4 * self.fc, yb - 3.6), (x + 7 * self.fc, yb - 6.2),
                  (x + 5 * self.fc, yb - 4.4)), (190, 100, 44))
        fcircle(s, x + 7.6 * self.fc, yb - 1.8, 1, (250, 246, 240))


class Bird(Entity):
    COLS = ((92, 142, 220), (222, 120, 92), (228, 198, 92), (150, 170, 190))

    def __init__(self, f):
        super().__init__(f, GRID / 2, GRID / 2)
        self.col = f.rng.choice(self.COLS)
        self.state = "fly"
        self.tree = None
        self.timer = 0.0
        self.wt = f.rng.uniform(0, 9)
        self.p0 = (f.rng.uniform(5, GRID - 5), f.rng.uniform(5, GRID - 5), 60.0)
        self.p1 = self.p0
        self.t = 1.0
        self.dur = 1.0
        self.fc = 1
        self._go_somewhere()

    def _perchable(self):
        f = self.f
        ok = [t for t in f.trees if t.alive() and t.stage in ("young", "adult", "old")]
        return f.rng.choice(ok) if ok else None

    def _go_somewhere(self):
        tr = self._perchable()
        if tr is None:
            self.p1 = (self.f.rng.uniform(5, GRID - 5), self.f.rng.uniform(5, GRID - 5), 50.0)
            self.tree = None
        else:
            self.tree = tr
            self.p1 = tr.perch()
        self.p0 = (self.gx, self.gy, self.z)
        d = math.hypot(self.p1[0] - self.p0[0], self.p1[1] - self.p0[1])
        self.dur = max(1.4, d * 0.5)
        self.t = 0.0
        self.state = "fly"

    def update(self, sdt):
        f = self.f
        self.wt += sdt
        if self.state == "perched":
            if self.tree is None or self.tree.dead or not self.tree.alive():
                self._go_somewhere()
                return
            p = self.tree.perch()
            self.gx, self.gy, self.z = p[0], p[1], p[2] + (abs(math.sin(self.wt * 6)) * 1.5
                                                           if (self.wt % 5) < 0.8 else 0)
            self.timer -= sdt
            storm = f.weather.rain > 0.7
            if self.timer <= 0 and not storm:
                self._go_somewhere()
        else:
            self.t += sdt / self.dur
            t = clamp(self.t, 0, 1)
            mx = (self.p0[0] + self.p1[0]) / 2
            my = (self.p0[1] + self.p1[1]) / 2
            mz = max(self.p0[2], self.p1[2]) + 34
            u = 1 - t
            self.gx = u * u * self.p0[0] + 2 * u * t * mx + t * t * self.p1[0]
            self.gy = u * u * self.p0[1] + 2 * u * t * my + t * t * self.p1[1]
            self.z = u * u * self.p0[2] + 2 * u * t * mz + t * t * self.p1[2]
            dx = (self.p1[0] - self.p0[0]) - (self.p1[1] - self.p0[1])
            self.fc = 1 if dx > 0 else -1
            if self.t >= 1:
                self.state = "perched"
                self.timer = f.rng.uniform(6, 22)

    def draw(self, s):
        f = self.f
        x, y = self.pos()
        if self.state == "fly":
            flap = math.sin(self.wt * 16)
            fell(s, x, y, 3.4, 2.4, self.col)
            fpoly(s, ((x - 1, y - 1), (x - 5, y - 1 - 5 * flap), (x + 1.6, y - 1.6)),
                  cadd(self.col, 20))
            fpoly(s, ((x - 1, y), (x - 5, y - 5 * flap), (x + 1.4, y - 0.5)),
                  cmul(self.col, 0.8))
        else:
            fell(s, x, y - 2, 3, 2.6, self.col)
            fline(s, (x - 2.4 * self.fc, y - 2), (x - 4.4 * self.fc, y - 1), cmul(self.col, 0.7), 2)
        fcircle(s, x + 2.6 * self.fc, y - 3.6, 1.7, cadd(self.col, 26))
        fline(s, (x + 3.8 * self.fc, y - 3.6), (x + 5.4 * self.fc, y - 3.2), (240, 190, 70), 1)


class Butterfly(Entity):
    COLS = ((242, 150, 60), (120, 170, 240), (240, 210, 90), (230, 130, 180))

    def __init__(self, f):
        super().__init__(f, GRID / 2, GRID / 2)
        self.col = f.rng.choice(self.COLS)
        self.wt = f.rng.uniform(0, 9)
        self.home = None
        self.retime = 0.0
        self.vis = 0.0
        self.z = 8

    def _active(self):
        f = self.f
        return (f.light.night < 0.4 and f.season.idx != 3 and f.weather.rain < 0.4
                and f.temp > 5)

    def update(self, sdt):
        f = self.f
        self.wt += sdt
        act = self._active()
        self.vis = clamp(self.vis + (sdt if act else -sdt) * 0.8, 0, 1)
        if self.vis <= 0:
            return
        self.retime -= sdt
        if self.home is None or self.retime <= 0:
            self.retime = f.rng.uniform(6, 15)
            fl = f.flowers
            if fl:
                h = f.rng.choice(fl)
                self.home = (h.gx, h.gy)
            else:
                self.home = (f.rng.uniform(6, GRID - 6), f.rng.uniform(6, GRID - 6))
        hx, hy = self.home
        self.gx += ((hx - self.gx) * 0.24 + math.sin(self.wt * 1.7) * 0.7) * sdt
        self.gy += ((hy - self.gy) * 0.24 + math.cos(self.wt * 1.3) * 0.7) * sdt
        self.z = 7 + math.sin(self.wt * 2.1) * 3.5

    def draw(self, s):
        if self.vis <= 0.02:
            return
        x, y = self.pos()
        a = int(230 * self.vis)
        wr = abs(math.sin(self.wt * 13)) * 2.6 + 0.6
        fell(s, x - wr * 0.7, y - 1, wr, 2, self.col + (a,))
        fell(s, x + wr * 0.7, y - 1, wr, 2, self.col + (a,))
        fline(s, (x, y - 2.4), (x, y + 1.4), (44, 38, 36, a), 1)


class Bee(Entity):
    def __init__(self, f):
        super().__init__(f, GRID / 2, GRID / 2)
        self.wt = f.rng.uniform(0, 9)
        self.home = None
        self.retime = 0.0
        self.vis = 0.0
        self.z = 6

    def _active(self):
        f = self.f
        return (f.light.night < 0.35 and f.season.idx in (0, 1) and f.weather.rain < 0.3
                and f.temp > 8)

    def update(self, sdt):
        f = self.f
        self.wt += sdt
        act = self._active()
        self.vis = clamp(self.vis + (sdt if act else -sdt), 0, 1)
        if self.vis <= 0:
            return
        self.retime -= sdt
        if self.home is None or self.retime <= 0:
            self.retime = f.rng.uniform(3, 8)
            fl = f.flowers
            if fl:
                h = f.rng.choice(fl)
                self.home = (h.gx, h.gy)
            else:
                self.home = (f.rng.uniform(6, GRID - 6), f.rng.uniform(6, GRID - 6))
        hx, hy = self.home
        self.gx += ((hx - self.gx) * 0.5 + math.sin(self.wt * 5.1) * 0.5) * sdt
        self.gy += ((hy - self.gy) * 0.5 + math.cos(self.wt * 4.3) * 0.5) * sdt
        self.z = 5 + math.sin(self.wt * 6.7) * 2

    def draw(self, s):
        if self.vis <= 0.02:
            return
        x, y = self.pos()
        a = int(240 * self.vis)
        fell(s, x, y, 2.4, 1.7, (240, 196, 60, a))
        fline(s, (x - 0.8, y - 1.6), (x - 0.8, y + 1.6), (40, 34, 30, a), 1)
        fline(s, (x + 0.8, y - 1.6), (x + 0.8, y + 1.6), (40, 34, 30, a), 1)
        wf = abs(math.sin(self.wt * 30))
        fell(s, x, y - 2.4, 1.8, 1 + wf, (230, 238, 244, int(a * 0.55)))


class Firefly(Entity):
    def __init__(self, f):
        super().__init__(f, 0, 0)
        for _ in range(40):
            x = f.rng.uniform(4, GRID - 4)
            y = f.rng.uniform(4, GRID - 4)
            if f.terrain.walkable(x, y):
                self.gx, self.gy = x, y
                break
        self.hx, self.hy = self.gx, self.gy
        self.wt = f.rng.uniform(0, 20)
        self.freq = f.rng.uniform(0.7, 1.6)
        self.ph = f.rng.uniform(0, TAU)
        self.z = f.rng.uniform(4, 16)
        self.vis = 0.0

    def update(self, sdt):
        f = self.f
        self.wt += sdt
        act = f.light.night > 0.55 and f.season.idx != 3 and f.weather.rain < 0.45
        self.vis = clamp(self.vis + (sdt if act else -sdt) * 0.5, 0, 1)
        if self.vis <= 0:
            return
        self.gx = self.hx + math.sin(self.wt * 0.31 + self.ph) * 2.4
        self.gy = self.hy + math.cos(self.wt * 0.23 + self.ph * 2) * 2.4
        self.z = 8 + math.sin(self.wt * 0.5 + self.ph) * 6

    def glow_pass(self):
        if self.vis <= 0.02:
            return
        f = self.f
        blink = max(0.0, math.sin(self.wt * self.freq * TAU * 0.28 + self.ph)) ** 3
        if blink < 0.03:
            return
        x, y = self.pos()
        f.glow_req.append((x, y, 6 + 4 * blink, (168, 240, 108), blink * self.vis))

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
            self.x = -self.w - rng_uniform_static()

    def vis(self, f):
        return clamp(f.weather.cloud * 1.7 - self.thr, 0, 1)

    def draw(self, s, f):
        v = self.vis(f)
        if v <= 0.03:
            return
        self.surf.set_alpha(int(215 * v))
        s.blit(self.surf, (int(self.x), int(self.y + math.sin(f.anim_t * 0.1 + self.thr * 9) * 3)))


def rng_uniform_static():
    return random.uniform(0, 120)


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


# ------------------------------------------------------------------------ hud
WEATHER_DOTS = {
    "Sunny": (255, 214, 96), "Cloudy": (190, 198, 210), "Windy": (170, 220, 210),
    "Rain": (110, 160, 220), "Heavy Rain": (80, 120, 190), "Fog": (200, 204, 214),
    "Storm": (150, 130, 220), "Snowfall": (235, 240, 250), "Heavy Snow": (225, 232, 246),
}
SEASON_DOTS = {"Spring": (150, 220, 130), "Summer": (250, 210, 90),
               "Autumn": (235, 150, 70), "Winter": (170, 210, 245)}


class HUD:
    def __init__(self):
        self.font = pygame.font.SysFont("segoeui,arial", 14)
        self.small = pygame.font.SysFont("segoeui,arial", 12)
        self.title = pygame.font.SysFont("georgia,segoeui,arial", 15, italic=True)

    def draw(self, screen, f):
        panel = pygame.Surface((238, 124), pygame.SRCALPHA)
        pygame.draw.rect(panel, (12, 18, 24, 132), panel.get_rect(), border_radius=14)
        pygame.draw.rect(panel, (255, 255, 255, 18), panel.get_rect(), 1, border_radius=14)
        panel.blit(self.title.render("Living Forest", True, (235, 238, 230)), (14, 8))
        hh = int(f.tday * 24)
        mm = int((f.tday * 24 - hh) * 60)
        line = "Day %d   %02d:%02d" % (f.day + 1, hh, mm)
        panel.blit(self.font.render(line, True, (208, 214, 210)), (14, 32))
        pygame.draw.circle(panel, SEASON_DOTS[f.season.name], (20, 62), 4)
        panel.blit(self.font.render("%s   %d°C" % (f.season.name, round(f.temp)),
                                    True, (208, 214, 210)), (32, 54))
        wname = f.weather.display_name()
        pygame.draw.circle(panel, WEATHER_DOTS.get(wname, (200, 200, 200)), (20, 84), 4)
        panel.blit(self.font.render(wname, True, (208, 214, 210)), (32, 76))
        stat = "%d trees   %d animals" % (f.tree_count, f.animal_count)
        if f.paused:
            stat += "   ·  paused"
        elif f.speed != 1.0:
            stat += "   ·  ×%g" % f.speed
        panel.blit(self.small.render(stat, True, (168, 176, 172)), (14, 100))
        screen.blit(panel, (16, 14))
        hint = self.small.render("space pause   ·   + / −  speed   ·   R regrow   ·   scroll zoom",
                                 True, (255, 255, 255))
        hint.set_alpha(84)
        screen.blit(hint, (W - hint.get_width() - 18, H - 26))


# ------------------------------------------------------------------------ app
class LivingForest:
    def __init__(self, args):
        pygame.init()
        pygame.display.set_caption("Living Forest")
        self.screen = pygame.display.set_mode((W, H))
        self.scene = pygame.Surface((W, H)).convert()
        self.tint = pygame.Surface((W, H)).convert()
        self.mask_layer = pygame.Surface((W, H), pygame.SRCALPHA)
        self.clock = pygame.time.Clock()
        self.hud = HUD()
        self.camera = Camera()
        self.args = args
        self.detail = 1.0
        self._fpst = 0.0
        self._build_static()
        self.reset(args.get("seed") or random.randint(1, 10 ** 6))

    def _build_static(self):
        # starfield
        rr = random.Random(42)
        self.stars = pygame.Surface((W, 270), pygame.SRCALPHA)
        for _ in range(150):
            x, y = rr.uniform(0, W), rr.uniform(0, 260)
            b = rr.randint(70, 220)
            r = 1 if rr.random() < 0.9 else 2
            fcircle(self.stars, x, y, r, (b, b, min(255, b + 25), 255))
        # vignette
        small = pygame.Surface((160, 100), pygame.SRCALPHA)
        for px in range(160):
            for py in range(100):
                dx, dy = (px - 80) / 80, (py - 50) / 50
                r = math.hypot(dx * 0.9, dy)
                a = int(clamp((r - 0.62) / 0.5, 0, 1) ** 2 * 88)
                if a:
                    small.set_at((px, py), (8, 10, 18, a))
        self.vignette = pygame.transform.smoothscale(small, (W, H))

    # ----------------------------------------------------------------- world
    def iso(self, gx, gy, z=0.0):
        return (OX + (gx - gy) * HW, OY + (gx + gy) * HH - z + self.bob)

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
        # a small clearing that stays open
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
        # flower meadows
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
        # fauna
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
                                 if isinstance(e, (Animal, Bird, Butterfly, Bee)))
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
        # grass slowly spreads
        if len(self.grasses) < 360 and self.grasses:
            g = rng.choice(self.grasses)
            x, y = g.gx + rng.uniform(-1.5, 1.5), g.gy + rng.uniform(-1.5, 1.5)
            if t.walkable(x, y):
                self.entities.append(GrassTuft(self, x, y))
        # flowers bloom back with the season
        target = int(18 + 116 * self.season.flowerf)
        if len(self.flowers) < target:
            cx, cy = self.clearing if rng.random() < 0.4 else rng.choice(t.land_list)
            x, y = cx + rng.gauss(0, 1.8), cy + rng.gauss(0, 1.8)
            if t.walkable(x, y):
                self.entities.append(Flower(self, x, y))
        # mushrooms after rain, in damp spots
        wet = self.weather.rain > 0.25 or self.season.idx == 2
        shroom_n = sum(1 for e in self.entities if isinstance(e, Mushroom))
        if wet and shroom_n < 30 and self.season.snow < 0.6 and rng.random() < 0.5:
            for _ in range(12):
                x, y = rng.uniform(2, GRID - 2), rng.uniform(2, GRID - 2)
                if t.walkable(x, y) and t.moist[int(x)][int(y)] > 0.45:
                    self.entities.append(Mushroom(self, x, y))
                    break
        # the forest never quite dies out
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
            n = wt.rain * (34 if snowing else 130) * rdt
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
        # sunny motes drifting in the light
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
            fps = self.clock.get_fps()
            if fps and fps < 32:
                self.detail = max(0.4, self.detail - 0.15)
            elif fps > 52:
                self.detail = min(1.0, self.detail + 0.1)
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
        # sky
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
        # beneath the island
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
        # terrain
        if self.terrain.surface:
            s.blit(self.terrain.surface, (0, self.bob))
        # cloud shadows, clipped to the island
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
        # water
        self.terrain.draw_water(s, self)
        # entities, depth sorted
        for e in sorted(self.entities, key=lambda e: e.depth):
            if self.detail < 0.95 and isinstance(e, (GrassTuft, Fern)) \
                    and (e.phase / TAU) > self.detail:
                continue
            e.draw(s)
        # particles
        for p in self.particles:
            p.draw(s, self)
        # fog
        for fb in self.fogbands:
            fb.draw(s, self)
        # --- lighting grade
        self.tint.fill(light.ambient)
        s.blit(self.tint, (0, 0), special_flags=pygame.BLEND_MULT)
        # warm horizon glow at dawn / dusk
        if light.dawn_glow > 0.04:
            gx2 = light.sun_pos[0] if light.sun_vis else OX
            g = glow(230, (66, 36, 14), clamp(light.dawn_glow, 0, 1))
            s.blit(g, (gx2 - 230, 380 - 230), special_flags=pygame.BLEND_RGB_ADD)
        # sun & moon halos
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
        # stars
        if light.night > 0.08:
            tw = 0.82 + 0.18 * math.sin(self.anim_t * 1.7)
            self.stars.set_alpha(int(200 * light.night * tw))
            s.blit(self.stars, (0, 0))
        # god rays
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
        # glowing things (fireflies, mushrooms)
        for ff in self.fireflies:
            ff.glow_pass()
        for (x, y, r, col, inten) in self.glow_req:
            q = round(clamp(inten, 0, 1) * 6) / 6
            if q > 0.05:
                g = glow(int(r), col, q)
                s.blit(g, (x - int(r), y - int(r)), special_flags=pygame.BLEND_RGB_ADD)
        # lightning
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
        # vignette
        s.blit(self.vignette, (0, 0))
        # to screen
        self.camera.apply(s, self.screen)
        self.hud.draw(self.screen, self)
        pygame.display.flip()

    # ---------------------------------------------------------------- events
    def handle_events(self):
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                return False
            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    return False
                if ev.key == pygame.K_SPACE:
                    self.paused = not self.paused
                if ev.key in (pygame.K_PLUS, pygame.K_KP_PLUS, pygame.K_EQUALS) \
                        or ev.unicode == "+":
                    self.speed_i = min(len(SPEEDS) - 1, self.speed_i + 1)
                if ev.key in (pygame.K_MINUS, pygame.K_KP_MINUS) or ev.unicode == "-":
                    self.speed_i = max(0, self.speed_i - 1)
                if ev.key == pygame.K_r:
                    self.reset(random.randint(1, 10 ** 6))
            if ev.type == pygame.MOUSEWHEEL:
                self.camera.tzoom = clamp(self.camera.tzoom * (1 + ev.y * 0.13), 1.0, 2.4)
        keys = pygame.key.get_pressed()
        pan = 300 * 0.016 / self.camera.zoom
        if keys[pygame.K_LEFT]:
            self.camera.tpx -= pan
        if keys[pygame.K_RIGHT]:
            self.camera.tpx += pan
        if keys[pygame.K_UP]:
            self.camera.tpy -= pan
        if keys[pygame.K_DOWN]:
            self.camera.tpy += pan
        return True

    def run(self):
        frames = 0
        maxf = self.args.get("frames")
        running = True
        while running:
            rdt = min(self.clock.tick(60) / 1000.0, 0.05)
            running = self.handle_events()
            self.update(rdt)
            self.draw()
            frames += 1
            if maxf and frames >= maxf:
                if self.args.get("shot"):
                    pygame.image.save(self.screen, self.args["shot"])
                running = False
        pygame.quit()


def parse_args(argv):
    args = {}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--frames":
            args["frames"] = int(argv[i + 1]); i += 1
        elif a == "--shot":
            args["shot"] = argv[i + 1]; i += 1
        elif a == "--tod":
            args["tod"] = float(argv[i + 1]); i += 1
        elif a == "--season":
            args["season"] = argv[i + 1]; i += 1
        elif a == "--weather":
            args["weather"] = argv[i + 1]; i += 1
        elif a == "--seed":
            args["seed"] = int(argv[i + 1]); i += 1
        elif a == "--speed":
            args["speed"] = float(argv[i + 1]); i += 1
        i += 1
    return args


def main():
    args = parse_args(sys.argv[1:])
    LivingForest(args).run()


if __name__ == "__main__":
    main()
