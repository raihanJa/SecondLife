"""MultiViewScene — watch several worlds at once, in an adaptive layout.

Rather than duplicating the worlds, this scene reuses the very same scene
instances the SceneManager already owns (fetched lazily on first entry), so a
world keeps its state whether you view it solo or alongside others. Each frame
it updates and draws every *visible* world, then scales their offscreen
surfaces into layout cells and composites them onto its own surface.

Which worlds are shown is toggled live with the number keys, and the layout
adapts to how many are visible: one fills the screen, two sit side by side
(duo mode), three form a 2x2 grid with an info panel. Input is routed to one
focused world at a time (TAB to switch), so the worlds' independent key choices
(M, R, L, +/-, wheel) never collide.
"""
import pygame

from scenes.base import Scene
from shared.renderer.fonts import sysfont
from shared.utils.color import col_scale, mix

BG = (6, 8, 14)
GAP = 6
TEXT = (230, 238, 250)
TEXT_DIM = (150, 165, 190)
BRIGHTEN = 22  # additive lift so scaled-down worlds read clearly on a glance


class MultiViewScene(Scene):
    id = "multi_view"
    title = "Multi View"
    description = "Watch several worlds at once — press 1/2/3 to show one, two or all three."
    accent = (190, 170, 255)
    reference_size = (1280, 800)

    def __init__(self, app):
        super().__init__(app)
        self._child_ids = [c.id for c in app.available_scenes if c.id != self.id]
        self._children = None
        self.visible = [True] * len(self._child_ids)
        self.focus = 0
        self.t = 0.0

    # -- children are created lazily so viewing the grid doesn't force every
    #    world to build itself before the app has even reached the launcher.
    def _get_children(self):
        if self._children is None:
            sm = self.app.scene_manager
            self._children = [sm._get_or_create(cid) for cid in self._child_ids]
        return self._children

    def _visible_indices(self):
        return [i for i, v in enumerate(self.visible) if v]

    def on_enter(self, **kwargs):
        for child in self._get_children():
            child.on_enter()
        self._fix_focus()

    def _fix_focus(self):
        vis = self._visible_indices()
        if self.focus not in vis:
            self.focus = vis[0] if vis else 0

    def toggle_pause(self):
        super().toggle_pause()
        for child in self._get_children():
            if child.paused != self.paused:
                child.toggle_pause()

    def _toggle_world(self, idx):
        vis = self._visible_indices()
        if self.visible[idx] and len(vis) == 1:
            return  # never hide the last remaining world
        self.visible[idx] = not self.visible[idx]
        self._fix_focus()

    def handle_event(self, event):
        children = self._get_children()
        if event.type == pygame.KEYDOWN:
            if pygame.K_1 <= event.key < pygame.K_1 + len(children):
                self._toggle_world(event.key - pygame.K_1)
                return
            if event.key == pygame.K_TAB:
                vis = self._visible_indices()
                if vis:
                    order = vis[vis.index(self.focus) + 1:] + vis[:vis.index(self.focus)] \
                        if self.focus in vis else vis
                    self.focus = order[0]
                return
        # Everything else belongs to the focused world.
        children[self.focus].handle_event(event)

    def update(self, dt):
        if self.paused:
            return
        self.t += dt
        children = self._get_children()
        for i in self._visible_indices():
            children[i].update(dt)

    # -- layout: cells for each visible world (+ an info cell in the 2x2 grid).
    def _layout(self):
        vis = self._visible_indices()
        w, h = self.reference_size
        n = len(vis)
        cells = []
        info = None
        if n <= 1:
            cells.append((vis[0], pygame.Rect(GAP, GAP, w - 2 * GAP, h - 2 * GAP)))
        elif n == 2:
            cw = (w - 3 * GAP) // 2
            ch = h - 2 * GAP
            cells.append((vis[0], pygame.Rect(GAP, GAP, cw, ch)))
            cells.append((vis[1], pygame.Rect(GAP * 2 + cw, GAP, cw, ch)))
        else:
            cw = (w - 3 * GAP) // 2
            ch = (h - 3 * GAP) // 2
            slots = [(GAP, GAP), (GAP * 2 + cw, GAP), (GAP, GAP * 2 + ch)]
            for (px, py), i in zip(slots, vis[:3]):
                cells.append((i, pygame.Rect(px, py, cw, ch)))
            info = pygame.Rect(GAP * 2 + cw, GAP * 2 + ch, cw, ch)
        return cells, info

    @staticmethod
    def _blit_cover(surf, frame, cell):
        """Scale the world to *fill* its cell (cropping the overflow evenly), so
        no letterbox bars shrink it — the near-1:1 scale also keeps it sharp."""
        fw, fh = frame.get_size()
        scale = max(cell.width / fw, cell.height / fh)
        sw, sh = max(cell.width, int(fw * scale)), max(cell.height, int(fh * scale))
        scaled = pygame.transform.smoothscale(frame, (sw, sh))
        if BRIGHTEN:
            scaled.fill((BRIGHTEN, BRIGHTEN, BRIGHTEN), special_flags=pygame.BLEND_RGB_ADD)
        src = pygame.Rect((sw - cell.width) // 2, (sh - cell.height) // 2,
                          cell.width, cell.height)
        surf.blit(scaled, cell.topleft, src)

    def draw(self):
        surf = self.surface
        surf.fill(BG)
        children = self._get_children()
        cells, info = self._layout()

        for i, cell in cells:
            child = children[i]
            frame = child.draw()
            self._blit_cover(surf, frame, cell)
            self._draw_tile_chrome(surf, cell, child, focused=(i == self.focus), index=i)

        if info is not None:
            self._draw_info_cell(surf, info)
        else:
            self._draw_legend(surf)
        return surf

    def _draw_tile_chrome(self, surf, rect, child, focused, index):
        accent = child.accent
        # Header strip with the world's name in its own accent colour.
        header = pygame.Surface((rect.width, 26), pygame.SRCALPHA)
        header.fill((10, 12, 20, 225 if focused else 190))
        surf.blit(header, rect.topleft)
        f = sysfont(15, bold=True)
        label = f.render(f"{index + 1}  {child.title}", True, mix(TEXT, accent, 0.5))
        surf.blit(label, (rect.x + 10, rect.y + 5))
        # Border — bright accent when this tile currently owns the keyboard.
        border = accent if focused else col_scale(accent, 0.4)
        pygame.draw.rect(surf, border, rect, 3 if focused else 1, border_radius=4)

    def _draw_legend(self, surf):
        """Slim bottom bar shown in solo/duo layouts (the grid uses an info cell)."""
        w, h = self.reference_size
        bar_h = 30
        bar = pygame.Surface((w, bar_h), pygame.SRCALPHA)
        bar.fill((8, 10, 18, 210))
        surf.blit(bar, (0, h - bar_h))
        f_key = sysfont(14, bold=True)
        f_txt = sysfont(14)
        y = h - bar_h + 7
        x = 12
        segments = [("1/2/3", "worlds"), ("TAB", "focus"),
                    ("SPACE", "pause"), ("ESC", "back")]
        for key, action in segments:
            surf.blit(f_key.render(key, True, self.accent), (x, y))
            x += f_key.size(key)[0] + 6
            surf.blit(f_txt.render(action, True, TEXT_DIM), (x, y))
            x += f_txt.size(action)[0] + 22

        focused = self._get_children()[self.focus]
        x += 6
        surf.blit(f_txt.render("│  " + focused.title + ":", True,
                               mix(TEXT, focused.accent, 0.5)), (x, y))
        x += f_txt.size("│  " + focused.title + ":")[0] + 12
        for key, action in focused.controls_help():
            surf.blit(f_key.render(key, True, focused.accent), (x, y))
            x += f_key.size(key)[0] + 6
            surf.blit(f_txt.render(action, True, TEXT_DIM), (x, y))
            x += f_txt.size(action)[0] + 20

    def _draw_info_cell(self, surf, cell):
        panel = pygame.Surface(cell.size, pygame.SRCALPHA)
        panel.fill((12, 15, 26, 235))
        pygame.draw.rect(panel, (*col_scale(self.accent, 0.5), 255),
                         panel.get_rect(), 1, border_radius=4)
        surf.blit(panel, cell.topleft)

        f_title = sysfont(30, bold=True)
        f_sub = sysfont(15)
        f_key = sysfont(14, bold=True)
        cx, cy = cell.x + 24, cell.y + 26

        title = f_title.render("SECONDLIFE", True, TEXT)
        surf.blit(title, (cx, cy))
        sub = f_sub.render("Multi View — all worlds live", True, mix(TEXT_DIM, self.accent, 0.4))
        surf.blit(sub, (cx, cy + 40))

        focused = self._get_children()[self.focus]
        y = cy + 84
        lines = [
            ("1 / 2 / 3", "Show / hide a world"),
            ("TAB", "Cycle focus"),
            ("SPACE", "Pause all"),
            ("ESC", "Back to launcher"),
        ]
        for key, action in lines:
            surf.blit(f_key.render(key, True, self.accent), (cx, y))
            surf.blit(f_sub.render(action, True, TEXT_DIM), (cx + 120, y))
            y += 26

        # Controls of whatever world currently has focus.
        y += 10
        head = f_sub.render(f"► {focused.title} controls", True,
                            mix(TEXT, focused.accent, 0.5))
        surf.blit(head, (cx, y))
        y += 26
        for key, action in focused.controls_help():
            surf.blit(f_key.render(key, True, focused.accent), (cx, y))
            surf.blit(f_sub.render(action, True, TEXT_DIM), (cx + 120, y))
            y += 24

    def controls_help(self):
        return [("1/2/3", "Show / hide a world"), ("TAB", "Cycle focus"),
                ("SPACE", "Pause all")]
