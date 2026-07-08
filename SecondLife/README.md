# SecondLife

A desktop application for your **second monitor**: one window, a premium
launcher, and a small collection of beautiful, ambient living simulations to
leave running while you game, code, or study on your primary display.

SecondLife merges three previously-standalone Pygame projects —
**City Pulse**, **Living Forest**, and **Network Highway** — into a single
product with a shared visual language, one input scheme, shared settings,
polished scene transitions, and an optional Showcase Mode that auto-cycles
through every world.

## Running it

```bash
pip install -r requirements.txt
python app/main.py
```

Debug a single scene directly (skips the launcher):

```bash
python app/main.py --scene city_pulse
```

Regression screenshot (renders N frames then saves a PNG):

```bash
python app/main.py --smoke living_forest out_dir
```

## The worlds

| Scene | What it is |
|---|---|
| **City Pulse** | A neon isometric cyberpunk city block whose districts pulse with your PC's live CPU, RAM, disk and network activity (falls back to a synthetic demo feed if `psutil` is unavailable). |
| **Living Forest** | A procedurally generated floating forest island with a full day/night cycle, four seasons, weather, and wandering animals. |
| **Network Highway** | Your network traffic reimagined as cars streaming down a neon perspective highway — one car per packet, lane and direction per protocol/direction, colored by protocol. Runs on synthetic demo traffic by default; real packet capture (via `scapy`) is an opt-in setting since it requires Administrator/root and, on Windows, Npcap. |

## Architecture

```
SecondLife/
  app/                  Application shell — one pygame window, one event loop
    main.py               Entry point
    window.py             Owns the display Surface (fullscreen/borderless/monitor)
    renderer.py            Compositor: scales the active scene into the window,
                            draws global overlays (debug FPS, pause, settings)
    scene_manager.py        Registers scenes, switches the active one, drives transitions
    input_manager.py         Global key bindings; unclaimed keys go to the active scene
    settings.py               Persisted settings (SecondLife/settings.json)
    settings_overlay.py        F2 settings menu
    showcase.py                 Auto-cycle controller for Showcase Mode
  scenes/
    base.py               Scene interface every world (and the launcher) implements
    launcher/              The premium picker screen — itself a Scene
    city_pulse/            City Pulse: city.py (sim), metrics.py, hud.py, scene.py
    living_forest/         Living Forest: common.py, entities.py, world.py, hud.py, scene.py
    network_highway/       Network Highway: traffic.py, highway_renderer.py, hud.py, scene.py
  shared/                 Code reused by 2+ scenes (see "What's shared" below)
    utils/                  Math (clamp/lerp) and color (mix/scale/blend) helpers
    renderer/                Additive glow cache, isometric projection, cached fonts, gradients
    camera/                  Generic smoothed zoom/pan camera (used by Living Forest today;
                             available to any future scene)
    particles/               Minimal particle-list alive/prune bookkeeping
    ui/                      Glass-panel HUD chrome, pause overlay, notifications/toasts,
                             FPS counter, loading screen, scene transitions
  assets/                 (empty — every scene draws procedurally, no bundled assets)
```

### What's shared vs. scene-specific

All three original apps had independently reinvented the same handful of
things — those were pulled into `shared/`:

- **Math & color helpers** (`clamp`/`lerp`/color-mix/color-scale) — City Pulse
  and Living Forest each hand-rolled nearly identical versions.
- **Additive glow-sprite cache** — both scenes built the same
  bake-a-radial-falloff-once-per-color technique independently.
- **The glass HUD panel** (translucent panel, neon border, corner brackets) —
  all three scenes' original UIs converged on this same look; there's one
  implementation now, shared by every scene's HUD, the settings overlay, and
  the launcher's cards.
- **Isometric projection** — City Pulse's and Living Forest's grid-to-screen
  math is the same formula with different tile-size/origin constants.
- **The app lifecycle** — one window, one clock, one event loop, dispatching
  update/draw to whichever `Scene` is active.

What stayed scene-specific (each is genuinely unique domain logic): City
Pulse's `psutil` metrics sampling and procedural city; Living Forest's
terrain generation (noise, pond/stream carving) and its incremental,
generator-based terrain rendering that spreads first-time generation cost
across several frames; Network Highway's packet classifier/demo generator
and its perspective-projection highway renderer (necessarily rewritten from
HTML canvas/JS into Pygame draw calls — see below).

### A note on Network Highway

The original `NetworkHighwayV2` was not a Pygame app: it was a small stdlib
HTTP server streaming packets over Server-Sent-Events to an HTML5 Canvas
renderer shown in a `pywebview` window. Since SecondLife must own exactly one
window, that renderer was ported to Pygame draw calls; the packet
classification and demo/live traffic generation logic was kept almost
verbatim, with the HTTP/SSE/webview plumbing removed.

## Controls

**Global** (work everywhere — the launcher or any scene):

| Key | Action |
|---|---|
| `ESC` | Back to the Launcher (or quit, from the Launcher) |
| `F11` | Toggle fullscreen |
| `F1` | Toggle the debug FPS overlay |
| `F2` | Open/close Settings |
| `SPACE` | Pause / resume the current scene |

**City Pulse:**

| Key | Action |
|---|---|
| `M` | Toggle live telemetry / demo feed |
| `R` | Trigger a stress surge |

**Living Forest:**

| Key | Action |
|---|---|
| `+` / `-` | Simulation speed |
| `R` | Regenerate the forest |
| Mouse wheel | Zoom |
| Arrow keys | Pan (while zoomed) |

**Network Highway:**

| Key | Action |
|---|---|
| `L` | Toggle live / demo packet capture (live requires the "Network live capture" setting and Administrator/root) |

**Launcher:**

| Key | Action |
|---|---|
| `←` / `→` | Move focus between cards and the Showcase Mode button |
| `ENTER` | Launch the focused card |

Only `SPACE`, `ESC`, `F1`, `F2`, and `F11` are ever claimed globally, so
scene-specific bindings never collide — only one scene is ever active at a
time.

## Settings

`F2` opens the settings overlay (arrow keys navigate, left/right adjust).
Settings persist to `SecondLife/settings.json`:

- Target FPS, VSync, Fullscreen, Borderless, Monitor selection
- Simulation speed multiplier
- Show HUD
- Particle quality (low/med/high — scales each scene's existing particle/
  density counts)
- Network live capture (opt-in; off by default)
- Showcase Mode interval

## Showcase Mode

Started from the Launcher's "Showcase Mode" button. Crossfades through every
scene on a timer (configurable in Settings, minimum 30 seconds). `ESC` exits
back to the Launcher at any time, even mid-transition.

## Performance

Only the active scene ticks — switching away fully stops the old one (except
for the brief crossfade during a transition). Each scene renders to its own
fixed reference-resolution surface (preserving all of its original layout
math untouched); the app compositor scales that once into the actual window/
monitor size, so scenes never had to be rewritten for arbitrary resolutions.
Living Forest's incremental, generator-based terrain rendering (spreading
first-time generation across several frames) is preserved as-is.
