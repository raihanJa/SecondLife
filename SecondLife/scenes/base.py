"""Common interface every scene (and the launcher) implements."""
import pygame


class Scene:
    id = "base"
    title = "Scene"
    description = ""
    accent = (80, 190, 255)
    reference_size = (1280, 800)

    def __init__(self, app):
        self.app = app
        self.paused = False
        self.surface = pygame.Surface(self.reference_size)

    def on_enter(self, **kwargs):
        """Called every time this scene becomes active (not just the first time)."""

    def on_exit(self):
        """Called when another scene becomes active."""

    def handle_event(self, event):
        """Scene-scoped input; the InputManager has already consumed global keys."""

    def toggle_pause(self):
        self.paused = not self.paused

    def update(self, dt):
        raise NotImplementedError

    def draw(self):
        """Draw to and return ``self.surface``."""
        raise NotImplementedError

    def controls_help(self):
        """[(key, action), ...] shown in the on-screen legend / README."""
        return []
