# Showcase dashboards

Five dashboards made to show what LevityDash can draw. Each has its own typeface, palette and layout idea, and
each runs on made-up data, so most of the keys belong to plugins that do not exist yet.

| Dashboard | Subject | Type | Ground |
|---|---|---|---|
| `atmos` | Weather: now, two and a half days ahead, five cards | SF Pro Display Black against Thin, SF Compact for labels | Black, neon |
| `rack` | Homelab: nodes, network, power, storage, services | Doto (dot matrix) numerals, JetBrains Mono labels written as code comments | Black, phosphor green |
| `grow` | Greenhouse: air, light, shelves, water, a notebook | Fraunces numerals, Instrument Serif italic, tracked capitals | Paper (light theme), no cards |
| `grid` | Home energy: solar, house, street, battery, car | Big Shoulders Display, Black for numbers and Thin for units | Blue-black |
| `tide` | Coast: sea level, the next turns, wind, swell | Unbounded Black and Light, hollow for times, Space Grotesk labels | Gradient, hairlines, no cards |

`default.py` is a sixth generator with a different job: it writes the dashboard LevityDash ships for OpenMeteo
(`src/LevityDash/resources/example-config/templates/dashboards/OpenMeteo.levity`, the one a fresh install starts
with), in the same style but with no invented keys, only bundled fonts (Nunito, Barlow Condensed) and only theme
tokens, so Dashboard > Theme recolours it. Its scenario is `scenarios/default.yaml`; `default.png` is its render.
`home.py` is the same dashboard with two rooms indoors, a bedroom and a terrarium (Govee sensors named by identity,
`indoor.…#bedroom`, `indoor.…#terrarium`), written beside it as `home.levity`.

Renders of four of them are beside the files (`rack.png`, `grow.png`, `grid.png`, `tide.png`), and of the default (`default.png`). There is none of `atmos`, because it is set in Apple's fonts.

## Rendering one

```bash
SEED=$(mktemp -d) && cp -r src/LevityDash/devtools/design-seed/. $SEED && mkdir -p $SEED/fonts && cp docs/design-references/showcase/fonts/* $SEED/fonts/
poetry run python src/LevityDash/devtools/render_dashboard.py atmos.png \
  --levity docs/design-references/showcase/atmos.levity --scenario docs/design-references/showcase/scenarios/atmos.yaml \
  --seed $SEED --size 2880x1800 --freeze-time 2026-06-20T18:40:00 --settle 10
```

The `--freeze-time` of each dashboard is in the comment at the top of its `.levity`. To use one for real, copy the
fonts into `<config>/fonts/` and change the keys to ones your plugins publish.

## Editing one

The `.levity` and the scenario are written by `<name>.py` from the helpers in `kit.py`. Edit the generator and run
`python docs/design-references/showcase/build.py`; `tests/test_showcase.py` fails if the files and the generators
differ. Positions are in "board units": percent of the whole dashboard, turned into each card's own percent by `nest`.

## Fonts

`fonts/` holds the faces the last four dashboards use, as static cuts (Qt does not read a variable font's weight
axis here). All are under the SIL Open Font License 1.1: Doto, JetBrains Mono, Fraunces, Instrument Serif, Big
Shoulders Display, Unbounded, Space Grotesk. `atmos` uses Apple's SF Pro Display and SF Compact Display, which
cannot be redistributed and are not here; without them it falls back to the default face. Its two fonts are theme
tokens, so one line changes them.

## What was invented

Real keys (a weather plugin or a Govee sensor publishes them today) are used where they exist. Everything below is
made up, and is the list of plugins these dashboards ask for.

| Dashboard | Invented keys | A plugin that could publish them |
|---|---|---|
| `atmos` | `environment.airQuality.{index, pm25, ozone, pollen}` | AirNow, PurpleAir |
| `atmos` | `environment.precipitation.{tomorrow, probabilityNext24, peakNext24}` | A forecast summary (today `max(key, 24h)` looks back, not ahead) |
| `rack` | `homelab.cluster.*`, `homelab.node.{cpu, memory, temperature}#node` | Proxmox |
| `rack` | `homelab.wan.{down, up, latency, clients, loss}` | UniFi, OPNsense |
| `rack` | `homelab.pool.{used, share}#pool`, `homelab.disk.temperature#bay`, `homelab.backup.age` | ZFS, SMART, a backup tool |
| `rack` | `homelab.power.{draw, today}`, `homelab.ups.{charge, runtime, load}` | NUT, a smart plug |
| `rack` | `homelab.service.response#name`, `homelab.dns.{blocked, queries}` | Uptime Kuma, Pi-hole |
| `grow` | `garden.air.*`, `garden.light.*`, `garden.shelf.*#shelf`, `garden.water.*` | A grow controller, soil probes, a PAR sensor |
| `grid` | `energy.solar.*`, `energy.home.power`, `energy.grid.power`, `energy.battery.*`, `energy.today.*`, `energy.vehicle.*` | An inverter, a home battery, a car charger |
| `tide` | `marine.tide.*`, `marine.swell.*`, `marine.water.temperature`, `marine.wind.*` | NOAA tides and buoys |

Also made up: the service states in `rack` (OK, SLOW, DOWN), the notebook lines in `grow` and the "to 80 % by" time
in `grid` are plain text, where a real dashboard would bind them.

## What the work added to the app

- `tracking`, `italic` and `outline` on any text and on a reading's `valueLabel`.
- `start:` in a Fixture scenario, so a series can begin before today.
