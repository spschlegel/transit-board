# transit-board

RGB LED matrix transit departure board powered by a Raspberry Pi 4.

Shows real-time MBTA bus + subway departures, current temperature, weather
condition, and UV index on two chained 64×64 P2.5 panels (128×64 px landscape).

```
┌──────────────────────────────────┬──────────┐
│  BUS          Forest Hills   2m  │  14:32   │
│  39           Forest Hills  12m  │  Fri 09  │
│  66           Harvard        5m  ├──────────┤
├──────────────────────────────────┤   72F    │
│  ORANGE       Oak Grove      3m  │  Clear   │
│  OL           Oak Grove     11m  ├──────────┤
│  OL           Forest Hills   7m  │  UV4     │
└──────────────────────────────────┴──────────┘
```

## Hardware

| Component | Detail |
|---|---|
| Compute | Raspberry Pi 4 |
| Driver board | Adafruit RGB Matrix Bonnet |
| Panels | 2× 64×64 RGB LED P2.5 → chained = **128×64 landscape** |
| Pi power | 15W USB-C |
| Panel power | 5V 10A brick → bonnet |

**One-time hardware mods (on the bonnet):**
- Solder **E→8 bridge** — required for 64×64 panel row addressing
- Solder **GPIO4→GPIO18 jumper** — enables hardware PWM quality mode

## Setup

```bash
# 1. System bootstrap (as normal user, sudo invoked internally)
bash scripts/bootstrap.sh

# 2. Restart shell if uv was just installed, then:
sudo make install-python   # Adafruit script — select Bonnet + Quality, then reboot

# 3. After reboot:
make install               # uv sync + hzeller Python bindings

# 4. Configure
cp config.toml.example config.toml   # edit: set your stop IDs + location
cp .env.example .env                 # add: MBTA_API_KEY=your_key

# 5. Run
make run
```

Get a free MBTA API key at <https://api-v3.mbta.com>.  
Look up stop IDs at <https://api-v3.mbta.com/stops>.

## Development (no hardware needed)

```bash
make dev   # uses mock data, opens a 4× scaled pygame preview window
```

Requires `pygame` (included in the `dev` dependency group via `uv sync --group dev`).

## Configuration

`config.toml` (copy from `config.toml.example`):

```toml
[location]
lat = 42.3601
lon = -71.0589

[[stops]]          # repeat for each stop (up to 2 displayed)
id = "64"
name = "Bus"
type = "bus"       # "bus" | "subway"

[display]
brightness = 50    # 0–100

[refresh]
transit_secs = 30
weather_secs = 300
```

MBTA API key goes in `.env`:
```
MBTA_API_KEY=your_key_here
```

## Run at boot (systemd)

```bash
make install-service     # installs + starts transit-board.service (uses sudo)
make logs                # follow the journal
make uninstall-service
```

The service runs as root like `make run` and restarts on crashes. Stop any
`make run` session first — both would claim the GPIO hardware and port 8080.
The app's "Restart board" button works under systemd too (it re-execs in place).

## Companion app

The board serves a small phone-friendly web app (a PWA) on port 8080: tap
Transit / Sports / Idle / Auto to show something for 15 min – 2 h (or hold it),
and it falls back to the schedule in `[schedule]` afterwards. The Board section
shows data freshness, reloads `config.toml` without restarting, or restarts the
whole process (re-exec in place, so it works under tmux).

1. Set `BOARD_TOKEN=<long random string>` in `.env` (without it the server stays off).
2. Open `http://<pi-hostname>.local:8080` on your phone, enter the token, then
   "Add to Home Screen".

Local network only: the process runs as root for GPIO access, so never forward
this port to the internet. In `make dev` the server binds to 127.0.0.1 with
token `dev` unless `BOARD_TOKEN` is set.

## Stack

| Concern | Choice |
|---|---|
| Runtime | CPython 3.11+ |
| Deps | `uv` + `pyproject.toml` |
| Matrix driver | hzeller/rpi-rgb-led-matrix (C lib, built by Adafruit script) |
| Rendering | Pillow → PIL Image → matrix frame |
| Companion server | aiohttp (same event loop as the render loop) |
| HTTP | `httpx` (async) |
| Transit | MBTA V3 API (free key required) |
| Weather | Open-Meteo (free, no key) |
| Config | `config.toml` + `.env` |
