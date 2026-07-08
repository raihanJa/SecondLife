"""Small numeric helpers shared by every scene."""
import math

TAU = math.tau


def clamp(v, lo=0.0, hi=1.0):
    return lo if v < lo else hi if v > hi else v


def lerp(a, b, t):
    return a + (b - a) * t


def smoothstep(t):
    t = clamp(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def soft_norm(value, ref):
    """Map an unbounded non-negative value (e.g. bytes/s) softly into 0..1."""
    return value / (value + ref) if value > 0 else 0.0
