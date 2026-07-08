"""Constants, projection, and the alpha-aware draw primitives shared by every
LivingForest module. Ported ~as-is from the standalone app; math/color/glow
helpers now come from ``shared`` instead of being redefined here."""
import pygame
import pygame.gfxdraw as gfx

from shared.renderer.iso import IsoGrid
from shared.utils.color import cadd, clerp, cmul, gray  # noqa: F401 (re-exported)
from shared.utils.mathutil import TAU, clamp, lerp, smoothstep as smooth  # noqa: F401

W, H = 1280, 760
GRID = 34
HW, HH = 16, 8
ELEV = 9
OX, OY = W // 2, 146
DAY_LEN = 120.0
SEASON_DAYS = 4.0
YEAR_DAYS = SEASON_DAYS * 4
SEASONS = ("Spring", "Summer", "Autumn", "Winter")
MAX_TREES = 100
SPEEDS = (0.25, 0.5, 1.0, 2.0, 4.0, 8.0)

_GRID_PROJ = IsoGrid(OX, OY, HW, HH)
isoS = _GRID_PROJ.project


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
