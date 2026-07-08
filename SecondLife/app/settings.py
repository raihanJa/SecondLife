"""Persisted application settings — loaded at startup, saved on change/exit."""
import json
import os
from dataclasses import asdict, dataclass, fields

SETTINGS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "settings.json")

PARTICLE_SCALE = {"low": 0.4, "med": 0.7, "high": 1.0}


@dataclass
class Settings:
    target_fps: int = 60
    vsync: bool = True
    fullscreen: bool = False
    borderless: bool = False
    monitor_index: int = 0
    audio_enabled: bool = True
    audio_volume: float = 0.6
    sim_speed_multiplier: float = 1.0
    show_hud: bool = True
    particle_quality: str = "high"
    network_live_capture: bool = False
    showcase_interval_min: float = 4.0
    window_w: int = 1280
    window_h: int = 800

    @classmethod
    def load(cls):
        if os.path.exists(SETTINGS_PATH):
            try:
                with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                known = {name.name for name in fields(cls)}
                return cls(**{k: v for k, v in data.items() if k in known})
            except Exception:
                pass
        return cls()

    def save(self):
        try:
            with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
                json.dump(asdict(self), f, indent=2)
        except Exception:
            pass

    def particle_scale(self):
        return PARTICLE_SCALE.get(self.particle_quality, 1.0)
