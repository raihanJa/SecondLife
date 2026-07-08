"""Shared debug overlay: FPS + active scene name, toggled globally with F1."""
import pygame

from shared.renderer.fonts import sysfont


def draw_fps_counter(screen, fps, scene_name):
    font = sysfont(13, bold=True)
    text = f"{fps:5.1f} FPS  ·  {scene_name}"
    surf = font.render(text, True, (140, 230, 255))
    bg_rect = surf.get_rect(topright=(screen.get_width() - 10, 8)).inflate(12, 8)
    box = pygame.Surface(bg_rect.size, pygame.SRCALPHA)
    box.fill((5, 8, 16, 190))
    screen.blit(box, bg_rect.topleft)
    screen.blit(surf, surf.get_rect(topright=(screen.get_width() - 16, 12)))
