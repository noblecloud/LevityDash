# Themes

A theme is a set of named colors, fonts, and gradients. A dashboard uses the names instead of the values. When you change the theme, the whole board changes with it.

A name that starts with `$` is called a token. `$accent` is a token for a color. `$mono` is a token for a font. `$temperature` is a token for a gradient.

## Choose a theme

Set `theme:` at the top of the dashboard file. Put the modules under `items:`.

<!-- panels:start -->

<!-- div:left-panel -->

A dashboard that is a plain list has no place for `theme:`. To use a theme, make the file a mapping with two keys: `theme` and `items`.

A dashboard with no `theme:` uses the `default` theme. The `default` theme is white on black. It is how LevityDash always looked.

<!-- div:right-panel -->

```yaml
theme: dusk
items:
  - type: group
    name: board
    items:
      - type: text
        text: Weather at the window
        font: $display
        color: $muted
        geometry: {x: 3%, y: 3%, width: 60%, height: 14%}
      - type: realtime.gauge
        key: environment.temperature.temperature
        title: false
        geometry: {x: 3%, y: 20%, width: 30%, height: 78%}
        display:
          arc: {start-angle: -135, end-angle: 135, weight: 6%, gradient: $temperature}
          range: {min: 0, max: 100}
          needle: {type: circle, length: 8%, width: 5%, color: $accent}
          value-label: {position: center, size: 14%}
      - type: realtime.gauge
        key: environment.humidity.humidity
        title: false
        geometry: {x: 36%, y: 20%, width: 30%, height: 78%}
        display:
          arc: {start-angle: -135, end-angle: 135, weight: 6%, gradient: $load}
          range: {min: 0, max: 100}
          needle: {type: circle, length: 8%, width: 5%, color: $accent}
          value-label: {position: center, size: 14%}
      - type: realtime.text
        key: environment.pressure.pressure
        title: false
        alignment: Center
        geometry: {x: 70%, y: 40%, width: 27%, height: 30%}
        display:
          font: $mono
          valueLabel: {color: $info}
```

<!-- panels:end -->

LevityDash includes three themes:

| Name | Look |
|------|------|
| `default` | White on black. The original look. |
| `dusk` | Light text on a cool, dark blue. One warm accent. |
| `paper` | Dark ink on warm paper. A light theme. |

To change the theme, edit the file and press `Ctrl+R`. A theme change needs a reload.

If the name is wrong, LevityDash logs an error that lists the themes it found. It then uses the `default` theme.

## Use a token

Write the token where you would write a value. A token starts with `$`.

```yaml
color: $accent
font: $mono
gradient: $temperature
```

- A value you write on an item always wins. `color: '#ff0000'` stays red in every theme.
- A token has one name space. `$mono` is a font and `$accent` is a color. The place that reads the token decides which kind it needs.
- If a token does not exist, the item shows an error. The error lists the tokens that do exist. See [When an item fails to load](/common-issues.md).

> [!NOTE]
> A variable and a token both start with `$`. LevityDash looks for a [variable](/config/dashboard/variables.md) first. If no variable has that name, the token is used.

### Standard tokens

Every theme defines these tokens.

| Group | Tokens |
|-------|--------|
| Colors | `background` `surface` `text` `muted` `faint` `rule` `accent` `good` `warn` `bad` `info` `series-1` to `series-6` |
| Fonts | `display` `mono` `body` |
| Gradients | `load` `temperature` |

- `background` is behind the whole board. `surface` is the face of a card.
- `text` is for values. `muted` is for titles and captions. `faint` is for units and tick marks.
- `rule` is for dividers, gauge tracks, and axes.
- `accent` is the one color that draws the eye.
- `good`, `warn`, and `bad` are for data that has a state.
- `series-1` to `series-6` are for graph lines, in the order a board uses them.
- `display` is for titles and labels. `mono` is for numbers that line up. `body` is for everything else.
- `load` is for a value from 0 to 100. `temperature` has stops pinned to °F. The stops follow the reading when the data is in °C.

A theme can add more tokens. For example, a theme can define `solar` and `grid` for a board that shows energy.

## Change a few tokens for one board

Write the theme inline. Use `extends:` to pick the theme to start from. List only the tokens you want to change.

```yaml
theme:
  extends: dusk
  colors:
    accent: '#ffd400'
    solar: '#ffd400'
items:
  - type: text
    text: Solar
    color: $solar
    geometry: {x: 5%, y: 5%, width: 50%, height: 40%}
```

## Make a theme file

A theme is a YAML file. Put it in a folder named `themes` in your [config folder](/config.md). Make the folder if it is not there. A theme in your folder wins over a built-in theme of the same name. The file name is the theme name: `themes/harbor.yaml` is `theme: harbor`.

```yaml
name: harbor
mode: dark
extends: default

colors:
  background: '#0b1620'
  text: '#e6f0f5'
  muted: {color: $text, alpha: 0.65}
  accent: '#4fd1c5'

fonts:
  display: Roboto
  mono: Roboto Mono

scales:
  load: {0: $good, 60: $warn, 85: $bad}
  temperature: {0°F: '#6cb6ff', 70°F: $text, 100°F: $bad}
```

<div class="indent">

#### <div class=mono>name: str</div>

The name of the theme. This is optional. The file name is used if you leave it out.

#### <div class=mono>mode: dark | light</div>

Says if the theme is dark or light. Other parts of LevityDash read it. For example, the beam on a panel uses it to pick its colors. The default is the mode of the theme that you extend.

#### <div class=mono>extends: str</div>

The theme to start from. A token that you leave out comes from this theme. The default is `default`.

#### <div class=mono>colors:, fonts:, scales:</div>

The three groups of tokens.

- `colors` takes any color: a name, a hex value, or a modifier (below).
- `fonts` takes a font family name.
- `scales` takes a gradient. It has the same forms as `gradient:` on an item. A stop can have a unit, such as `70°F`.

</div>

> [!WARNING]
> Quote hex colors. In YAML, `#` starts a comment, so an unquoted `#0b1620` is empty.

> [!WARNING]
> LevityDash can use a font only if the font is installed or bundled. Nunito, Roboto, and Roboto Mono are bundled.

### Color modifiers

A token can be built from another token. Write a mapping with `color:` and one or more modifiers.

```yaml
muted: {color: $text, alpha: 0.65}
```

| Modifier | Effect |
|----------|--------|
| `alpha: 0.4` | Sets the opacity. `1` is solid. |
| `lighten: 0.1` | Makes the color lighter. A negative number makes it darker. |
| `darken: 0.1` | The same as `lighten`, with the sign reversed. |
| `chroma: 0.8` | Multiplies the color strength. A number below `1` makes the color more grey. |
| `hue-shift: 30` | Turns the hue by this many degrees. |
| `mix: {with: $background, by: 0.3}` | Moves the color toward another color. `by: 1` gives the other color. |

Lightness, chroma, and hue use the Oklch color space. Mixing uses Oklab. You can use a modifier in a theme file and on an item in a dashboard.

## What a theme does not change yet

- The dark glow on a gauge needle.
- The Moon.
- A color that is written as a value in the code.

## Look at a board in each theme

The render tool can force a theme over the one in the file. Use it to compare themes.

```bash
poetry run python src/LevityDash/devtools/render_dashboard.py out.png \
    --levity my-board.levity --scenario stormy-day --theme paper
```
