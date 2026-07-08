"""Generic smoothed zoom/pan camera, generalized from LivingForest's Camera so
any scene (present or future — Galaxy, Ocean, ...) can opt into the same
subsurface+smoothscale zoom technique instead of reinventing it."""
import pygame

from shared.utils.mathutil import clamp


class Camera2D:
    def __init__(self, view_w, view_h, min_zoom=1.0, max_zoom=2.4, follow_speed=6.0):
        self.view_w, self.view_h = view_w, view_h
        self.min_zoom, self.max_zoom = min_zoom, max_zoom
        self.follow_speed = follow_speed
        self.zoom = self.tzoom = 1.0
        self.px = self.py = 0.0
        self.tpx = self.tpy = 0.0

    def nudge_zoom(self, factor):
        self.tzoom = clamp(self.tzoom * factor, self.min_zoom, self.max_zoom)

    def pan(self, dx, dy):
        self.tpx += dx
        self.tpy += dy

    def update(self, rdt):
        k = clamp(rdt * self.follow_speed, 0, 1)
        self.zoom += (self.tzoom - self.zoom) * k
        self.px += (self.tpx - self.px) * k
        self.py += (self.tpy - self.py) * k
        vw, vh = self.view_w / self.zoom, self.view_h / self.zoom
        mx, my = (self.view_w - vw) / 2, (self.view_h - vh) / 2
        self.tpx = clamp(self.tpx, -mx, mx)
        self.tpy = clamp(self.tpy, -my, my)

    def apply(self, scene_surface, dst_surface):
        if abs(self.zoom - 1.0) < 0.005 and abs(self.px) < 0.6 and abs(self.py) < 0.6:
            dst_surface.blit(scene_surface, (0, 0))
            return
        w, h = self.view_w, self.view_h
        vw, vh = int(w / self.zoom), int(h / self.zoom)
        x = int(clamp(w / 2 + self.px - vw / 2, 0, w - vw))
        y = int(clamp(h / 2 + self.py - vh / 2, 0, h - vh))
        sub = scene_surface.subsurface((x, y, vw, vh))
        dst_surface.blit(pygame.transform.smoothscale(sub, (w, h)), (0, 0))
