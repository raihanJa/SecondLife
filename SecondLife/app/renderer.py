"""Compositor: scales the active scene's offscreen surface into the real
window (letterboxed, aspect-preserved) and draws global overlays on top."""
import pygame

from shared.ui.fps_counter import draw_fps_counter
from shared.ui.loading_screen import draw_loading_screen
from shared.ui.pause_overlay import draw_pause_overlay


class Renderer:
    def __init__(self, window):
        self.window = window

    def _fit(self, surface, target_size):
        sw, sh = surface.get_size()
        tw, th = target_size
        if sw == 0 or sh == 0:
            return surface, (0, 0)
        scale = min(tw / sw, th / sh)
        new_size = (max(1, int(sw * scale)), max(1, int(sh * scale)))
        if new_size == (sw, sh):
            return surface, ((tw - sw) // 2, (th - sh) // 2)
        return pygame.transform.smoothscale(surface, new_size), \
            ((tw - new_size[0]) // 2, (th - new_size[1]) // 2)

    def present(self, scene_surface, *, paused=False, show_debug=False, fps=0.0,
                scene_name="", notifications=None):
        screen = self.window.surface
        screen.fill((0, 0, 0))
        scaled, offset = self._fit(scene_surface, screen.get_size())
        screen.blit(scaled, offset)

        if paused:
            draw_pause_overlay(screen, screen.get_size())
        if notifications is not None:
            notifications.draw(screen)
        if show_debug:
            draw_fps_counter(screen, fps, scene_name)

    def present_loading(self, label, t=0.0):
        screen = self.window.surface
        draw_loading_screen(screen, label, t)
        pygame.display.flip()
