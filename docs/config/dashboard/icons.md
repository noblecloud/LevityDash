# Glyphs and icon packs

A glyph is a named picture that an item draws instead of, or beside, its text. You write it as `pack:name`, for example `wi:day-sunny`. The item properties that take a glyph are `icon` on a `text` item, `icon` on a `realtime` value label, and the pins of a graph (`pins.glyph`, `pins.steps`, `pins.map`).

LevityDash ships these packs.

| Prefix | Pack | Kind | Names |
| --- | --- | --- | --- |
| `fa:` | Font Awesome 6 (`solid`, `regular`, `brands`) | font | 1852 |
| `mdi:` | Material Design Icons 6 | font | 6395 |
| `wi:` | Weather Icons | font | 596 |
| `wiv:` | Weather Icons | vector, `0 0 30 30` | 219 |
| `qw:` | QWeather Icons | vector, `0 0 16 16` | 507 |
| `meteo:` | Meteocons (monochrome) | vector, `0 0 128 128` | 519 |
| `vec:` | Levity Vectors (arrows, sun, moon, cloud, wind, compass, gauge) | vector, `0 0 24 24` | 16 |
| `mxn:` | Meteocons (animated: SMIL, played by the item) | animated SVG, `0 0 128 128` | 475 |
| `ph:` | Phosphor (`regular`) | vector, `0 0 256 256` | 1512 |
| `tb:` | Tabler (`outline`) | vector, `0 0 24 24` | 5491 |
| `lu:` | Lucide | vector, `0 0 24 24` | 2102 |
| `io:` | Iconoir (`regular`) | vector, `0 0 24 24` | 1382 |
| `rx:` | Remix Icon (`fill`) | vector, `0 0 24 24` | 1539 |
| `bi:` | Bootstrap Icons | vector, `0 0 16 16` | 2078 |

`wi:` and `wiv:` carry the same names from the same project — one font, one set of exported shapes. Keep `wi:` in a value that must not change; use `wiv:` where a vector draws better at size.

```yaml
- type: text
  icon: wi:day-sunny
  text: Clear
```

A name that is not in the pack you asked for is an error tile, not a crash. The error names the closest names it knows: `wi:day-sunnyy` answers `wi: has no glyph named 'day-sunnyy'; did you mean day-sunny?`.

## How a name is found

1. `pack:name` asks that pack. A retired prefix still works: `mdi6:` answers the `mdi` pack.
2. A bare name (`home`, `day-sunny`) is looked for in every pack. A declared alias is checked first, because an explicit mapping is the stronger statement; then real names, packs in **prefix order**, so the answer is the same every run. Two packs that share a name resolve to the first one, so write the prefix when it matters.
3. A pack's `aliases` table maps another vocabulary onto its own names. The weather pack, for example, accepts the forecast-io names `clear-day`, `clear-night`, `partly-cloudy-day`, and `partly-cloudy-night`.
4. `icon:` in front of the whole value is ignored, so `icon:wi:rain` is the same as `wi:rain`.

Lookup results are cached per pack, so an item that redraws often does not reload a font or resolve a name again.

## A pack is data

A pack is one TOML file in `resources/icons/maps/`. Your own packs go in the `icons/maps` folder of your configuration folder, which is read first, so your file wins over a shipped pack with the same prefix.

```toml
[my-icons]
prefix = "my"
name = "My Icons"          # optional, shown in error messages
default = "regular"        # optional, the first style with a font otherwise
also = ["mine"]            # optional, other prefixes that resolve to this pack

[my-icons.aliases]         # optional
clear = "sun"

[my-icons.regular]
font = "{__resources__}/icons/weathericons.ttf"

[my-icons.regular.chars]
sun = "0xf00d"             # a code point, or the character itself
cloud = "0xf013"
```

- Every style table needs a `font`. A style without one falls back to the default style's font.
- `{__resources__}` is the app's resources folder. Use it for a font that ships with the app; an absolute path works for one that does not.
- `chars` values are a code point in hex (`0xf00d`) or the character itself. Case names in lower case with hyphens, the way the shipped packs do.
- A style may also carry an `svg` table of raw path data. Font Awesome does; the weather and Material Design packs are font-only today.

