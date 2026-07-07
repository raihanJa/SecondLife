# Living Forest 🌲

A living, procedurally generated forest diorama — a tiny floating island
suspended in the sky, rendered entirely with pygame primitives. No sprites,
no textures, no assets: every tree, cloud, raindrop and firefly is drawn
procedurally, every frame.

There is no player and there are no objectives. Leave it running on a second
monitor and watch a miniature world live its life.

## What happens on the island

- **Trees** sprout from seeds, grow through sapling, young, adult and old age,
  drop seeds of their own, die, decay and disappear. The forest slowly
  reshapes itself over hours.
- **A full day/night cycle** — warm dawns, bright noons, golden evenings and
  deep blue moonlit nights with stars, fireflies and glowing mushrooms.
- **Four seasons** — spring blossom, dense summer green, fiery autumn with
  continuously falling leaves, and winter with snow, bare trees and a frozen
  pond.
- **Weather** — sun, drifting clouds, wind, fog banks, rain with puddles and
  splashes, and full storms with lightning.
- **Animals** — rabbits hop, deer graze, a fox patrols, birds fly between
  trees, butterflies and bees visit the flowers, and fireflies come out at
  night. Everything is peaceful; nothing hunts.
- **Water** — a pond that ripples, reflects the trees and the moon, a stream,
  and a waterfall spilling off the island's edge.

## Running

```bash
pip install -r requirements.txt
python main.py
```

## Controls

| Key | Action |
| --- | --- |
| `ESC` | Quit |
| `SPACE` | Pause |
| `+` / `-` | Simulation speed (0.25× – 8×) |
| `R` | Generate a new forest |
| Mouse wheel | Zoom |
| Arrow keys | Pan (when zoomed) |

## Extras

Optional command line flags, mostly useful for previewing:

```
--seed N          use a specific world seed
--season autumn   start in a given season (spring/summer/autumn/winter)
--weather Storm   lock the weather (Sunny/Cloudy/Windy/Rain/"Heavy Rain"/Fog/Storm)
--tod 0.9         lock the time of day (0..1, 0.5 = noon)
--frames N        run N frames then exit
--shot file.png   save a screenshot when exiting (with --frames)
```

At 1× speed a full day lasts two minutes and a full year about half an hour.
