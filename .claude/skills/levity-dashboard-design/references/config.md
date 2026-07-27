# `.levity` configuration inventory

What the layout/display engine can actually do. Read this when you need an
option name, or want to know whether an idea is expressible before designing
around it.

Verified against the source 2026-07-27. When something here disagrees with the
code, the code wins — grep for `@StateProperty(key='…')` in
`lib/ui/frontends/PySide/Modules/` to check.

## Contents

- [Item types](#item-types)
- [Geometry and sizing](#geometry-and-sizing)
- [Groups, stacks, and inheritance](#groups-stacks-and-inheritance)
- [Text and values](#text-and-values)
- [Gauges](#gauges)
- [Gradients](#gradients)
- [Sizing groups](#sizing-groups)
- [Keys](#keys)

## Item types

Used as `type:` on an item.

| type | what it is |
|---|---|
| `realtime.text` | a value as text, with optional title and unit |
| `realtime.gauge` | a value as a dial/ring — a `Realtime` whose *display* is a gauge |
| `graph` | time-series plot |
| `titled-group` | a group with a heading |
| `group` | bare container, positions children by `geometry` |
| `stack` | lays children out along an axis by `size` |
| `value-stack` | stack specialised for labelled values |
| `clock`, `moon` | the clock and moon-phase items |

⚠️ A bare `type: gauge` silently loads a plain `Panel` — `itemLoader` has no
`gauge` case, so it falls through to `case str(panel)`. The gauge is the
*display* of a `realtime`, hence `realtime.gauge`.

## Geometry and sizing

`geometry:` positions an item inside its parent:

```yaml
geometry: {x: 0%, y: 0%, width: 50%, height: 100%}
```

Sizes accept `%` (of parent), `px`, `mm`, `cm`. Physical units survive a
resolution change, which is why titles are usually `mm`.

Other panel-level keys: `margins`, `padding`, `opacity`, `border`, `name`.

## Groups, stacks, and inheritance

`stack` distributes children along `direction: Horizontal | Vertical`:

```yaml
- type: stack
  direction: Horizontal
  spacing: 10px
  dividers: {enabled: true, opacity: 20%, size: 84%}
  preset:
    title: {height: 0.7cm}
  items: [...]
```

- `size:` on each child is its share.
- `spacing` costs real space **on top of** the declared sizes. Five panels with
  `spacing: 10px` on 1920px eats ~2%, so sizes should sum to ~97%, not 100%.
  Overflow is silent — the last panel runs off the edge.
- `dividers` draw a line between children. Useful for binding by *common
  region* when proximity alone can't group things.
- `preset:` / `shared:` push defaults into children.

⚠️ **`shared:` overrides a child's `title: false`.** A child told not to have a
title gets one anyway, and if a sibling also has one the cell shows two. When
any child needs to opt out, set titles per item rather than in `shared`.

## Text and values

On a `realtime.text` item:

```yaml
- type: realtime.text
  key: environment.temperature.temperature
  title: {text: Feels, height: 2.8mm, font: Roboto, matchingGroup: title@stats}
  display:
    font: Roboto Mono
    unitPosition: FloatUnder
    format: '%-I:%M%p'          # datetimes; measurements take a format spec
    valueLabel: {matchingGroup: value@stats}
  geometry: {...}
```

**`display` keys:** `font`, `weight`, `format`, `format-hint`, `unitPosition`,
`unitSize`, `unit-string`, `unitLabel`, `valueLabel`, `max-length`,
`floating-offset`, `null`, `text-height`, `text-scale-type`.

**`unitPosition`** (`DisplayPosition`): `Auto`, `Inline`, `NewLine`, `Above`,
`Below`, `Hidden`, `Inside`, `Outside`, `Floating`, `FloatUnder`,
`TrailingValue`, `LeadingValue`.

`FloatUnder` puts the unit under the value as its own small label — good when an
inline unit would crowd a large number.

⚠️ **Units are strings, not booleans.** `unit_symbol: True` renders the literal
word `True` (`61True`). Omit the key or pass a real string. Same trap for
`unit_spacer`.

Datetimes need an explicit `format` or they render `10:05:41`; use
`'%-I:%M%p'` → `10:05am`.

## Gauges

```yaml
- type: realtime.gauge
  key: environment.wind.speed.speed
  title: false
  display:
    radius: 92%
    arc:
      gradient: WindSpeedGradient
      weight: 13%
      start-angle: -120        # default
      end-angle: 120           # default
      cap: FlatCap
    needle: {type: Needle, width: 7%, length: 80%, offset: 0}
    major: {enabled: true, count: …, interval: …, labels: {rotate: false, height: 2.6mm}}
    minor: {enabled: true}
    micro: {enabled: true}
    value-label: {visible: true, position: below, font: Roboto Mono, format: {…}}
    unit-label: {visible: true, position: below}
    range: {min: …, max: …}
  geometry: {...}
```

- **Ring, not dial:** `major/minor/micro: {enabled: false}` removes graduations,
  leaving arc + needle. Good as a compact indicator beside a number.
- **Corner/partial gauges:** `arc.start-angle` / `end-angle` (default −120/+120)
  make quarter-arcs and other sweeps — a quarter arc tucked into a corner is
  expressible.
- **Graduation labels:** `major.labels.rotate: false` keeps tick numbers upright
  rather than following the arc; upright usually reads better on small dials.
- `value-label` / `unit-label` both take `visible`, `position`, `font`, `format`.

⚠️ **`value-label: {position: center}` does not centre** — known
`_center_transform` gap; the value lands beside the ring. Don't chase it with
radius tweaks. Compose explicitly instead: a gauge with
`value-label: {visible: false}` plus a sibling `realtime.text`, which also gives
full control over where the number sits.

## Gradients

Referenced by name under `arc.gradient`. Defined in `lib/ui/colors/presets.py`:

`TemperatureGradient`, `RainbowTemperature`, `RainbowDefault`,
`RainbowPercentage`, `PrecipitationProbabilityGradient`,
`PrecipitationRateGradient`, `UVIndexGradient`, `WindSpeedGradient`,
`PressureGradient`, `HumidityGradient`, `CloudCoverGradient`,
`FabledSunsetGradientLux`, `FabledSunsetGradientWattsPerSquareMeter`,
`PurpleSunset`, `PlumPlate`, `HappyFisher`, `RipeMalinkaGradient`.

Gradients map to **absolute values**, not to the gauge's own range — a gradient
built for a 0–11 UV scale will look wrong on a 0–100 dial.

There is no YAML syntax for defining gradients yet; new ones are added to
`presets.py`. A user-editable colours file is a known open idea.

## Sizing groups

`matchingGroup: <name>` makes items share a computed text size, so a row of
readings doesn't render at slightly different sizes.

Groups cluster by **proximity** (`lib/ui/Groups.py`), so items far apart may not
equalise even with the same group name.

⚠️ A lone short value (`0`, `8`) in a tall cell fits far larger than `71°` in
the same box and can tower over its neighbours. Give short values company, or
constrain the cell.

## Keys

`CategoryItem` carries two orthogonal extras:

- **`@source`** — *who* provided it. Multiple sources for one key are reconciled
  into a single value by `MultiSourceContainer`.
- **`#identity`** — *which* value it is (`indoor.temperature.temperature#bedroom`).
  Never merged; two identities are two different readings.

A key with no publisher renders `•••` forever. Before adding a value, confirm
something actually publishes it — the control plane will tell you
(`plugin_status` reports each plugin's `keyCount` and `lastPublish`).
