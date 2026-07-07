# City Pulse Simulator

A compact isometric cyberpunk city diorama that lives and breathes with
your computer. One dense neon city block floats on a dark reflective
platform — every subsystem of your machine powers a district. Leave it
running on a second monitor and watch your PC as a living ecosystem.

The 3D look is faked entirely with 2D shapes: isometric buildings with
lit side faces, rooftop neon signs, window grids, shadows, additive glow
and wet-street reflections. Everything is drawn procedurally with
Pygame — no external assets.

## The city

| District | Metric | Color | What you'll see |
|---|---|---|---|
| Processing Grid (back-right) | CPU % | Electric orange | Iso towers pulsing with load, orange pods circling the block |
| Memory Spires (back-left) | RAM % | Bright cyan | Tall spires whose window grids fill as memory fills, rising data bands |
| Downlink Expressway | Download speed | Bright blue | Glowing pods and data sparks streaming across the island on an elevated highway |
| Uplink Expressway | Upload speed | Purple | Purple pods with light trails heading out of the city |
| Storage Docks (front-left) | Disk read/write | Lime green | Warehouses with animated loading doors, cranes, container trucks |
| Data Quarter (front-right) | Up/downlink | Blue / purple | Mixed towers with UP / DOWN rooftop signs by the ramps |
| System Stress | Composite | Red | Red beacons and platform warning ring, emergency pods, patrol drones, rain and lightning |

A holographic HUD panel on the right shows live telemetry: CPU, RAM,
downlink, uplink, disk read/write, and a segmented stress meter.

## Install & run

```bash
pip install -r requirements.txt
python main.py
```

Requires Python 3.9+.

## Controls

| Key | Action |
|---|---|
| `ESC` | Quit |
| `SPACE` | Pause / resume |
| `M` | Toggle live metrics / demo mode |
| `R` | Trigger a random stress surge |

## Notes

- Live metrics come from [psutil](https://pypi.org/project/psutil/)
  (CPU %, RAM %, network and disk I/O rates sampled twice per second,
  then smoothed for buttery animation).
- If psutil isn't installed the app falls back to demo mode, which
  synthesizes evolving metrics so the city still feels alive.
- Stress is a weighted blend of all metrics. Above ~50% the rain starts
  and the platform edge glows red; above ~70% expect lightning, drones
  and emergency traffic.
- Depth is done painter's-style: every building, crane and vehicle is
  sorted back-to-front each frame so objects overlap correctly.
