# Gradient stops at real unit values

**Audit 2026-10-10: partly done.** Merged into `feat/value-sources` on 2026-10-05. The running-dashboard edit mode is still open.

Suggested branch: `feat/gradient-unit-stops` off `feat/value-sources`. Start it after
`fix/warp-smooth` merges, because both edit `devtools/_studio_editors.py`.

Status: implemented on `feat/gradient-unit-stops`. The running-dashboard edit mode is still open.

## What the user asked for

> for the gradients, you should be able to set an actual unit value. like "red at 99ºf"
> kind of deal. tho not like that in english, but you get what I mean, right?

A gradient stop should be pinned to a measured value, such as 99 °F, 30 mph or 1.2 in/hr.
It should not be a bare float or a position along the scale. The colour then sits at the
same reading whatever the gauge's range, and whatever unit the data arrives in.

## Where things are

- `src/LevityDash/lib/ui/colors/gradient.py`: `Gradient` (a dict of
  `MappedGradientValue`) and `Gradient.decode`, which takes a dict, a list or a preset
  name.
  - Presets in `colors/presets.py` (for example `TemperatureGradient`) already carry
    unit-typed values through `MappedGradientValue[<unit class>]`.
  - Stops written in YAML are plain numbers, whose meaning depends on the receiving
    display.
  - `Gradient.QtGradient` converts values to the plot's data type
    (`self.plot.data.dataType`). Read it first: some of the conversion machinery exists.
- Gauge and graph use gradients through `ColorGradientMixin` (Gauge.py) and Plot
  (Graph.py).
- In Gauge Studio, the gradient stop list editor is in `devtools/_studio_editors.py`.
  The zone and marker editors already have a "values in" WeatherUnits unit selector.
  Reuse that.

## Expected change

1. **YAML.** A stop key or value may carry a unit:

   ```yaml
   gradient:
     32°F: '#4aa3ff'
     70°F: '#7bd88f'
     99°F: '#ff4a4a'
   ```

   A list form also works: `- {at: 37°C, color: '#ff4a4a'}`. Parse the unit with
   WeatherUnits, using the same parser that range, zone and marker values use. Convert
   each stop into the display's data unit when the stops are applied. A bare number keeps
   its current meaning, so existing files do not change.
2. **Mixed units** in one gradient are allowed, and each stop converts on its own. A
   unit whose type does not match the data, such as mph on a temperature, logs one
   clear error naming the stop. That stop is then skipped, and the display is not
   aborted.
3. **Encoding.** Write a stop back in the unit it was written in, so the YAML
   round-trips unchanged. Encode as plain strings only, never measurement objects
   (see the StateProperty encoder gotcha in CLAUDE.md).
4. **Studio.**
   - Each gradient stop row gets a value slider with a number box and a unit dropdown,
     using the same selector as zones.
   - Give each stop a colour swatch.
   - **Collapsed by default.** The user asked: "have the gradient colors collapsed by
     default and only showing a color band". A collapsed gradient shows one row: a
     colour band drawn across the gauge's range, with small ticks at each stop.
     Clicking the band or a disclosure arrow expands the stop list. The collapsed or
     expanded state persists per Studio session.
   - **Gradient edit mode with draggable nodes.** This is required, not optional. The
     user asked: "we need a gradient edit mode with dragible nodes. Both in the little
     config editor but also on the actual meters".
     - **In the editor:** the colour band becomes a gradient bar with one node per
       stop. Drag a node to move its stop; the value snaps to the property's unit
       step. Click empty band to add a stop with the colour sampled there.
       Double-click a node to pick its colour. Drag a node off the bar, or press
       Delete, to remove it. The value and unit fields stay in step with the nodes.
     - **On the meter:** a toggle, "Edit gradient", in the gradient row and in the
       preview toolbar. While it is on, the drag handles layer (`_studio_handles.py`)
       draws one node per stop on the track, at the stop's value. The same drag, add,
       remove and recolour actions work there, and each node shows its value and unit
       while dragged. The other handles dim, so the two kinds don't fight for the
       mouse.
     - One drag is one undo step, in both places.
     - Nodes are placed through the gauge's value-to-angle mapping. After the meter
       refactor (`docs/tasks/meter-and-bar.md`) they should go through
       `Scale`/`Track` instead, so bars get gradient nodes for free. Leave a note at
       that spot if the refactor has not landed yet.
     - The same mode in the running dashboard's own edit mode is a follow-up. Don't
       build it here.
   - Use a distinct default colour for a new stop. Today a new stop repeats the last
     colour.

## Verification

Use real renders. Small tests are allowed only for the parse and convert maths.

- Render a temperature gauge whose gradient is pinned at 32 °F, 70 °F and 99 °F. Do it
  twice: once with the data in °F, once in °C. The colour at the needle must match
  between the two.
- Render the same gradient on a range of 0-120 °F and on a range of 40-100 °F. Each stop
  must stay at its reading, not at its fraction of the range.
- Open the stop editor in Studio offscreen. Switch a stop's unit and check that the
  render does not change. Export, reload, and confirm the YAML is unchanged.
- Run `pytest tests -q -p no:cacheprovider`.
- Use offscreen only, and end each script with `app.quit()`.
