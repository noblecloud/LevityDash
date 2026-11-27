# Weather maps

`type: map` draws a map of the weather around you: rain radar that loops over the last two hours, or a smooth picture of temperature, wind or cloud across the region. Nothing needs a key.

```yaml
- type: map
  layer: radar            # radar | temperature | wind | clouds | none
  zoom: 6                 # 1 world .. 16 street
  lat: 40.7               # left out: [Location] from your config
  lon: -74.0
```

A map with no `lat` and `lon` is centred on `[Location]`, and a dot marks that place.

| Setting | Default | What it does |
|---|---|---|
| `layer` | `radar` | `radar`, `temperature`, `wind`, `clouds`, or `none` for just the base map. |
| `lat`, `lon` | `[Location]` | The centre. |
| `zoom` | `6` | 1 shows the world, 16 a street. Fractions are fine. Radar data stops at 7 and is stretched past that. |
| `basemap` | `auto` | `auto` follows the theme's background (dark or light), or choose `dark`, `light`; `none` draws the layer on the dashboard itself. |
| `labels` | `true` | Place names over the data. |
| `opacity` | `0.92` radar, `0.74` fields | How solid the data layer is, `0` to `1`. |
| `animate` | `true` | Radar loops through the last two hours. `false` shows the newest picture. Click the map to pause. |
| `speed` | `600` | Milliseconds a radar frame shows. The newest frame stays three times as long. |
| `refresh` | `300` | Seconds between asking RainViewer for new radar pictures. |
| `marker` | `true` | The dot at your `[Location]`. |
| `legend` | `true` | The colour scale, bottom left. |
| `stamp` | `true` | The layer's name and time, top left. |
| `range` | | `[low, high]`: the ends of the wind (m/s) or temperature (°C) scale. |
| `tiles` | | A base map of your own: an XYZ URL with `{z}`, `{x}` and `{y}` in it. |

## Where it comes from

- **Radar**: [RainViewer](https://www.rainviewer.com/), composite radar for most of the world, a new picture every ten minutes. The service paints its own colours, so each colour is read back as an echo strength and drawn again in a palette that belongs to the dashboard (below). It is free for personal use and stops at zoom 7.
- **Temperature, wind, clouds**: [Open-Meteo](https://open-meteo.com/). One request for a coarse grid of points over the map (up to 70) every half hour, smoothed with a spline into a picture and clipped to the range of the points, so it shows the pattern across a region, not any one town. Wind also draws an arrow at each point. Open-Meteo's free tier is for non-commercial use and counts every point as a call.
- **Base map**: Esri's grey canvas tiles, read as sea and land and redrawn in your theme's `background`, `text` and `faint`, so it sits in the dashboard instead of on it. Credit for each service is printed small in the corner.

Tiles are kept on disk under the app's cache directory (`maps/`) and sit out a restart.

If a service cannot be reached the map keeps what it has and asks again a minute later. It never blocks the dashboard.

## The colours

The palettes are written in Oklch, so the middle of every ramp stays vivid instead of going grey the way an sRGB mix does (`lib/.../weathermap/palette.py`).

- **Rain** runs from a pale cyan drizzle through blue and violet to magenta, with a warm core for the heaviest cells. Light rain is almost see-through; heavy rain is nearly solid.
- **Temperature** has a quiet middle: the soft green-to-yellow band is your `[Comfort]` range, and the colder and hotter stops slide with it (the same rule as the temperature gradients). Set `[Comfort] low` and `high` and the map follows.
- **Wind** is clear in calm air, then teal, green, amber and red.
- **Clouds** are a cool white that thickens.

## Trying it

```bash
poetry run python src/LevityDash/devtools/render_widget.py \
  --levity docs/design-references/maps/map-radar.levity --scenario hot-clear-day \
  --name map --out map.png --size 1000x640 --settle 20
```

The render has to wait for the tiles, so give it a long `--settle`. Other examples are in `docs/design-references/maps/`.
