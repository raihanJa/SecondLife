"""Vertical gradient fill — CityPulse bakes its sky this way per scanline;
the Launcher reuses the same technique for its backdrop."""
import pygame

from shared.utils.color import mix


def vertical_gradient(size, top, bottom):
    w, h = size
    surf = pygame.Surface(size)
    for y in range(h):
        surf.fill(mix(top, bottom, y / max(1, h - 1)), (0, y, w, 1))
    return surf
