# Value Sources

Some options take a value source. A value source is the thing that gives the option its value. It can be one of three kinds:

| Kind | Example |
|------|---------|
| A key | `environment.temperature.temperature` |
| A number | `90` |
| An expression | `max(environment.temperature.temperature, today)` |

An expression is a small calculation. It can use keys, numbers, units, and the history of a key. The result updates when its keys update. A module that uses an expression looks the same as one that uses a key.

## Where you can use an expression

| Option | Used for |
|--------|----------|
| `key:` on a `realtime` module | The value that the module shows. |
| `when:` on any module | Show the module only while the expression is true. See [Switch](/config/dashboard/switch.md). |
| `value:` of a gauge `markers:` entry | The place of the marker on the dial. |
| `from:` and `to:` of a gauge `fill:` | The two ends of the filled part of the dial. |

## Examples

<!-- panels:start -->

<!-- div:left-panel -->

The high and the low of today, on a dial.

Each marker takes an expression. The fill takes two. The module has no other change.

<!-- div:right-panel -->

```yaml
- type: realtime.gauge
  key: environment.temperature.temperature
  title: false
  display:
    arc: {weight: 5%}
    range: {min: 60, max: 110}
    fill:
      from: min(environment.temperature.temperature, today)
      to: max(environment.temperature.temperature, today)
      weight: 5%
      color: '#ff8a3d'
    markers:
      - value: min(environment.temperature.temperature, today)
        type: marker
        length: 12%
        color: '#4aa3ff'
      - value: max(environment.temperature.temperature, today)
        type: marker
        length: 12%
        color: '#ff5a4a'
    value-label: {position: below}
```

<!-- panels:end -->

<!-- panels:start -->

<!-- div:left-panel -->

A module that shows a calculation. `key:` takes an expression, so a module can show how much the pressure changed in the last three hours.

<!-- div:right-panel -->

```yaml
- type: realtime.text
  key: environment.pressure.pressure - at(environment.pressure.pressure, -3h)
  title: Pressure, 3 hours
  alignment: Center
```

<!-- panels:end -->

<!-- panels:start -->

<!-- div:left-panel -->

A value that picks between two keys. This shows the gust when the gust is more than 1.5 times the wind. Otherwise, it shows the wind.

<!-- div:right-panel -->

```yaml
- type: realtime.text
  key: >-
    environment.wind.speed.gust
    if environment.wind.speed.gust > environment.wind.speed.speed * 1.5
    else environment.wind.speed.speed
  title: Wind
  alignment: Center
```

<!-- panels:end -->

## Syntax

### <div class=mono>Operators</div>

| Kind | Operators |
|------|-----------|
| Arithmetic | `+` `-` `*` `/` and brackets `( )` |
| Comparison | `<` `<=` `>` `>=` `==` `!=` |
| Logic | `and` `or` `not` |
| Choice | `a if condition else b` |

### <div class=mono>Functions</div>

| Function | Result |
|----------|--------|
| `min(key, window)` | The lowest value of the key in the window. |
| `max(key, window)` | The highest value of the key in the window. |
| `avg(key, window)` | The average value of the key in the window. |
| `at(key, offset)` | The value of the key at a time, counted from now. `-3h` is three hours ago. `3h` is three hours ahead. |
| `min(a, b, ...)` | The lowest of two or more values. |
| `max(a, b, ...)` | The highest of two or more values. |
| `abs(x)` | The size of a number, without its sign. |

### <div class=mono>Windows and offsets</div>

A window is the span of time that a function reads.

- `today` is from midnight to the next midnight, in your time zone. It includes the data that has been recorded and the forecast.
- A duration, such as `24h`, is the last 24 hours. It ends now.

A duration is a number and one of these units: `ms`, `s`, `m` (minutes), `h`, `d`, `w`. Examples: `90s`, `3h`, `7d`.

A window or an offset can be the second argument of `min`, `max`, `avg`, or `at`. It cannot be used in other places.

> [!NOTE]
> A window needs data over time. A source that gives only the current value has no history to read. `min(key, today)` then has no value.

### <div class=mono>Keys</div>

Write a key as you write it in `key:`. A key has at least two parts that are joined with a dot. A key can have a source before it (`OpenMeteo:environment.temperature.temperature`) and an identity after it (`indoor.temperature.temperature#bedroom`).

## Units in an expression

A number can have a unit. This is a unit literal.

```yaml
- type: text
  text: Hot
  when: environment.temperature.temperature > 90°F
  geometry: {x: 5%, y: 5%, width: 40%, height: 40%}
- type: text
  text: Windy
  when: environment.wind.speed.speed >= 20 mph
  geometry: {x: 50%, y: 5%, width: 40%, height: 40%}
- type: text
  text: Wet
  when: environment.precipitation.precipitation > 0.1 in/hr
  geometry: {x: 5%, y: 50%, width: 40%, height: 40%}
```

A unit literal takes its meaning from the value next to it. LevityDash converts the number to the unit of the data. `90°F` works when the data is in °C. The comparison is correct in both cases.

<div class="indent">

#### <div class=mono>What you can write</div>

- A degree sign and a unit: `90°F`, `32°C`.
- A word or an abbreviation: `30 mph`, `1013 hPa`, `5 mm`.
- A rate: `0.1 in/hr`, `3 mm/hr`.
- A percentage: `55%`.

A space between the number and the unit is optional.

#### <div class=mono>What you cannot write</div>

- A unit of one letter. `5 m` is not read as metres. Use `5 mm`, `5 cm`, or another unit with at least two letters.
- A span of time. `3h` is a duration. A duration is only for a window or an offset.

#### <div class=mono>Units must match</div>

A unit must measure the same thing as the data. `90°F` and a wind speed do not match. The expression then has an error.

A rate keeps its time. Write `0.1 in/hr`, not `0.1 in`. A plain `in` is a length, so it converts as a distance (to miles, for example), not as a rate.

#### <div class=mono>A bare number next to a measurement</div>

A bare number next to a measurement with `+`, `-`, or a comparison is an error. LevityDash does not know the unit of the number. Is the `5` in `temperature - 5` Celsius or Fahrenheit? Write the unit: `temperature - 5°F`.

A comparison with `0` is the one exception for a measure that starts at zero. `rain > 0` is allowed. A temperature is not an exception, because 0°C is not 0°F.

You can always multiply or divide a measurement by a bare number: `wind * 1.5`.

</div>

## When there is no data

- An expression that reads a key with no value has no value. It does not become `0`.
- A module with no value shows `•••`.
- In `when:`, no value counts as false.
- A choice (`a if c else b`) reads only the branch it takes. The other branch can be missing.
- A division by zero has no value.

## When an expression is wrong

LevityDash reads the expression when the dashboard loads. A mistake in the syntax, an unknown function, or an unknown name is an error. The error says what is wrong. The module does not get a value. For `when:`, the module counts as false.

An error that depends on the values, such as a bare number next to a measurement, shows when the expression runs.

> [!NOTE]
> An expression is not Python. LevityDash reads it with its own limited reader. It cannot run code, call other functions, or read files.
