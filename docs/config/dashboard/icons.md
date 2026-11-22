# Glyphs and icon packs

A glyph is a named picture that an item draws instead of, or beside, its text. You write it as `pack:name`, for example `wi:day-sunny`. The item properties that take a glyph are `icon` on a `text` item, `icon` on a `realtime` value label, and the pins of a graph (`pins.glyph`, `pins.steps`, `pins.map`).

LevityDash ships three packs.

| Prefix | Pack | Names |
| --- | --- | --- |
| `fa:` | Font Awesome 6 (`solid`, `regular`, `brands`) | 1852 |
| `mdi:` | Material Design Icons 6 | 6395 |
| `wi:` | Weather Icons | 596 |

```yaml
- type: text
  icon: wi:day-sunny
  text: Clear
```

A name that is not in the pack you asked for is an error tile, not a crash. The error names the closest names it knows: `wi:day-sunnyy` answers `wi: has no glyph named 'day-sunnyy'; did you mean day-sunny?`.

## How a name is found

1. `pack:name` asks that pack. A retired prefix still works: `mdi6:` answers the `mdi` pack.
2. A bare name (`home`, `day-sunny`) is looked for in every pack, in load order. Two packs that share a name resolve to the first one, so write the prefix when it matters.
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

## Check a pack

`IconPack.validate()` answers a list of `(style, what, message)` for every mapping the pack cannot serve: a font that will not load, a font file that is missing, a style with no glyphs, an alias that points at a name the pack does not have, an empty `svg` entry. `tests/ui/test_icons.py` runs it for every shipped pack.

It does not check glyph coverage with `QFontMetrics.inFont`. That call reports false for a large share of the private-use characters these fonts really do draw (1083 of the 1852 Font Awesome names, 1102 of the 6395 Material Design names on macOS), so it would flag working icons as broken.

## Limits

- One colour per glyph. A glyph is a character in an icon font, so it takes the item's `color` and nothing else; there is no second colour, gradient, or outline.
- No animation. A glyph pops from one condition to the next.
- A glyph is a character, so it is sized like text. It does not scale independently of the item's font size.

These three limits are what a vector pack tier would lift; see [the glyph system brief](../tasks/glyph-system.md).
