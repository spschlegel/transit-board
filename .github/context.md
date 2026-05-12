# Project Context

> For AI assistant session resumption. Keep updated as project evolves.
> Caveman mode (full) is active — see `.github/skills/caveman/Skill.md`.
> Python 3.13. Last session: Python 3.13 upgrade + full visual polish pass.

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
┌──────────────────────────────────┬──────────┐
│  Departures  (left ¾ = ~96×64)  │  Clock   │
│  Bus stop    ·  Metro stop       │  Temp    │
│  scrolling rows per stop         │  Weather │
│                                  │  UV idx  │
└──────────────────────────────────┴──────────┘
```

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
make install                     # uv sync + hzeller bindings
cp config.toml.example config.toml
cp .env.example .env             # add MBTA_API_KEY
make run
```

## Repo structure (implemented)

```
transit-board/
├── adafruit/rgb-matrix.sh       VENDORED — do not modify
├── scripts/bootstrap.sh         system bootstrap (apt + uv)
├── src/transit_board/
│   ├── __init__.py
│   ├── __main__.py              argparse, --dev flag, SIGINT/SIGTERM shutdown
│   ├── config.py                load config.toml + .env, dev_default()
│   ├── loop.py                  async 20-FPS render loop, TTL caches, parallel fetches
│   ├── display/
│   │   ├── layout.py            pixel geometry + colour constants
│   │   ├── matrix.py            rgbmatrix init OR pygame 4× dev preview
│   │   └── renderer.py          get_font, new_canvas, draw_text_clipped (scrolling)
│   ├── widgets/
│   │   ├── departures.py        left 96×64 — route/headsign/minutes rows
│   │   ├── clock.py             right sidebar — HH:MM + date
│   │   ├── weather.py           right sidebar — °F + WMO condition label
│   │   └── uv.py                right sidebar — UV index (WHO colour scale)
│   └── providers/
│       ├── cache.py             TTLCache[T] generic
│       ├── transit.py           MBTAClient (httpx async) + mock_departures()
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

- **Departure panel** (left 95 px): 3 px coloured accent bar on stop headers; route "chips" (coloured badge with 20%-tint background); headsign scrolls when too long; minutes urgency-coloured (green ≤2 m, yellow ≤5 m, amber ≤9 m, white 10+, dim=scheduled); BRD blinks every 15 frames; realtime green dot top-right of row
- **Sidebar** (right 32 px): clock (HH:MM + Mon DD), temperature (°F), 7×7 pixel-art weather icon + WMO label, UV index + WHO colour-scale progress bar
- **Chrome**: 1 px vertical panel divider at x=95; 1 px horizontal sidebar section dividers at TEMP_Y/WEATHER_Y/UV_Y — drawn last so they're always on top
- **Sidebar layout**: CLOCK 20 px · TEMP 13 px · WEATHER 18 px · UV 13 px = 64 px

## Key open questions / next steps

- **Stop IDs**: user must look up real bus + metro stop IDs at api-v3.mbta.com/stops
- **Font**: Pillow built-in default font (size 7/8/10 pt). Custom TTF configurable via `font_path` arg in each widget — not yet exposed in config.toml
- **Brightness schedule**: could dim at night — not implemented
- **Multi-panel config**: hardcoded 2×64×64 chain; could be made configurable
