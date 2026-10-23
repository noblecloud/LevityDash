# Bindings

A setting can follow a value. Write a mapping in place of the plain value; it names a key or expression (`of`), and the setting changes when the value does. A plain value is the same setting with nothing to follow, so nothing else about the item changes.

`of` is read as a value source, as for any `key:` in a dashboard, so it may be an expression, and it need not be the key the item shows.

## A colour that follows a value

```yaml
- type: realtime.text
  key: environment.temperature.temperature
  display:
    valueLabel:
      color: {scale: $temperature, of: environment.temperature.feelsLike}
```

| Key | Meaning |
|---|---|
| `scale` | A theme scale (`$temperature`), a preset gradient name, or a gradient written in place. Stops with units (`32°F`) place themselves by reading, in any unit. |
| `of` | A key or an expression. |
| `fallback` | Optional colour used until the value has a number. Default: the default text colour. |

It works on every colour of a text, a gauge (arc, fill, zones, markers, needle, hub, halo, labels) and a bar (track, fill, zones, markers, pointer, labels). An unknown scale name is an error (a gradient would otherwise pick the nearest preset). A saved dashboard writes the mapping back as written, with a theme scale shown as its resolved gradient. The Studio's colour control has a ⟳ button for it.

## A number that follows a value

```yaml
- type: group
  opacity: {of: environment.humidity.humidity, from: [0, 100], to: [0.25, 1]}
```

The reading is placed on the `from` range and the setting takes the matching point of the `to` range, in a straight line.

| Key | Meaning |
|---|---|
| `of` | A key or an expression. |
| `from` | Two numbers, low then high. Either end may carry a unit (`['32°F', '99°F']`); it is converted to the unit the value arrives in. |
| `to` | Two numbers, the setting at each end of `from`. A reversed pair runs backwards. |
| `clamp` | `true` (default) keeps the setting between the ends of `to`; `false` lets it run on. |
| `fallback` | Optional number used until the value has a number. Default: the number the item already had. |

`opacity` is the first property to take it. Every item has `opacity` (0 to 1, and it fades everything inside the item); a result outside 0 to 1 is held to it.

## For code

Both kinds share `lib/ui/follow.py`. A colour setting is read through `ColorSlots` (`lib/ui/colors/bound.py`), a number through `NumberSlots` (`lib/ui/bound_number.py`): a StateProperty adds `decodeNumber` to its decoder, calls `numbers.follow` in its setter and writes the spec back in its encoder.
