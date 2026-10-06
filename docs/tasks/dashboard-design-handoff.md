# Dashboard design handoff (weather boards)

Paused 2026-10-06 when the project's token budget ran out. Branch
`claude/dashboard-design-uy2w74` (draft PR #22: process table and the
max-length fix).

## Where things are
- Mockups: `docs/design-references/weather-boards.html` (open in a browser). The
  same page is published at https://claude.ai/artifact/Rit1u69z54f7vSg7rE5cKt.
- Technique notes: `/mnt/project-files/levitydash/cascading-options.md` (cascading
  options, the clock lesson, the 2022 board, density).
- Theme roles: `/mnt/project-files/levitydash/themes.md`. The theme engine is PR #24 (`$token`).

## State of the boards
- **Core + rotation** (top of the page). Fixed heroes: temperature, wind and rain.
  Satellites: humidity and pressure. One `switch` slot rotates sun & UV, sky, moon
  and soil. A conditional Lightning panel takes the slot when a strike is within 10 mi
  (alerts beat rotation). Rain switches to a storm state above 0.3 in/hr. There are
  three layered graphs: temperature with feels, dew point and humidity; wind speed
  inside its gust band; rain (past and forecast) with chance and pressure. The
  12-hour and 7-day tables run along the bottom.
- **Station**: 16:10. Gauge heroes (humidity ring, UV bar, wind compass, rain
  rate). A detail band of about 30 readings sits under them. One base graph
  layers temperature, feels, dew point, humidity, pressure and rain chance.
- Everything (about 110 readings, ten panels) is the density ceiling. Storm, Sky
  and Week are parked; they need the engine features listed below.
- Neal liked Core and Station. He has not picked which to build first.

## Neal's feedback (follow it)
- Dense, with hierarchy. Station-level density was "still super data sparse";
  Everything was "a bit of an overcorrection". Aim near Everything with clear heroes.
- Display: 15in retina, 2880x1800. Mock and render at 16:10.
- Combine graphs. Layer series into a few graphs, not one sparkline per panel.
- Colour: saturated and brilliant on pure black. Use `#ff9124`, `#14e3c0`,
  `#1a8cff`, `#ffd400` and `#ff3048`, with light-grey labels (`#a3a7b0`). Pastels
  read as "too faint".
- Use more than one font: Nunito for heroes, Roboto Mono for figures, Roboto for labels.

## Keys and engine gaps
- Keys are in the "Keys" notes under each board on the page. Most are standard
  `environment.*` keys. Low, high and trend use `min/max(k, 24h)` and `k - at(k, -1h)`.
- Missing:
  - arg-min/arg-max for "low at 05:12" and "rain after 3 pm".
  - a threshold-to-text function for the plain-words lines.
  - linear bar meters.
  - pointer shapes (needle → pointer rename).
  - a gauge whose range is a pair of datetimes (the sun arc).
  - bar plots and a filled band (gust band) in Graph.
  - the `switch` slot with `when`, `cycle` and `hold`, which is being built in the
    conditional-panels thread (`claude/conditional-panels*`, draft PR into feat/value-sources).

## Next
1. Neal picks Station or Core.
2. Write the .levity on feat/value-sources (Core uses `switch` syntax). Add a
   weather scenario with the needed keys, render offscreen at 2880x1800 and
   compare against the mockup.
3. Drop cells whose engine gap isn't filled yet. Never pad with keys nothing publishes.
