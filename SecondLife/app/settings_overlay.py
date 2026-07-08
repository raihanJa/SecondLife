"""Minimal settings overlay: arrow keys navigate/adjust, F2 or ESC closes it.
Shares the same glass-panel chrome every scene HUD uses."""
import pygame

from shared.renderer.fonts import sysfont
from shared.ui.panel import Panel, draw_header

ACCENT = (140, 210, 255)

_PARTICLE_LEVELS = ["low", "med", "high"]


class SettingsOverlay:
    def __init__(self, app):
        self.app = app
        self.index = 0
        self._rows = [
            ("Target FPS", self._get_fps, self._step_fps),
            ("VSync", self._get_vsync, self._step_vsync),
            ("Fullscreen", self._get_fullscreen, self._step_fullscreen),
            ("Borderless", self._get_borderless, self._step_borderless),
            ("Simulation speed", self._get_sim_speed, self._step_sim_speed),
            ("Show HUD", self._get_show_hud, self._step_show_hud),
            ("Particle quality", self._get_particles, self._step_particles),
            ("Network live capture", self._get_live_capture, self._step_live_capture),
            ("Showcase interval (min)", self._get_showcase, self._step_showcase),
        ]
        panel_w, panel_h = 460, 74 + len(self._rows) * 30 + 24
        self.panel = Panel(pygame.Rect(0, 0, panel_w, panel_h), accent=ACCENT)

    # -- field accessors ----------------------------------------------------
    def _s(self):
        return self.app.settings

    def _get_fps(self):
        return str(self._s().target_fps)

    def _step_fps(self, d):
        self._s().target_fps = max(24, min(144, self._s().target_fps + d * 6))

    def _get_vsync(self):
        return "on" if self._s().vsync else "off"

    def _step_vsync(self, d):
        self._s().vsync = not self._s().vsync
        self.app.window.rebuild()

    def _get_fullscreen(self):
        return "on" if self._s().fullscreen else "off"

    def _step_fullscreen(self, d):
        self.app.window.toggle_fullscreen()

    def _get_borderless(self):
        return "on" if self._s().borderless else "off"

    def _step_borderless(self, d):
        s = self._s()
        s.borderless = not s.borderless
        if s.borderless:
            s.fullscreen = False
        self.app.window.rebuild()

    def _get_sim_speed(self):
        return f"{self._s().sim_speed_multiplier:.2f}x"

    def _step_sim_speed(self, d):
        s = self._s()
        s.sim_speed_multiplier = max(0.25, min(4.0, round(s.sim_speed_multiplier + d * 0.25, 2)))

    def _get_show_hud(self):
        return "on" if self._s().show_hud else "off"

    def _step_show_hud(self, d):
        self._s().show_hud = not self._s().show_hud

    def _get_particles(self):
        return self._s().particle_quality

    def _step_particles(self, d):
        levels = _PARTICLE_LEVELS
        i = levels.index(self._s().particle_quality)
        self._s().particle_quality = levels[max(0, min(len(levels) - 1, i + d))]

    def _get_live_capture(self):
        return "on" if self._s().network_live_capture else "off"

    def _step_live_capture(self, d):
        self._s().network_live_capture = not self._s().network_live_capture

    def _get_showcase(self):
        return f"{self._s().showcase_interval_min:.0f}"

    def _step_showcase(self, d):
        s = self._s()
        s.showcase_interval_min = max(1.0, min(60.0, s.showcase_interval_min + d))

    # -- input ---------------------------------------------------------------
    def handle_event(self, event):
        if event.type != pygame.KEYDOWN:
            return
        if event.key in (pygame.K_UP, pygame.K_w):
            self.index = (self.index - 1) % len(self._rows)
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self.index = (self.index + 1) % len(self._rows)
        elif event.key in (pygame.K_LEFT, pygame.K_a):
            self._rows[self.index][2](-1)
        elif event.key in (pygame.K_RIGHT, pygame.K_d):
            self._rows[self.index][2](1)

    # -- draw ------------------------------------------------------------------
    def draw(self, screen):
        w, h = screen.get_size()
        self.panel.rect.center = (w // 2, h // 2)
        surf = self.panel.begin()
        draw_header(surf, "SETTINGS", "F2 / ESC TO CLOSE  ·  ARROWS TO ADJUST", 0.0, ACCENT)
        font = sysfont(14)
        font_b = sysfont(14, bold=True)
        y = 70
        for i, (label, getter, _) in enumerate(self._rows):
            active = i == self.index
            col = (255, 255, 255) if active else (170, 195, 220)
            if active:
                pygame.draw.rect(surf, (*ACCENT, 40), (10, y - 3, surf.get_width() - 20, 24), border_radius=5)
            surf.blit(font.render(label, True, col), (18, y))
            val = font_b.render(str(getter()), True, col)
            surf.blit(val, (surf.get_width() - 18 - val.get_width(), y))
            y += 30
        self.panel.end(screen, ambient_glow=0.14)
