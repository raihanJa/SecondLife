"""Shared toast/notification system — e.g. NetworkHighway's "busy traffic"
warning, or showcase mode's "Now showing: X" banner. Any scene or the app
shell can push a message; NotificationCenter fades it in/out on its own."""
import pygame

from shared.renderer.fonts import sysfont
from shared.utils.mathutil import clamp

FADE_IN = 0.25
HOLD = 2.6
FADE_OUT = 0.6
ACCENT = (255, 210, 63)


class _Toast:
    def __init__(self, text, accent):
        self.text = text
        self.accent = accent
        self.age = 0.0

    @property
    def duration(self):
        return FADE_IN + HOLD + FADE_OUT

    @property
    def alpha(self):
        if self.age < FADE_IN:
            return clamp(self.age / FADE_IN)
        if self.age < FADE_IN + HOLD:
            return 1.0
        remain = self.duration - self.age
        return clamp(remain / FADE_OUT)


class NotificationCenter:
    def __init__(self):
        self._toasts = []

    def push(self, text, accent=ACCENT):
        self._toasts.append(_Toast(text, accent))

    def update(self, dt):
        for toast in self._toasts:
            toast.age += dt
        self._toasts = [t for t in self._toasts if t.age < t.duration]

    def draw(self, screen):
        w, _ = screen.get_size()
        font = sysfont(14, bold=True)
        y = 20
        for toast in self._toasts:
            surf = font.render(toast.text, True, (245, 250, 255))
            pad_x, pad_y = 16, 10
            box = pygame.Surface((surf.get_width() + pad_x * 2, surf.get_height() + pad_y * 2),
                                  pygame.SRCALPHA)
            a = toast.alpha
            box.fill((10, 13, 24, int(230 * a)))
            pygame.draw.rect(box, (*toast.accent, int(200 * a)), box.get_rect(), 1, border_radius=6)
            box.blit(surf, (pad_x, pad_y))
            box.set_alpha(int(255 * a))
            screen.blit(box, ((w - box.get_width()) // 2, y))
            y += box.get_height() + 8
