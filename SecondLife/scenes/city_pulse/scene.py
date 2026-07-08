"""CityPulseScene — thin adapter wiring the ported City simulation, HUD, and
metrics provider into the SecondLife Scene interface."""
import pygame

from scenes.base import Scene

from .city import DISTRICT_LABELS, City
from .hud import HUD
from .metrics import DemoMetrics, MetricsProvider
from shared.renderer.fonts import sysfont
from shared.utils.color import col_scale


class CityPulseScene(Scene):
    id = "city_pulse"
    title = "City Pulse"
    description = "A neon isometric cyberpunk city powered by your PC's vital signs."
    accent = (255, 122, 24)
    reference_size = (1280, 800)

    def __init__(self, app):
        super().__init__(app)
        self.city = City(particle_scale=app.settings.particle_scale())
        self.hud = HUD()
        self.metrics = MetricsProvider()
        self.demo = DemoMetrics()
        self.live_mode = self.metrics.available
        self.f_label = sysfont(11, bold=True)
        self.t = 0.0

    def on_enter(self, **kwargs):
        pass

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_m:
                if self.metrics.available:
                    self.live_mode = not self.live_mode
            elif event.key == pygame.K_r:
                self.city.trigger_stress()

    def update(self, dt):
        if self.paused:
            return
        self.t += dt
        if self.live_mode:
            self.metrics.update(dt)
            raw = (self.metrics.cpu, self.metrics.ram, self.metrics.dl,
                   self.metrics.ul, self.metrics.disk_r, self.metrics.disk_w)
        else:
            raw = self.demo.sample(self.t)
        self.city.update(dt, self.t, raw)

    def draw(self):
        surf = self.surface
        self.city.draw(surf, self.t)
        for text, pos, color in DISTRICT_LABELS:
            label = self.f_label.render(text, True, col_scale(color, 0.85))
            surf.blit(label, pos)
            pygame.draw.line(surf, col_scale(color, 0.4),
                             (pos[0], pos[1] + 12),
                             (pos[0] + label.get_width(), pos[1] + 12))
        if self.app.settings.show_hud:
            self.hud.draw(surf, self.t, self.city, self.live_mode, self.app.clock.get_fps())
        return surf

    def controls_help(self):
        return [("M", "Live / demo telemetry"), ("R", "Trigger stress surge")]
