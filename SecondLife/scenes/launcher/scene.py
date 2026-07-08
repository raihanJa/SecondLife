"""The premium picker screen. It's modeled as a plain Scene (not special-cased
by the SceneManager) so adding a future world only means registering another
scene and adding one entry to ``app.available_scenes``."""
import math

import pygame

from scenes.base import Scene
from shared.renderer.fonts import sysfont
from shared.renderer.gradient import vertical_gradient
from shared.renderer.glow import blit_glow
from shared.utils.color import mix, col_scale
from shared.utils.mathutil import clamp

BG_TOP = (8, 10, 20)
BG_BOTTOM = (16, 14, 30)
TEXT = (225, 235, 250)
TEXT_DIM = (150, 165, 190)


class LauncherScene(Scene):
    id = "launcher"
    title = "SecondLife"
    accent = (150, 180, 255)
    reference_size = (1280, 800)

    def __init__(self, app):
        super().__init__(app)
        self.t = 0.0
        self.focus = 0
        self.background = vertical_gradient(self.reference_size, BG_TOP, BG_BOTTOM)
        self._stars = self._make_stars()
        self.card_rects = []
        self.showcase_rect = pygame.Rect(0, 0, 0, 0)

    def _make_stars(self):
        import random
        rng = random.Random(11)
        w, h = self.reference_size
        return [(rng.uniform(0, w), rng.uniform(0, h * 0.5), rng.uniform(0.3, 1.0))
                for _ in range(90)]

    def on_enter(self, **kwargs):
        self.focus = 0

    def _entries(self):
        return self.app.available_scenes

    def _layout(self):
        entries = self._entries()
        n = len(entries)
        w, h = self.reference_size
        card_w, card_h = 300, 380
        gap = 40
        max_w = w - 80  # keep a margin on both sides
        if n * card_w + (n - 1) * gap > max_w:
            gap = 24
            if n * card_w + (n - 1) * gap > max_w:
                card_w = (max_w - (n - 1) * gap) // n
        total_w = n * card_w + (n - 1) * gap
        x0 = (w - total_w) // 2
        y = h // 2 - card_h // 2 - 20
        rects = [pygame.Rect(x0 + i * (card_w + gap), y, card_w, card_h) for i in range(n)]
        showcase = pygame.Rect(0, 0, 420, 56)
        showcase.centerx = w // 2
        showcase.y = y + card_h + 44
        return rects, showcase

    def handle_event(self, event):
        entries = self._entries()
        focus_count = len(entries) + 1
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_LEFT, pygame.K_a):
                self.focus = (self.focus - 1) % focus_count
            elif event.key in (pygame.K_RIGHT, pygame.K_d):
                self.focus = (self.focus + 1) % focus_count
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self._activate(self.focus)
        elif event.type == pygame.MOUSEMOTION:
            self._update_hover(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._update_hover(event.pos)
            self._activate(self.focus)

    def _screen_to_scene(self, pos):
        sw, sh = self.app.window.size
        rw, rh = self.reference_size
        scale = min(sw / rw, sh / rh)
        ox = (sw - rw * scale) / 2
        oy = (sh - rh * scale) / 2
        return ((pos[0] - ox) / scale, (pos[1] - oy) / scale)

    def _update_hover(self, mouse_pos):
        pos = self._screen_to_scene(mouse_pos)
        rects, showcase = self._layout()
        for i, r in enumerate(rects):
            if r.collidepoint(pos):
                self.focus = i
                return
        if showcase.collidepoint(pos):
            self.focus = len(rects)

    def _activate(self, index):
        entries = self._entries()
        if index < len(entries):
            self.app.scene_manager.switch_to(entries[index].id, transition="crossfade")
        else:
            self.app.showcase.start()

    def update(self, dt):
        self.t += dt

    def draw(self):
        surf = self.surface
        surf.blit(self.background, (0, 0))
        for x, y, b in self._stars:
            v = int(80 + 100 * b)
            surf.set_at((int(x), int(y)), (v, v, min(255, v + 25)))

        w, _ = self.reference_size
        f_title = sysfont(46, bold=True)
        f_sub = sysfont(16)
        title = f_title.render("SECONDLIFE", True, TEXT)
        surf.blit(title, (w // 2 - title.get_width() // 2, 96))
        sub = f_sub.render("Living worlds for your second monitor", True, TEXT_DIM)
        surf.blit(sub, (w // 2 - sub.get_width() // 2, 96 + 58))

        rects, showcase = self._layout()
        self.card_rects = rects
        self.showcase_rect = showcase
        entries = self._entries()
        for i, (scene_cls, rect) in enumerate(zip(entries, rects)):
            self._draw_card(surf, rect, scene_cls, focused=(i == self.focus))
        self._draw_showcase_button(surf, showcase, focused=(self.focus == len(rects)))
        return surf

    def _draw_card(self, surf, rect, scene_cls, focused):
        accent = scene_cls.accent
        lift = 8 if focused else 0
        r = rect.move(0, -lift)
        panel = pygame.Surface(r.size, pygame.SRCALPHA)
        base_alpha = 235 if focused else 200
        panel.fill((14, 17, 28, base_alpha))
        border_col = accent if focused else col_scale(accent, 0.45)
        pygame.draw.rect(panel, (*border_col, 255), panel.get_rect(), 2, border_radius=18)
        pygame.draw.rect(panel, (*mix((14, 17, 28), accent, 0.08), 255), panel.get_rect(),
                          border_radius=18)

        f_name = sysfont(22, bold=True)
        f_desc = sysfont(13)
        name = f_name.render(scene_cls.title, True, (245, 248, 255))
        panel.blit(name, (22, 26))
        pygame.draw.line(panel, (*accent, 200), (22, 60), (r.width - 22, 60))

        y = 78
        for line in self._wrap(scene_cls.description, f_desc, r.width - 44):
            panel.blit(f_desc.render(line, True, TEXT_DIM), (22, y))
            y += 20

        icon_c = (r.width // 2, r.height - 74)
        pulse = 0.6 + 0.4 * math.sin(self.t * 2.0 + hash(scene_cls.id) % 10)
        blit_glow(panel, icon_c, 46, accent, 0.35 + 0.25 * pulse * focused)
        pygame.draw.circle(panel, accent, icon_c, 8)

        surf.blit(panel, r.topleft)
        if focused:
            blit_glow(surf, r.midtop, 90, accent, 0.22)

    @staticmethod
    def _wrap(text, font, max_w):
        words = text.split()
        lines, cur = [], ""
        for word in words:
            trial = f"{cur} {word}".strip()
            if font.size(trial)[0] <= max_w:
                cur = trial
            else:
                if cur:
                    lines.append(cur)
                cur = word
        if cur:
            lines.append(cur)
        return lines

    def _draw_showcase_button(self, surf, rect, focused):
        accent = self.accent
        panel = pygame.Surface(rect.size, pygame.SRCALPHA)
        panel.fill((14, 17, 28, 235 if focused else 190))
        border = accent if focused else col_scale(accent, 0.5)
        pygame.draw.rect(panel, (*border, 255), panel.get_rect(), 2, border_radius=28)
        f = sysfont(16, bold=True)
        label = f.render("▶  SHOWCASE MODE — cycle through every world", True, (240, 245, 255))
        panel.blit(label, (panel.get_width() // 2 - label.get_width() // 2,
                            panel.get_height() // 2 - label.get_height() // 2))
        surf.blit(panel, rect.topleft)
        if focused:
            blit_glow(surf, rect.center, 70, accent, 0.22)

    def controls_help(self):
        return [("←/→", "Navigate"), ("ENTER", "Launch"), ("ESC", "Quit")]
