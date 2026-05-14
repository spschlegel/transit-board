# Project Context

> For AI assistant session resumption. Keep updated as project evolves.
> Caveman mode (full) is active — see `.github/skills/caveman/Skill.md`.
> Python 3.13. Last session: horizontal split layout + "when to leave" + multi-route bus support.

## What this is

RGB LED matrix transit departure board. Raspberry Pi 4 drives two chained 64×64 P2.5 panels via Adafruit RGB Matrix Bonnet. Shows MBTA real-time departures (bus + metro), weather, temperature, UV index, time.

## Hardware

| Component | Detail |
|---|---|
| Compute | Raspberry Pi 4 |
| Driver board | Adafruit RGB Matrix Bonnet |
| Panels | 2× 64×64 RGB LED P2.5 → chained = **128×64 landscape** |
| Pi power | 15W USB-C |
| Panel power | 5V 10A brick → bonnet |
| Cooling | 30×30mm 5V fan on 40-pin header + heatsinks |

### Hardware mods (one-time, already planned)
- **E→8 solder bridge** on bonnet — required for 64×64 panel addressing
- **GPIO4→GPIO18 jumper** on bonnet — enables hardware PWM quality mode, disables onboard audio

## Display layout (128×64 landscape)

```
┌───────────────────────────────┬───────────────────────────────┐
│  Stop 1  (64×32)              │  Stop 2  (64×32)              │
│  [header]  stop name  ← lv4m │  [header]  stop name  ← lv8m │
│  [chip] headsign        12m • │  [chip] headsign         3m • │
│  [chip] headsign         5m • │  [chip] headsign         7m • │
│  [chip] headsign        18m   │  [chip] headsign        14m   │
├────────────┬──────┬───────────┴──┬──────────────────────────--┤
│  12:34     │ 72°F │  ☀ Clear     │  UV 4  ████░░              │
│  Mon 09    │      │              │                             │
└────────────┴──────┴──────────────┴─────────────────────────────┘
```

- **Top 32 px**: two stops side-by-side (64 px each). Header = 8 px, 3 departure rows × 8 px.
- **Bottom 31 px** (info strip): Clock (34 px) · Temp (22 px) · Weather (40 px) · UV (32 px)
- **Dividers**: horizontal at y=32; vertical stop divider at x=64; info strip dividers at x=34,56,96

## Stack decisions

| Concern | Choice |
|---|---|
| Runtime | CPython 3.13+ |
| Venv / deps | `uv` + `pyproject.toml` |
| Matrix driver | hzeller/rpi-rgb-led-matrix (C lib, built from source by adafruit script) |
| Matrix Python bindings | built by adafruit script, installed via `uv pip install ./rpi-rgb-led-matrix/bindings/python/` |
| Rendering | Pillow → Image → matrix frame |
| HTTP | `httpx` |
| Transit API | MBTA V3 API (free, **requires API key** from api-v3.mbta.com) |
| Weather + UV | Open-Meteo (free, no key) |
| Config | `config.toml` (gitignored) + `.env` for secrets |

## Setup sequence (on Pi)

```
git clone <repo>
bash scripts/bootstrap.sh        # apt deps + uv install; restart shell after
sudo make install-python         # adafruit script → select Bonnet + Quality → reboot
make install                     # uv sync + patches bindings setup.py (distutils→setuptools) + installs
cp config.toml.example config.toml
cp .env.example .env             # add MBTA_API_KEY
make run
```

> **Python 3.13 note**: `make install` auto-patches `rpi-rgb-led-matrix/bindings/python/setup.py` swapping `distutils` → `setuptools` (distutils removed in 3.12+). Patch uses `sudo sed` — run `make install` as **normal user**, not root (root lacks `uv` in PATH).

## Repo structure (implemented)

```
transit-board/
├── adafruit/rgb-matrix.sh       VENDORED — do not modify
├── scripts/bootstrap.sh         system bootstrap (apt + uv)
├── src/transit_board/
│   ├── __init__.py
│   ├── __main__.py              argparse, --dev flag, SIGINT/SIGTERM shutdown
│   ├── config.py                load config.toml + .env, dev_default()
│   ├── loop.py                  async 20-FPS render loop, TTL caches, parallel fetches,
│   │                            haversine walk-time init on startup
│   ├── display/
│   │   ├── layout.py            pixel geometry + colour constants (horizontal-split layout)
│   │   ├── matrix.py            rgbmatrix init OR pygame 4× dev preview
│   │   └── renderer.py          get_font, new_canvas, draw_text_clipped, draw_panel_chrome
│   ├── widgets/
│   │   ├── departures.py        top 128×32 — two stops side-by-side, leave-time header
│   │   ├── clock.py             info strip clock section (x 0–33)
│   │   ├── weather.py           info strip temp (x 34–55) + weather icon/label (x 56–95)
│   │   └── uv.py                info strip UV section (x 96–127)
│   └── providers/
│       ├── cache.py             TTLCache[T] generic
│       ├── transit.py           MBTAClient: departures() + stop_coords() + mock_departures()
│       └── weather.py           WeatherClient (Open-Meteo) + mock_weather()
├── .env.example
├── .github/
│   ├── context.md               this file
│   └── skills/caveman/Skill.md
├── .gitignore
├── .python-version              3.13
├── config.toml.example
├── Makefile
├── pyproject.toml
└── README.md
```

`rpi-rgb-led-matrix/` — created at repo root by adafruit script, gitignored.

## Visual design (current)

- **Transit panel** (top 32 px): two 64×32 stop columns. Header: 3 px coloured accent bar + stop name + right-aligned "when to leave" label. Rows: route chip (pad_x=1) + scrolling headsign + urgency-coloured minutes + realtime green dot. BRD blinks every 15 frames.
- **Leave label** (header right): `LATE` red / `GO!` blinking green / `1m` blinking / `≤5m` yellow / else dim. Calculated as `dep.minutes − stop.walk_minutes`.
- **Multi-route**: departures sorted by time regardless of route — next 3 shown from any mix of routes at stop.
- **Info strip** (bottom 31 px): Clock (HH:MM size 10 + Mon DD size 7) · Temp (°F yellow) · Weather (7×7 pixel-art icon + WMO label teal) · UV (label + WHO colour-scale 2 px bar).
- **Urgency colours**: green ≤2 m, yellow ≤5 m, amber ≤9 m, white 10+, dim = scheduled.
- **Chrome**: drawn last on top — horizontal divider y=32, stop divider x=64, info dividers x=34/56/96.

## Config (config.toml)

```toml
[location]
lat = 42.3601
lon = -71.0589
walk_speed_kmh = 5.0      # used for auto walk-time calc

[[stops]]
id = "64"
name = "Bus"
type = "bus"
# walk_minutes = 8        # optional override; auto-calc from coords if omitted

[[stops]]
id = "place-rugg"
name = "Orange"
type = "subway"
```

`StopConfig.walk_minutes` — `None` at load time if not set; populated on startup by `loop.py` via MBTA `/stops/{id}` → haversine distance → `round(dist_km / walk_speed_kmh * 60)`. Dev mode defaults to 8 min.

## Key open questions / next steps

- **Stop IDs**: look up at api-v3.mbta.com/stops
- **Font**: Pillow default (7/8/10 pt). Custom TTF: `font_path` arg per widget — not yet in config.toml
- **Brightness schedule**: dim at night — not implemented
- **Multi-panel config**: hardcoded 2×64×64 chain
