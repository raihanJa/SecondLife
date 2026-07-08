"""Additive glow-sprite cache, shared by every scene.

CityPulse and LivingForest each independently built the same technique: bake a
radial falloff into a small opaque ``Surface`` once per (radius, color,
intensity) key, then blit it with ``BLEND_RGB_ADD``. Both call shapes are kept:
``blit_glow`` (CityPulse style — draws straight onto a destination surface)
and ``glow`` (LivingForest style — returns the sprite so the caller can
composite it after applying its own camera/bob offset).
"""
import pygame

from shared.utils.mathutil import clamp
from shared.utils.color import col_scale

_CACHE = {}


def _bucket_color(color):
    return (color[0] // 8, color[1] // 8, color[2] // 8)


def glow(radius, color, intensity=1.0):
    """Return a cached additive-glow sprite; brightness = color * intensity * falloff."""
    radius = max(2, int(radius))
    intensity = clamp(intensity, 0.0, 1.0)
    bucket = _bucket_color(color)
    key = (radius, bucket, round(intensity, 2))
    sprite = _CACHE.get(key)
    if sprite is None:
        base = (bucket[0] * 8, bucket[1] * 8, bucket[2] * 8)
        sprite = pygame.Surface((radius * 2, radius * 2))
        for r in range(radius, 0, -1):
            f = (1.0 - r / radius) ** 2 * intensity
            pygame.draw.circle(sprite, col_scale(base, f), (radius, radius), r)
        _CACHE[key] = sprite
    return sprite


def blit_glow(dst, center, radius, color, intensity=1.0):
    if clamp(intensity, 0.0, 1.0) <= 0.02 or radius < 2:
        return
    sprite = glow(radius, color, intensity)
    r = sprite.get_width() // 2
    dst.blit(sprite, (center[0] - r, center[1] - r),
              special_flags=pygame.BLEND_RGB_ADD)
