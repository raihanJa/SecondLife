"""Owns the single pygame display Surface for the whole app."""
import pygame


class Window:
    def __init__(self, settings):
        self.settings = settings
        self.surface = None
        self.rebuild()

    def rebuild(self):
        s = self.settings
        flags = 0
        if s.fullscreen:
            flags |= pygame.FULLSCREEN
        elif s.borderless:
            flags |= pygame.NOFRAME | pygame.RESIZABLE
        else:
            flags |= pygame.RESIZABLE

        kwargs = {}
        try:
            sizes = pygame.display.get_desktop_sizes()
            if 0 <= s.monitor_index < len(sizes):
                kwargs["display"] = s.monitor_index
        except Exception:
            pass

        size = (s.window_w, s.window_h)
        try:
            self.surface = pygame.display.set_mode(size, flags, vsync=1 if s.vsync else 0, **kwargs)
        except TypeError:
            self.surface = pygame.display.set_mode(size, flags, **kwargs)
        pygame.display.set_caption("SecondLife")

    def toggle_fullscreen(self):
        self.settings.fullscreen = not self.settings.fullscreen
        if self.settings.fullscreen:
            self.settings.borderless = False
        self.rebuild()

    def handle_resize(self, size):
        if not self.settings.fullscreen and not self.settings.borderless:
            self.settings.window_w, self.settings.window_h = size
            self.surface = pygame.display.set_mode(size, pygame.RESIZABLE)

    @property
    def size(self):
        return self.surface.get_size()
