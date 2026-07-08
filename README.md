# SecondLife

A desktop app for your **second monitor** — one window, a premium launcher,
and a small collection of beautiful, ambient living simulations to leave
running while you game, code, or study on your primary display.

Built with Python and [Pygame](https://www.pygame.org/), everything is drawn
procedurally: no sprites, no textures, no bundled assets.

## The worlds

| Scene | What it is |
|---|---|
| **City Pulse** | A neon isometric cyberpunk city block whose districts pulse with your PC's live CPU, RAM, disk and network activity. |
| **Living Forest** | A procedurally generated floating forest island with a full day/night cycle, four seasons, weather, and wandering animals. |
| **Network Highway** | Your network traffic reimagined as cars streaming down a neon perspective highway — one car per packet, colored by protocol. |
| **Multi View** | A composite view that runs several worlds side by side in a single window. |

All four share one window, one input scheme, shared settings, polished scene
transitions, and an optional Showcase Mode that auto-cycles through every
world.

## Running it

```bash
cd SecondLife
pip install -r requirements.txt
python app/main.py
```

Debug a single scene directly (skips the launcher):

```bash
python app/main.py --scene city_pulse
```

See [SecondLife/README.md](SecondLife/README.md) for full details:
architecture, controls, settings, and how each scene works.

## Repository layout

```
SecondLife/            The app — start here
CityPulseSimulator/    Original standalone City Pulse (Pygame)
LivingForest/           Original standalone Living Forest (Pygame)
NetworkHighwayV2/       Original standalone Network Highway (HTML canvas + pywebview)
```

`SecondLife/` merges the three standalone projects into a single product with
a shared visual language; the standalone folders are kept as-is for history
and are no longer developed independently. Each has its own README with
scene-specific details.

## Requirements

- Python 3.9+
- [pygame](https://pypi.org/project/pygame/), [psutil](https://pypi.org/project/psutil/)
- Optional: [scapy](https://pypi.org/project/scapy/) for real packet capture
  in Network Highway (requires Administrator/root, and Npcap on Windows)
