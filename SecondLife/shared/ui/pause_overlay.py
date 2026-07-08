"""Shared paused-state overlay (dim + centered text), used by every scene
instead of each one drawing its own pause banner."""
import pygame

from shared.renderer.fonts import sysfont

ACCENT = (80, 190, 255)


def draw_pause_overlay(screen, size):
    w, h = size
    dim = pygame.Surface((w, h), pygame.SRCALPHA)
    dim.fill((4, 6, 14, 130))
    screen.blit(dim, (0, 0))
    font = sysfont(22, bold=True)
    txt = font.render("· · ·  PAUSED  · · ·", True, (200, 230, 255))
    x = w // 2 - txt.get_width() // 2
    y = h // 2 - 14
    screen.blit(txt, (x, y))
    pygame.draw.line(screen, ACCENT, (x - 30, y + 32), (x + txt.get_width() + 30, y + 32))
