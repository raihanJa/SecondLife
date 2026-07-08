"""Cached SysFont loader shared by every scene's HUD, so all of them agree on
one typeface instead of each re-resolving fonts independently every frame."""
import pygame

_CACHE = {}
FAMILY = "consolas"


def sysfont(size, bold=False):
    key = (size, bold)
    font = _CACHE.get(key)
    if font is None:
        try:
            font = pygame.font.SysFont(FAMILY, size, bold=bold)
        except Exception:
            font = pygame.font.Font(None, size + 4)
        _CACHE[key] = font
    return font
