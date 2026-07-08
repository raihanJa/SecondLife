"""Registers scenes, switches the active one, and drives transitions.

Scenes are instantiated lazily (on first visit) and then kept alive for the
app's lifetime so revisiting one doesn't re-pay its setup cost (e.g.
LivingForest's terrain generation) — only the active scene's ``update`` runs,
so idle scenes cost nothing while not shown.
"""
import time

import pygame

from shared.ui.transitions import make_transition

LAUNCHER_ID = "launcher"


class SceneManager:
    def __init__(self, app):
        self.app = app
        self._registry = {}
        self._instances = {}
        self.active_id = None
        self.active = None
        self._transition = None

    def register(self, scene_cls):
        self._registry[scene_cls.id] = scene_cls

    def title_of(self, scene_id):
        return self._registry[scene_id].title

    def _get_or_create(self, scene_id):
        inst = self._instances.get(scene_id)
        if inst is None:
            self.app.renderer.present_loading(self._registry[scene_id].title, time.perf_counter())
            inst = self._registry[scene_id](self.app)
            self._instances[scene_id] = inst
        return inst

    def start(self, scene_id, **enter_kwargs):
        self.active = self._get_or_create(scene_id)
        self.active_id = scene_id
        self.active.on_enter(**enter_kwargs)

    def switch_to(self, scene_id, transition="crossfade", **enter_kwargs):
        if self._transition is not None:
            # A request (e.g. ESC) must never be silently dropped just because a
            # showcase crossfade is mid-flight — snap it to its destination first.
            self.active = self._transition["to_scene"]
            self.active_id = self._transition["to_id"]
            self._transition = None
        if scene_id == self.active_id:
            return
        old_frame = self.active.draw().copy() if self.active is not None else None
        if self.active is not None:
            self.active.on_exit()

        new_scene = self._get_or_create(scene_id)
        new_scene.on_enter(**enter_kwargs)

        if old_frame is None:
            self.active, self.active_id = new_scene, scene_id
            return

        self._transition = {
            "effect": make_transition(transition),
            "elapsed": 0.0,
            "old_frame": old_frame,
            "to_id": scene_id,
            "to_scene": new_scene,
        }

    def go_back_or_quit(self):
        if self.active_id == LAUNCHER_ID or self.active_id is None:
            self.app.request_quit()
        else:
            self.switch_to(LAUNCHER_ID)

    def toggle_pause(self):
        if self.active is not None and self._transition is None:
            self.active.toggle_pause()

    def dispatch_event(self, event):
        if self._transition is None and self.active is not None:
            self.active.handle_event(event)

    @property
    def transitioning(self):
        return self._transition is not None

    def update(self, dt):
        tr = self._transition
        if tr is not None:
            tr["elapsed"] += dt
            tr["to_scene"].update(dt)
            if tr["elapsed"] >= tr["effect"].duration:
                self.active = tr["to_scene"]
                self.active_id = tr["to_id"]
                self._transition = None
        elif self.active is not None:
            self.active.update(dt)

    def draw(self):
        tr = self._transition
        if tr is None:
            return self.active.draw()

        new_frame = tr["to_scene"].draw()
        old_frame = tr["old_frame"]
        if old_frame.get_size() != new_frame.get_size():
            old_frame = pygame.transform.smoothscale(old_frame, new_frame.get_size())

        dst = pygame.Surface(new_frame.get_size())
        progress = min(1.0, tr["elapsed"] / tr["effect"].duration)
        tr["effect"].draw(dst, old_frame, new_frame, progress)
        return dst