A pack that will not parse is logged and skipped. One bad user file cannot stop the window from opening, and the other packs still load.

## Vector packs

A style can carry path data instead of a font. This is the same map file, with an `svg` table and a `viewBox`:

```toml
[vector.line]
viewBox = "0 0 24 24"
stroke = 2

[vector.line.svg]
sun = 'M12 7 A5 5 0 1 1 12 17 A5 5 0 1 1 12 7 Z M12 1.5 V4 M12 20 V22.5'
```

- `stroke` is a width in `viewBox` units. Set it for line art (Lucide, Tabler, Iconoir are all stroke-only). The outline is baked into the glyph, so the item still fills it with one brush. Without `stroke`, the path is filled as drawn.
- A vector glyph is square: it occupies a box one cap height wide and tall, sitting on the baseline, and it takes the item's `color`. It is not a character, so it does not follow `font`, `weight`, or letter spacing.
- `vec:` ships with the app: `arrow-up`, `arrow-down`, `arrow-left`, `arrow-right`, `plus`, `minus`, `dot`, `ring`, `sun`, `moon`, `cloud`, `rain`, `snow`, `wind`, `gauge-low`, `compass`.

The parser is `lib/ui/svgpath.py` and covers the whole `d` grammar — `M L H V C S Q T A Z`, absolute and relative, implicit repeats, elliptical arcs converted to cubics, and `transform` (translate, scale, rotate, matrix, skew).

A glyph may also be a list of parts, when its pieces do not share one mode:

```toml
[meteocons.mono.svg]
clear-day = [
  { d = "M64 16…", role = "body" },
  { d = "M64 46…", stroke = 4 },
  { d = "M64 58…", role = "cutout" },
]
```

- `stroke` on a part strokes that part (`fill="none"` in the source); without it the part fills.
- `role = "cutout"` is subtracted from the rest, which is how a monochrome set draws a hole in a bigger shape with one colour.
- `transform` is kept and applied to that part.
- `role = "body"` (the default) is the glyph. `accent`, `edge` and `shadow` are reserved for sets with more than one tone.

### Converting a set

```sh
.venv/bin/python src/LevityDash/devtools/import_svg_pack.py SOURCE_DIR OUT.toml \
    --prefix qw --name "QWeather Icons" --style regular --strip qi- --precision 2
```

It reads paths and the basic shapes (`circle`, `ellipse`, `rect`, `line`, `polyline`, `polygon`), keeps each part's stroke and transform, turns `fill="white"` into a `cutout`, and drops gradients, masks, filters and clip paths with a warning. `--precision` rounds coordinates, which matters for a dense set: Meteocons' 519 glyphs are 1.3 MB at two decimals. A set with more than one `viewBox` is refused rather than drawn wrong.

The shipped vector maps are generated this way: `wiv:` from weather-icons' own `svg/` folder, `qw:` from `qwd/Icons/icons`, `meteo:` from `@meteocons/svg-static` (monochrome).

Provenance of the three vendored maps:

| Map | Source | Revision |
| --- | --- | --- |
| `weather-vector.toml` | https://github.com/erikflowers/weather-icons `svg/` | `bb80982`, 2021-12-13 |
| `qweather.toml` | https://github.com/qwd/Icons `icons/` | `d7d4ef4`, 2025-12-02 |
| `meteocons.toml` | `@meteocons/svg-static` (npm), `monochrome/` | 0.1.0 |
| `meteocons-animated.toml` + `icons/animated/meteocons/` | `@meteocons/svg` (npm), `monochrome/` | 0.1.0 |
| `phosphor.toml` | https://github.com/phosphor-icons/core `assets/regular/` | `2b75f3ad` |
| `tabler.toml` | https://github.com/tabler/tabler-icons `icons/outline/` | `85e870d` |
| `lucide.toml` | https://github.com/lucide-icons/lucide `icons/` | `e00b2b2` |
| `iconoir.toml` | https://github.com/iconoir-icons/iconoir `icons/regular/` | `39834e3` |
| `remix.toml` | https://github.com/Remix-Design/RemixIcon `icons/**/*-fill.svg` | `9fb7967` |
| `bootstrap.toml` | https://github.com/twbs/icons `icons/` | `829d2bc` |

