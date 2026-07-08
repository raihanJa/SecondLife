"""Glass-panel HUD chrome shared by every scene.

CityPulse's ``HUD``, LivingForest's ``HUD``, and NetworkHighway's CSS
``.bord``/``.legenda`` asides all independently converged on the same look:
a translucent dark panel, a thin neon border, and bracketed corners. One
implementation now backs all of them.
"""
import pygame

from shared.renderer.fonts import sysfont
from shared.renderer.glow import blit_glow


class Panel:
    def __init__(self, rect, accent=(80, 190, 255), bg=(7, 11, 24), bg_alpha=242):
        self.rect = rect
        self.accent = accent
        self.bg = bg
        self.bg_alpha = bg_alpha
        self.surface = pygame.Surface(rect.size, pygame.SRCALPHA)

    def begin(self, corner_len=16, border_alpha=130):
        """Paint background + border + corner brackets; returns the local-origin
        surface for the caller to draw scene-specific content onto."""
        surf = self.surface
        w, h = surf.get_size()
        surf.fill((*self.bg, self.bg_alpha))
        pygame.draw.rect(surf, (*self.accent, border_alpha), (0, 0, w, h), 1)
        bl = corner_len
        for cx, cy, dx, dy in ((0, 0, 1, 1), (w - 1, 0, -1, 1),
                               (0, h - 1, 1, -1), (w - 1, h - 1, -1, -1)):
            pygame.draw.line(surf, (*self.accent, 255), (cx, cy), (cx + dx * bl, cy), 2)
            pygame.draw.line(surf, (*self.accent, 255), (cx, cy), (cx, cy + dy * bl), 2)
        return surf

    def end(self, screen, ambient_glow=0.10):
        screen.blit(self.surface, self.rect.topleft)
        if ambient_glow > 0:
            blit_glow(screen, self.rect.midtop, 60, self.accent, ambient_glow)


def draw_header(surf, title, subtitle, t, accent, x=18, y=20):
    """Title + subtitle + a moving scanline sweep, as seen in every scene HUD."""
    f_title = sysfont(22, bold=True)
    f_sub = sysfont(13)
    surf.blit(f_title.render(title, True, (225, 245, 255)), (x, y))
    surf.blit(f_sub.render(subtitle, True, (168, 192, 224)), (x, y + 26))
    w = surf.get_width()
    line_y = y + 42
    pygame.draw.line(surf, (*accent, 170), (x, line_y), (w - x, line_y))
    span = max(1, w - x * 2)
    sweep = x + ((t * 60) % span)
    pygame.draw.line(surf, (255, 255, 255, 200), (sweep, line_y - 1), (sweep + 14, line_y - 1), 2)


def draw_bar_row(surf, x, y, w, label, value, frac, color):
    """Label + value + a filled progress bar — CityPulse's per-metric HUD row."""
    from shared.utils.color import col_scale, mix

    lab_col = mix((235, 244, 255), color, 0.30)
    surf.blit(sysfont(14, bold=True).render(label, True, lab_col), (x, y))
    val = sysfont(16, bold=True).render(value, True, (245, 250, 255))
    surf.blit(val, (x + w - val.get_width(), y - 2))
    bar = pygame.Rect(x, y + 21, w, 9)
    pygame.draw.rect(surf, (16, 22, 40, 255), bar, border_radius=4)
    pygame.draw.rect(surf, (*col_scale(color, 0.35), 255), bar, 1, border_radius=4)
    fill_w = int(bar.width * max(0.0, min(1.0, frac)))
    if fill_w > 2:
        fill = pygame.Rect(bar.x, bar.y, fill_w, bar.height)
        pygame.draw.rect(surf, (*col_scale(color, 0.75), 255), fill, border_radius=4)
        pygame.draw.rect(surf, (*color, 255),
                          (fill.x, fill.y + 1, fill.width, 3), border_radius=2)
        tipx = bar.x + fill_w
        pygame.draw.circle(surf, (*color, 255), (tipx, bar.centery), 3)
        pygame.draw.circle(surf, (255, 255, 255, 180), (tipx, bar.centery), 1)


def draw_stat_row(surf, x, y, w, label, value, accent):
    """Simple label/value row without a bar — NetworkHighway's dashboard style."""
    f = sysfont(14)
    surf.blit(f.render(label, True, (168, 192, 224)), (x, y))
    val = sysfont(14, bold=True).render(value, True, (255, 255, 255))
    surf.blit(val, (x + w - val.get_width(), y))
