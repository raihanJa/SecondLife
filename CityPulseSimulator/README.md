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
| Fusion Reactor (satellite platform) | GPU load / temp / VRAM | Magenta | A containment ring with a floating plasma core on its own island, feeding the city through a glowing energy conduit |
| System Stress | Composite | Red | Red beacons and platform warning ring, emergency pods, patrol drones, rain and lightning |

The reactor is your GPU made visible: the core pulses faster and grows
with GPU load while charge particles and arcs crackle around it, the
core's colour tracks temperature (icy cyan when cool, amber, then
red-hot), the fuel rods in the ring fill with VRAM, and the twin
cooling towers vent more steam as the card heats up. Past ~82 °C the
site strobes red and the sign flips to OVERHEAT.

A holographic HUD panel on the right shows live telemetry: CPU, RAM,
GPU load / core temperature / VRAM, downlink, uplink, disk read/write,
and a segmented stress meter.

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
- GPU load, temperature and VRAM come from NVML via
  [nvidia-ml-py](https://pypi.org/project/nvidia-ml-py/) on NVIDIA
  cards, or from AMD's ADL driver library via
  [pyadl](https://pypi.org/project/pyadl/) on AMD cards (ADL exposes no
  VRAM figure, so that row shows `--` and the fuel rods stay dark).
  `nvidia-smi` / `rocm-smi` background polls act as fallbacks. Without
  any supported GPU the reactor simply idles cold in live mode (demo
  mode still animates it).
- If psutil isn't installed the app falls back to demo mode, which
  synthesizes evolving metrics so the city still feels alive.
- Stress is a weighted blend of all metrics (GPU included — a heavy
  gaming session will push the city into stress mode). Above ~50% the
  rain starts and the platform edge glows red; above ~70% expect
  lightning, drones and emergency traffic.
- Depth is done painter's-style: every building, crane and vehicle is
  sorted back-to-front each frame so objects overlap correctly.
