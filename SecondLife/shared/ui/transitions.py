"""Scene-to-scene transition effects.

Each transition blends a snapshot of the outgoing scene's last frame with the
incoming scene's current frame, both pre-rendered to same-size surfaces by
the SceneManager. "Camera pull back" is approximated by ``ZoomFade`` — a true
3D pull-back isn't feasible generically across heterogeneous 2D renderers, so
a zoom-out-and-fade stands in for it.
"""
import pygame

from shared.utils.mathutil import smoothstep


class Transition:
    duration = 0.8

    def draw(self, dst, old_frame, new_frame, progress):
        raise NotImplementedError


class Fade(Transition):
    """Fade to black, then fade in — safest choice when the two scenes' color
    palettes clash badly."""
    duration = 0.9

    def draw(self, dst, old_frame, new_frame, progress):
        p = smoothstep(progress)
        if p < 0.5:
            shown, local = old_frame, p / 0.5
            alpha = 255 - int(255 * local)
        else:
            shown, local = new_frame, (p - 0.5) / 0.5
            alpha = int(255 * local)
        dst.blit(shown, (0, 0))
        veil = pygame.Surface(dst.get_size())
        veil.set_alpha(255 - alpha)
        dst.blit(veil, (0, 0))


class Crossfade(Transition):
    """Direct alpha blend between the two scenes — the default, smoothest option."""
    duration = 0.8

    def draw(self, dst, old_frame, new_frame, progress):
        p = smoothstep(progress)
        dst.blit(old_frame, (0, 0))
        top = new_frame.copy()
        top.set_alpha(int(255 * p))
        dst.blit(top, (0, 0))


class ZoomFade(Transition):
    """Old scene zooms out and fades while the new one fades in underneath —
    stands in for a "camera pull back" transition."""
    duration = 1.0

    def draw(self, dst, old_frame, new_frame, progress):
        p = smoothstep(progress)
        w, h = dst.get_size()
        new_top = new_frame.copy()
        new_top.set_alpha(int(255 * p))
        dst.blit(old_frame, (0, 0))
        dst.blit(new_top, (0, 0))
        scale = 1.0 - 0.18 * p
        sw, sh = max(1, int(w * scale)), max(1, int(h * scale))
        shrunk = pygame.transform.smoothscale(old_frame, (sw, sh))
        shrunk.set_alpha(255 - int(255 * p))
        dst.fill((3, 4, 8))
        dst.blit(new_top, (0, 0))
        dst.blit(shrunk, ((w - sw) // 2, (h - sh) // 2))


TRANSITIONS = {"fade": Fade, "crossfade": Crossfade, "zoom": ZoomFade}


def make_transition(name):
    cls = TRANSITIONS.get(name, Crossfade)
    return cls()
