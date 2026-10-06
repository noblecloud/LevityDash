# Variables

A variable gives a name to a value. You write the value once. You use the name in as many places as you like.

Use a variable to keep a number the same on several gauges, to name a key you use often, or to change one setting for the whole board.

## Define a variable

Set `vars:` at the top of the dashboard file. Put the modules under `items:`. This is the same file shape that [themes](/config/dashboard/themes.md) use, and one file can have both.

<!-- panels:start -->

<!-- div:left-panel -->

Each entry in `vars:` is a name and a value. A name has letters, digits, `_`, and `-`. It does not start with a digit.

Write `$name` where you want the value. In the example, two gauges share the same range and arc weight. They are both defined once.

<!-- div:right-panel -->

```yaml
vars:
  temp: environment.temperature.temperature
  lo: 30
  hi: 110
  weight: 10%
  hot: 90
items:
  - type: group
    name: main
    items:
      - type: realtime.gauge
        name: outside
        key: $temp
        title: false
        geometry: {x: 0%, y: 0%, width: 50%, height: 100%}
        display:
          radius: 90%
          arc: {gradient: TemperatureGradient, weight: $weight}
          range: {min: $lo, max: $hi}
          zones:
            - {from: $hot, to: $hi, color: '#ff6a4a'}
          value-label: {position: below}
      - type: realtime.gauge
        name: dewpoint
        key: environment.temperature.dewpoint
        title: false
        geometry: {x: 50%, y: 0%, width: 50%, height: 100%}
        display:
          radius: 90%
          arc: {gradient: TemperatureGradient, weight: $weight}
          range: {min: $lo, max: $hi}
          value-label: {position: below}
```

<!-- panels:end -->

## Whole value or part of a value

There are two ways to use a variable.

- **A whole value.** The value is exactly `$name`. The result is the variable, with its own type. In the example, `min: $lo` is the number `30`, not the text `30`.
- **Part of a text.** `$name` is inside a longer text. The value of the variable is put into the text. Write `${name}` when a letter, digit, or `_` follows the name. Also write `${name}` for a name that has a hyphen in it.

```yaml
vars:
  place: Porch
  gap: 3mm
items:
  - type: stack
    padding: $gap                       # a whole value: 3mm
    items:
      - type: text
        text: ${place}_north            # part of a text: Porch_north
        alignment: CenterLeft
      - type: realtime.text
        key: environment.temperature.temperature
        title: $place temperature       # part of a text: Porch temperature
```

## Use a variable inside an expression

A variable can hold a unit, a key, or a part of an [expression](/config/dashboard/expressions.md). The variable is put into the text before the expression is read.

```yaml
vars:
  temp: environment.temperature.temperature
  hot: 90°F
items:
  - type: text
    text: Hot
    color: '#ff6a4a'
    when: $temp > $hot            # environment.temperature.temperature > 90°F
    geometry: {x: 5%, y: 5%, width: 40%, height: 40%}
```

## Rules

- A variable can use a variable that is defined before it. It cannot use one that is defined after it.
- A name that is not a variable stays as it is. The [theme](/config/dashboard/themes.md) then gets it. For example, `$accent` goes to the theme. An unknown token is an error that lists the tokens it knows.
- Variables work everywhere in the dashboard file, including an inline `theme:`. They do not reach into a separate theme file.
- If `vars:` is wrong, LevityDash logs the error and loads the file without variables. The board does not fail to load because of it.

## What a save writes

When you edit a dashboard in the app and save it, LevityDash keeps your variables.

- A value that you did not change is saved as the `$name` text.
- A value that you changed in the app is saved as its new value. The `$name` text is gone for that value. Edit the file by hand if you want to use the variable again.
- The `vars:` block is always saved.
