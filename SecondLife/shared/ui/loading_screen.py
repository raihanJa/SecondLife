"""Shared loading screen, shown while a scene does heavy first-time init
(e.g. LivingForest generating its terrain)."""
import math

import pygame

from shared.renderer.fonts import sysfont

BG = (5, 7, 14)
ACCENT = (80, 190, 255)


def draw_loading_screen(screen, label, t):
    w, h = screen.get_size()
    screen.fill(BG)
    font = sysfont(20, bold=True)
    text = font.render(f"Loading {label}…", True, (225, 240, 255))
    screen.blit(text, (w // 2 - text.get_width() // 2, h // 2 - 30))

    cx, cy, r = w // 2, h // 2 + 24, 14
    for i in range(3):
        phase = t * 3.0 - i * 0.9
        a = 0.35 + 0.65 * max(0.0, math.sin(phase))
        dot_col = tuple(int(c * a) for c in ACCENT)
        pygame.draw.circle(screen, dot_col, (cx - r + i * r, cy), 4)
