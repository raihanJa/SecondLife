"""Color helpers shared by every scene.

CityPulse and LivingForest each hand-rolled the same three operations under
different names (``mix``/``col_scale`` vs ``clerp``/``cmul``). Both name sets
are kept as aliases here so ported scene code can import whichever it always
called without renaming call sites.
"""
from .mathutil import clamp, lerp


def mix(c1, c2, t):
    return (int(lerp(c1[0], c2[0], t)), int(lerp(c1[1], c2[1], t)),
            int(lerp(c1[2], c2[2], t)))


def col_scale(color, f):
    """Darken-only scale: multiplier is clamped to 0..1 first (CityPulse style)."""
    f = clamp(f, 0.0, 1.0)
    return (int(color[0] * f), int(color[1] * f), int(color[2] * f))


def cmul(c, m):
    """Scale that can brighten past white: result is clamped, not the multiplier
    (LivingForest style — used with m > 1 for highlights)."""
    return (int(clamp(c[0] * m, 0, 255)),
            int(clamp(c[1] * m, 0, 255)),
            int(clamp(c[2] * m, 0, 255)))


def cadd(c, d):
    if isinstance(d, (int, float)):
        d = (d, d, d)
    return (int(clamp(c[0] + d[0], 0, 255)),
            int(clamp(c[1] + d[1], 0, 255)),
            int(clamp(c[2] + d[2], 0, 255)))


def gray(c):
    g = (c[0] + c[1] + c[2]) // 3
    return (g, g, g)


# CityPulse naming
clerp = mix
