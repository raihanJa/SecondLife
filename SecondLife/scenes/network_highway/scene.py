"""NetworkHighwayScene — thin adapter wiring the packet source, the ported
Pygame highway renderer, and the HUD into the SecondLife Scene interface."""
import pygame

from scenes.base import Scene

from .highway_renderer import HighwayRenderer
from .hud import HUD
from .traffic import DemoSource, LiveSource, TrafficStats


class NetworkHighwayScene(Scene):
    id = "network_highway"
    title = "Network Highway"
    description = "Your network traffic reimagined as cars streaming down a neon highway."
    accent = (0, 229, 255)
    reference_size = (1280, 800)

    def __init__(self, app):
        super().__init__(app)
        self.demo_source = DemoSource()
        self.live_source = None
        self.live_mode = False
        self.stats = TrafficStats()
        self.renderer = HighwayRenderer(particle_scale=app.settings.particle_scale())
        self.hud = HUD()
        self.t = 0.0
        self._last_skipped = 0

    def on_enter(self, **kwargs):
        if self.app.settings.network_live_capture and self.live_source is None:
            self._enable_live()

    def _enable_live(self):
        self.live_source = LiveSource()
        if self.live_source.available:
            self.live_mode = True
            self.app.notifications.push("Live packet capture enabled")
        else:
            self.app.notifications.push(f"Live capture unavailable: {self.live_source.error}")
            self.live_mode = False

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_l:
            if self.live_mode:
                self.live_mode = False
            elif self.live_source is not None and self.live_source.available:
                self.live_mode = True
            else:
                self._enable_live()

    def update(self, dt):
        if self.paused:
            return
        self.t += dt
        source = self.live_source if (self.live_mode and self.live_source) else self.demo_source
        packets = source.poll(dt)
        self.stats.ingest(packets, self.t)
        self.renderer.update(dt, packets)
        if self.renderer.skipped > self._last_skipped:
            self.app.notifications.push(
                f"Busy traffic — {self.renderer.skipped - self._last_skipped} packets not drawn")
        self._last_skipped = self.renderer.skipped

    def draw(self):
        surf = self.surface
        self.renderer.draw(surf)
        if self.app.settings.show_hud:
            connected = (not self.live_mode) or (self.live_source and self.live_source.available)
            self.hud.draw(surf, self.t, self.stats, self.live_mode, connected)
        return surf

    def controls_help(self):
        return [("L", "Toggle live / demo capture")]
