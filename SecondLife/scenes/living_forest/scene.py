"""LivingForestScene — thin adapter wiring the ported ForestWorld simulation
and HUD into the SecondLife Scene interface."""
import random

import pygame

from scenes.base import Scene

from .common import H, SPEEDS, W
from .hud import HUD
from .world import ForestWorld


class LivingForestScene(Scene):
    id = "living_forest"
    title = "Living Forest"
    description = "A procedurally generated forest island that lives through days and seasons."
    accent = (92, 168, 82)
    reference_size = (W, H)

    def __init__(self, app):
        super().__init__(app)
        self.world = ForestWorld({}, particle_scale=app.settings.particle_scale())
        self.hud = HUD()

    def toggle_pause(self):
        super().toggle_pause()
        self.world.paused = self.paused

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_PLUS, pygame.K_KP_PLUS, pygame.K_EQUALS) or event.unicode == "+":
                self.world.speed_i = min(len(SPEEDS) - 1, self.world.speed_i + 1)
            elif event.key in (pygame.K_MINUS, pygame.K_KP_MINUS) or event.unicode == "-":
                self.world.speed_i = max(0, self.world.speed_i - 1)
            elif event.key == pygame.K_r:
                self.world.reset(random.randint(1, 10 ** 6))
        elif event.type == pygame.MOUSEWHEEL:
            cam = self.world.camera
            cam.tzoom = max(cam.min_zoom, min(cam.max_zoom, cam.tzoom * (1 + event.y * 0.13)))

    def update(self, dt):
        keys = pygame.key.get_pressed()
        pan = 300 * 0.016 / self.world.camera.zoom
        cam = self.world.camera
        if keys[pygame.K_LEFT]:
            cam.tpx -= pan
        if keys[pygame.K_RIGHT]:
            cam.tpx += pan
        if keys[pygame.K_UP]:
            cam.tpy -= pan
        if keys[pygame.K_DOWN]:
            cam.tpy += pan
        self.world.update(dt)

    def draw(self):
        world_frame = self.world.draw()
        self.world.camera.apply(world_frame, self.surface)
        if self.app.settings.show_hud:
            self.hud.draw(self.surface, self.world)
        return self.surface

    def controls_help(self):
        return [("+/-", "Simulation speed"), ("R", "Regenerate forest"),
                ("Wheel", "Zoom"), ("Arrows", "Pan")]