To regenerate one: clone or `npm pack` the source, then run the converter with the prefix, style and `--precision 2` shown above. Nothing calls the converter at runtime, so a map is a build artifact that can be rebuilt at any time from a stated revision.

### Colour

A vector glyph paints with the item's `color`, or with the theme's token when the item names none. Roles decide the rest:

| role | default token | meaning |
| --- | --- | --- |
| `body` | `$text` | the glyph itself |
| `accent` | `$accent` | a second tone — a highlight, a badge, a lit part |
| `edge` | `$rule` | an outline layer |
| `shadow` | `$surface` | a backing plate |
| `cutout` | — | subtracted from the others; it is never painted |

A pack may choose its tokens, and a theme may override a pack by name:

```toml
[meteocons]
prefix = "meteo"
colors = { body = "$accent", accent = "$warn" }
```

```yaml
# themes/dusk.yaml
glyphs:
  meteo: { body: $muted, accent: $accent }
```

The theme's word wins, then the pack's, then the standard token. All three are read at paint time through `Color.role`, so a theme switch repaints without rebuilding a pack. An item's own `color:` beats all of them.

### `glyph-color`

How a vector glyph asks for its colours:

- `themed` (default) — one token per role, as above. A two-tone glyph draws its `accent` as a child path with its own brush, so it is genuinely two colours.
- `mono` — every role in the body colour; the glyph becomes one silhouette.
- `native` — reserved for a pack that carries its own palette; today it behaves as `themed`, because the converter flattens colour into roles.

```yaml
- type: text
  text: "x"
  icon: meteo:clear-day
  glyph-color: mono
```

### Animation

A style may point at a folder of SVG files that animate themselves:

```toml
[meteocons-animated.mono]
viewBox = "0 0 128 128"
dir = "{__resources__}/icons/animated/meteocons"
animated = true

[meteocons-animated.mono.svg]
clear-day = "clear-day.svg"
```

The item hosts the file in a `QSvgRenderer` and advances `setCurrentFrame` on a timer at the file's own frame rate. Qt 6 plays SMIL `animateTransform` and CSS `@keyframes`; it does not animate plain attributes (`<animate attributeName="r">` stays still on this build). The item substitutes the theme colour into the SVG's paint before rendering, because a renderer bakes the file's `black` in.

`mxn:` is the shipped example: 475 animated Meteocons. A theme switch re-renders rather than restarting a frame loop, and a static pack starts no timer at all.

<!-- panels:start -->

<!-- div:left-panel -->

Any item that takes `icon:` takes a vector glyph. There is nothing to opt into: the prefix says which pack, and the pack says whether it is a font or a path.

<!-- div:right-panel -->

```yaml
- type: text
  text: "x"
  icon: vec:wind
```

<!-- panels:end -->

## Check a pack

`IconPack.validate()` answers a list of `(style, what, message)` for every mapping the pack cannot serve: a font that will not load, a font file that is missing, a style with no glyphs, an alias that points at a name the pack does not have, an empty `svg` entry. `tests/ui/test_icons.py` runs it for every shipped pack.

It does not check glyph coverage with `QFontMetrics.inFont`. That call reports false for a large share of the private-use characters these fonts really do draw (1083 of the 1852 Font Awesome names, 1102 of the 6395 Material Design names on macOS), so it would flag working icons as broken.

## Limits

- A font glyph is sized like text; a vector glyph reserves a square one cap height wide. Neither scales independently of the item's font size, and a vector glyph does not fill the box edge to edge — the artwork's own padding stays.
- `native` colour mode is a placeholder: the converter records roles, not the pack's original palette.
- Animation covers what Qt SVG plays (SMIL `animateTransform`, CSS `@keyframes`). SMIL attribute animation and Lottie are not wired.
- Morphing one glyph into another (the roadmap's Morphicons item) is not implemented; a condition still pops.
- A two-tone glyph paints its `accent`/`edge`/`shadow` as child items, so an item's hit shape is its body only.

These are what the rest of the glyph brief is for; see [the glyph system brief](../tasks/glyph-system.md).
