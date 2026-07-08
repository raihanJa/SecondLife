"""City Pulse telemetry HUD, built on the shared glass-panel chrome."""
import math

import pygame

from shared.renderer.fonts import sysfont
from shared.ui.panel import Panel, draw_bar_row, draw_header
from shared.utils.color import col_scale, mix
from shared.utils.mathutil import clamp, soft_norm

from .city import (CPU_COLOR, DISK_COLOR, DOWN_COLOR, MB, RAM_COLOR,
                    STRESS_COLOR, UP_COLOR, fmt_speed)

RECT = pygame.Rect(988, 18, 276, 764)
PANEL_EDGE = (80, 190, 255)


class HUD:
    def __init__(self):
        self.panel = Panel(RECT, accent=PANEL_EDGE)

    def draw(self, screen, t, city, live_mode, fps):
        surf = self.panel.begin()
        w = surf.get_width()
        draw_header(surf, "CITY PULSE", "SYSTEM TELEMETRY UPLINK", t, PANEL_EDGE)

        y = 74
        blink = math.sin(t * 4) > 0
        mode_col = (90, 255, 140) if live_mode else (255, 210, 80)
        mode_txt = "LIVE TELEMETRY" if live_mode else "DEMO SIGNAL"
        if blink:
            pygame.draw.circle(surf, mode_col, (24, y + 6), 3)
        surf.blit(sysfont(13).render(mode_txt, True, mode_col), (34, y))
        fps_s = sysfont(13).render(f"{fps:3.0f} FPS", True, (168, 192, 224))
        surf.blit(fps_s, (w - 18 - fps_s.get_width(), y))

        n = city.n
        rows = [
            ("CPU LOAD", f"{city.cpu:4.0f} %", n["cpu"], CPU_COLOR),
            ("MEMORY", f"{city.ram:4.0f} %", n["ram"], RAM_COLOR),
            ("DOWNLINK", fmt_speed(city.dl), n["dl"], DOWN_COLOR),
            ("UPLINK", fmt_speed(city.ul), n["ul"], UP_COLOR),
            ("DISK READ", fmt_speed(city.dr), n["disk"], DISK_COLOR),
            ("DISK WRITE", fmt_speed(city.dw), clamp(soft_norm(city.dw, 20 * MB)), DISK_COLOR),
        ]
        y = 104
        for label, value, frac, color in rows:
            draw_bar_row(surf, 18, y, w - 36, label, value, frac, color)
            y += 58

        y += 6
        surf.blit(sysfont(14, bold=True).render(
            "SYSTEM STRESS", True, mix((235, 244, 255), STRESS_COLOR, 0.30)), (18, y))
        st = city.stress
        status, scol = self._status(st)
        stxt = sysfont(16, bold=True).render(status, True, scol)
        if st < 0.75 or math.sin(t * 8) > -0.2:
            surf.blit(stxt, (w - 18 - stxt.get_width(), y - 2))
        y += 22
        segs = 22
        seg_w = (w - 36 - (segs - 1) * 3) / segs
        lit = int(round(st * segs))
        for i in range(segs):
            f = i / (segs - 1)
            color = mix((80, 255, 140), (255, 210, 60), clamp(f / 0.6)) if f < 0.6 \
                else mix((255, 210, 60), STRESS_COLOR, clamp((f - 0.6) / 0.4))
            x = 18 + i * (seg_w + 3)
            r = pygame.Rect(int(x), y, int(seg_w), 14)
            if i < lit:
                hot = st > 0.78 and i > segs * 0.7 and math.sin(t * 9) > 0
                pygame.draw.rect(surf, (255, 255, 255) if hot else color, r)
            else:
                pygame.draw.rect(surf, (*col_scale(color, 0.18), 255), r)
                pygame.draw.rect(surf, (*col_scale(color, 0.35), 255), r, 1)
        y += 26
        surf.blit(sysfont(13).render(f"STRESS INDEX {st * 100:3.0f}", True, (168, 192, 224)),
                   (18, y))

        y = self.panel.rect.height - 90
        pygame.draw.line(surf, (*PANEL_EDGE, 90), (18, y), (w - 18, y))
        y += 10
        for key, action in (("M", "LIVE / DEMO FEED"), ("R", "STRESS SURGE TEST")):
            k = sysfont(13).render(key, True, (165, 225, 255))
            pygame.draw.rect(surf, (30, 52, 80, 220), (18, y - 2, 54, 18), border_radius=3)
            pygame.draw.rect(surf, (*PANEL_EDGE, 120), (18, y - 2, 54, 18), 1, border_radius=3)
            surf.blit(k, (18 + 27 - k.get_width() // 2, y))
            surf.blit(sysfont(13).render(action, True, (168, 192, 224)), (82, y))
            y += 25

        self.panel.end(screen)

    @staticmethod
    def _status(st):
        if st < 0.25:
            return "CALM", (90, 255, 140)
        if st < 0.5:
            return "STEADY", (140, 230, 255)
        if st < 0.75:
            return "BUSY", (255, 210, 60)
        return "OVERLOAD", STRESS_COLOR
