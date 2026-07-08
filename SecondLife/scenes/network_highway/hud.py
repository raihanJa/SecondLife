"""Network Highway's holographic dashboard + protocol legend, ported from
index.html's ``.bord``/``.legenda`` asides onto the shared glass-panel chrome."""
import pygame

from shared.renderer.fonts import sysfont
from shared.ui.panel import Panel, draw_header, draw_stat_row

from .traffic import PROTOCOLS

ACCENT = (0, 229, 255)


def fmt_bytes_per_sec(n):
    if n >= 1e9:
        return f"{n / 1e9:.1f} GB/s"
    if n >= 1e6:
        return f"{n / 1e6:.1f} MB/s"
    if n >= 1e3:
        return f"{n / 1e3:.1f} kB/s"
    return f"{n:.0f} B/s"


def fmt_bytes(n):
    if n >= 1e9:
        return f"{n / 1e9:.1f} GB"
    if n >= 1e6:
        return f"{n / 1e6:.1f} MB"
    if n >= 1e3:
        return f"{n / 1e3:.1f} kB"
    return f"{n:.0f} B"


class HUD:
    def __init__(self):
        self.dashboard = Panel(pygame.Rect(18, 18, 268, 218), accent=ACCENT)
        self.legend = Panel(pygame.Rect(0, 0, 260, 168), accent=ACCENT)
        self._prev_bytes = None
        self._prev_t = 0.0
        self._rate = (0.0, 0.0)

    def draw(self, screen, t, stats, live_mode, connected):
        self._draw_dashboard(screen, t, stats, live_mode, connected)
        self._draw_legend(screen, stats)

    def _draw_dashboard(self, screen, t, stats, live_mode, connected):
        surf = self.dashboard.begin()
        draw_header(surf, "NETWORK HIGHWAY", "LIVE PACKET STREAM", t, ACCENT)

        elapsed = t - self._prev_t
        if self._prev_bytes is None:
            self._prev_bytes = (stats.in_bytes, stats.out_bytes)
            self._prev_t = t
        elif elapsed >= 0.5:
            self._rate = (max(0.0, (stats.in_bytes - self._prev_bytes[0]) / elapsed),
                          max(0.0, (stats.out_bytes - self._prev_bytes[1]) / elapsed))
            self._prev_bytes = (stats.in_bytes, stats.out_bytes)
            self._prev_t = t
        down_rate, up_rate = self._rate

        y = 72
        draw_stat_row(surf, 18, y, surf.get_width() - 36, "▼ DOWNLOAD", fmt_bytes_per_sec(down_rate), ACCENT)
        y += 26
        draw_stat_row(surf, 18, y, surf.get_width() - 36, "▲ UPLOAD", fmt_bytes_per_sec(up_rate), ACCENT)
        y += 26
        draw_stat_row(surf, 18, y, surf.get_width() - 36, "PACKETS/S", f"{stats.pps:,.0f}", ACCENT)
        y += 26
        total = f"{stats.pkts:,} pkts · {fmt_bytes(stats.in_bytes + stats.out_bytes)}"
        draw_stat_row(surf, 18, y, surf.get_width() - 36, "TOTAL", total, ACCENT)

        y += 34
        if not connected:
            lamp, label = (255, 71, 87), "Disconnected"
        elif live_mode:
            lamp, label = (61, 220, 132), "Live capture"
        else:
            lamp, label = (255, 210, 63), "Demo traffic"
        pygame.draw.circle(surf, lamp, (24, y + 6), 4)
        surf.blit(sysfont(12, bold=True).render(label.upper(), True, (200, 220, 235)), (36, y))

        self.dashboard.end(screen)

    def _draw_legend(self, screen, stats):
        w, h = screen.get_size()
        self.legend.rect.bottomright = (w - 18, h - 18)
        surf = self.legend.begin(corner_len=10)
        f_label = sysfont(12)
        f_count = sysfont(12, bold=True)
        cols = 2
        col_w = surf.get_width() // cols
        y0 = 16
        row_h = 24
        items = list(PROTOCOLS.items())
        for idx, (key, meta) in enumerate(items):
            col, row = idx % cols, idx // cols
            x = 16 + col * col_w
            y = y0 + row * row_h
            pygame.draw.rect(surf, meta["color"], (x, y + 4, 16, 6), border_radius=3)
            surf.blit(f_label.render(meta["name"], True, (210, 220, 230)), (x + 22, y))
            count = stats.per_protocol.get(key, 0)
            ctext = f_count.render(str(count), True, (170, 190, 205))
            surf.blit(ctext, (x + col_w - 34, y))
        self.legend.end(screen, ambient_glow=0.08)
