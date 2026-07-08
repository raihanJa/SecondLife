"""Global key bindings, checked before anything is forwarded to the active
scene — this is what keeps CityPulse's, LivingForest's, and NetworkHighway's
independent key choices from ever colliding: only one scene is ever active,
and the small global layer is claimed here so scenes never see those keys.
"""
import pygame


class InputManager:
    def __init__(self, app):
        self.app = app
        self.global_bindings = {
            pygame.K_ESCAPE: lambda: app.on_escape(),
            pygame.K_F11: lambda: app.window.toggle_fullscreen(),
            pygame.K_F1: lambda: app.toggle_debug(),
            pygame.K_F2: lambda: app.toggle_settings_overlay(),
            pygame.K_SPACE: lambda: app.scene_manager.toggle_pause(),
        }

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN and event.key in self.global_bindings:
            self.global_bindings[event.key]()
            return
        self.app.scene_manager.dispatch_event(event)
