"""LivingForest entities — trees, flora, fauna, and weather particles. Ported
~as-is from the standalone app; only imports were swapped for shared/common
modules."""
import math
import random

import pygame
import pygame.gfxdraw as gfx

from .common import (DAY_LEN, ELEV, GRID, TAU, cadd, clamp, clerp, cmul,
                      fcircle, fell, fline, fpoly, lerp, year_lerp)

AUTUMN_PALS = [
    ((150, 78, 34), (188, 106, 44), (224, 148, 66)),
    ((136, 52, 36), (176, 72, 44), (212, 108, 62)),
    ((150, 116, 40), (192, 152, 52), (228, 196, 84)),
    ((122, 96, 44), (162, 132, 56), (204, 176, 88)),
]


def draw_shadow(s, f, x, y, wdt, inten=1.0):
    a = int((13 + 46 * f.light.sun_strength) * inten)
    if a <= 2:
        return
    dx = f.light.shadow_dx * wdt * 0.045
    fell(s, x + dx, y + 1, wdt, max(2, wdt * 0.36), (22, 32, 26, a))


def swayv(f, phase, scale=1.0):
    return math.sin(f.wind_phase + phase) * (0.6 + 3.6 * f.weather.windv) * scale


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
        if self.stage in ("adult", "old"):
            self.seedt -= dtd
            if self.seedt <= 0:
                self.seedt = f.rng.uniform(0.8, 2.4)
                f.try_seed(self)
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
        if 0.28 < yr < 0.5 and snow < 0.2:
            for i in range(4):
                fcircle(s, bx + rr.uniform(-r * 0.6, r * 0.6) + sw,
                        by - r * 0.5 + rr.uniform(-r * 0.3, r * 0.3), 1, (198, 62, 66))
        elif yr < 0.1 and snow < 0.2:
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


# --------------------------------------------------------------------- weather
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
