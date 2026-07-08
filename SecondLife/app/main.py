#!/usr/bin/env python3
"""SecondLife — one window, many living worlds.

Run with:  python main.py
Debug a single scene directly:  python main.py --scene city_pulse
Regression screenshot:  python main.py --scene living_forest --smoke out_dir
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame

from app.input_manager import InputManager
from app.renderer import Renderer
from app.scene_manager import SceneManager, LAUNCHER_ID
from app.settings import Settings
from app.settings_overlay import SettingsOverlay
from app.showcase import ShowcaseController
from app.window import Window
from scenes.launcher.scene import LauncherScene
from shared.ui.notifications import NotificationCenter


def _load_scene_classes(smoke_scene_only=None):
    from scenes.city_pulse.scene import CityPulseScene
    from scenes.living_forest.scene import LivingForestScene
    from scenes.network_highway.scene import NetworkHighwayScene
    from scenes.multi_view.scene import MultiViewScene
    all_scenes = [CityPulseScene, LivingForestScene, NetworkHighwayScene, MultiViewScene]
    # multi_view composites the other worlds, so it needs them all present.
    if smoke_scene_only and smoke_scene_only != MultiViewScene.id:
        return [s for s in all_scenes if s.id == smoke_scene_only]
    return all_scenes


class App:
    def __init__(self, smoke=None):
        pygame.init()
        self.settings = Settings.load()
        self.window = Window(self.settings)
        self.renderer = Renderer(self.window)
        self.scene_manager = SceneManager(self)
        self.input_manager = InputManager(self)
        self.notifications = NotificationCenter()
        self.settings_overlay = SettingsOverlay(self)
        self.clock = pygame.time.Clock()

        self.show_debug = False
        self.show_settings = False
        self._running = True
        self.smoke = smoke

        smoke_filter = smoke[0] if smoke and smoke[0] != LAUNCHER_ID else None
        self.available_scenes = _load_scene_classes(smoke_filter)
        self.scene_manager.register(LauncherScene)
        for cls in self.available_scenes:
            self.scene_manager.register(cls)
        showcase_ids = [c.id for c in self.available_scenes if c.id != "multi_view"]
        self.showcase = ShowcaseController(self, showcase_ids)

        start_id = smoke[0] if smoke else LAUNCHER_ID
        self.scene_manager.start(start_id)

    def toggle_debug(self):
        self.show_debug = not self.show_debug

    def toggle_settings_overlay(self):
        self.show_settings = not self.show_settings

    def on_escape(self):
        if self.show_settings:
            self.show_settings = False
        elif self.showcase.active:
            self.showcase.stop()
            self.scene_manager.switch_to(LAUNCHER_ID)
        else:
            self.scene_manager.go_back_or_quit()

    def request_quit(self):
        self._running = False

    def run(self):
        frame = 0
        while self._running:
            dt = min(self.clock.tick(self.settings.target_fps) / 1000.0, 0.05)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._running = False
                elif event.type == pygame.VIDEORESIZE:
                    self.window.handle_resize(event.size)
                elif self.show_settings:
                    if event.type == pygame.KEYDOWN and event.key in (pygame.K_F2, pygame.K_ESCAPE):
                        self.show_settings = False
                    else:
                        self.settings_overlay.handle_event(event)
                else:
                    self.input_manager.handle_event(event)

            self.notifications.update(dt)
            if not self.show_settings:
                sim_dt = dt if self.scene_manager.transitioning else dt * self.settings.sim_speed_multiplier
                self.scene_manager.update(sim_dt)
                self.showcase.update(dt)

            frame_surface = self.scene_manager.draw()
            active = self.scene_manager.active
            self.renderer.present(
                frame_surface,
                paused=bool(active and active.paused and not self.scene_manager.transitioning),
                show_debug=self.show_debug,
                fps=self.clock.get_fps(),
                scene_name=self.scene_manager.active_id or "",
                notifications=self.notifications,
            )
            if self.show_settings:
                self.settings_overlay.draw(self.window.surface)
            pygame.display.flip()

            if self.smoke:
                frame += 1
                _scene_id, out_dir, max_frames = self.smoke
                if frame >= max_frames:
                    os.makedirs(out_dir, exist_ok=True)
                    pygame.image.save(self.window.surface, os.path.join(out_dir, f"{_scene_id}.png"))
                    print("SMOKE OK")
                    self._running = False

        self.settings.save()
        pygame.quit()


def main():
    argv = sys.argv[1:]
    smoke = None
    if "--smoke" in argv:
        i = argv.index("--smoke")
        scene_id = argv[i + 1]
        out_dir = argv[i + 2] if len(argv) > i + 2 else "."
        smoke = (scene_id, out_dir, 180)
    App(smoke=smoke).run()


if __name__ == "__main__":
    main()
