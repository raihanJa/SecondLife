"""LivingForest's compact status panel, rebuilt on the shared glass-panel
chrome for visual consistency with the other scenes' HUDs."""
import pygame

from shared.renderer.fonts import sysfont
from shared.ui.panel import Panel

ACCENT = (140, 200, 150)

WEATHER_DOTS = {
    "Sunny": (255, 214, 96), "Cloudy": (190, 198, 210), "Windy": (170, 220, 210),
    "Rain": (110, 160, 220), "Heavy Rain": (80, 120, 190), "Fog": (200, 204, 214),
    "Storm": (150, 130, 220), "Snowfall": (235, 240, 250), "Heavy Snow": (225, 232, 246),
}
SEASON_DOTS = {"Spring": (150, 220, 130), "Summer": (250, 210, 90),
               "Autumn": (235, 150, 70), "Winter": (170, 210, 245)}


class HUD:
    def __init__(self):
        self.panel = Panel(pygame.Rect(16, 14, 252, 138), accent=ACCENT)

    def draw(self, screen, f):
        surf = self.panel.begin(corner_len=10)
        f_title = sysfont(15, bold=True)
        f_text = sysfont(13)

        surf.blit(f_title.render("Living Forest", True, (235, 238, 230)), (14, 10))
        hh = int(f.tday * 24)
        mm = int((f.tday * 24 - hh) * 60)
        line = "Day %d   %02d:%02d" % (f.day + 1, hh, mm)
        surf.blit(f_text.render(line, True, (208, 214, 210)), (14, 36))

        pygame.draw.circle(surf, SEASON_DOTS[f.season.name], (20, 66), 4)
        surf.blit(f_text.render("%s   %d°C" % (f.season.name, round(f.temp)),
                                 True, (208, 214, 210)), (32, 58))

        wname = f.weather.display_name()
        pygame.draw.circle(surf, WEATHER_DOTS.get(wname, (200, 200, 200)), (20, 88), 4)
        surf.blit(f_text.render(wname, True, (208, 214, 210)), (32, 80))

        stat = "%d trees   %d animals" % (f.tree_count, f.animal_count)
        if f.speed != 1.0:
            stat += "   ·  ×%g" % f.speed
        surf.blit(f_text.render(stat, True, (168, 176, 172)), (14, 104))

        self.panel.end(screen, ambient_glow=0.08)
