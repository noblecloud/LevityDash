---
name: levity-dashboard-design
description: Design, lay out, or revise LevityDash `.levity` dashboards — panels, gauges, value/label placement, fonts, gradients, sizing groups. Use this whenever the user asks to build, redesign, rearrange, or critique a dashboard, add or move a value or panel, change how something *looks* ("it looks wonky", "too empty", "make it denser", "that title looks wrong", "can you make it prettier"), or asks why a label/value/gauge is rendering badly. Also use it before editing any `.levity` file or `saves/dashboards/default.levity`, even when the request sounds purely mechanical like "add terrarium temperature" — laying a value out well is a design decision, not a config edit.
---

# Designing LevityDash dashboards

## Read this first: the failure mode this skill exists to prevent

The natural pull when handed a `.levity` file is to treat it as configuration —
find the right key, set the value, confirm it parses, move on. That produces
dashboards that are *correct and ugly*: labels that float between two values so
you can't tell what they belong to, gauges that never move, panels padded with
`•••` because a key had no source.

The author's words for it: *"it seems like you're in programmer mode rather than
designer mode."* And, on an earlier attempt: *"it kinda seems like you just added
the gradients just because I suggested it. It didn't seem like it was actually
intentionally designed."*

So: **decide what the layout is saying before touching a key.** Then verify with
your eyes, not with "the YAML parsed."

**`references/config.md`** is the exhaustive inventory — item types, gauge
options (including partial/corner arcs via `start-angle`/`end-angle`), text and
unit placement, stacks, gradients, sizing groups. Read it when you need an option
name or want to know whether an idea is even expressible. This file is about
judgment.

## The loop

1. **Look at the current dashboard.** Screenshot or render it. You cannot
   redesign what you haven't seen.
2. **Say what you're trying to achieve, and why**, in one or two sentences,
   before editing. If you can't articulate the intent, you're about to decorate.
3. **Build it.**
4. **Render and look again.** Compare against the intent. Most problems are
   obvious in the image and invisible in the YAML.
5. **Iterate on what you see** — not on what you expect the numbers to do.

## Principles

### 1. Proximity decides what a label belongs to

This is the one that goes wrong most often. A label binds to whatever it is
*nearest*. Not what it's above, not what it's semantically paired with in the
file — what it is physically closest to.

A label sitting in the gutter between two rows, roughly equidistant from the
value above and the value below, reads as belonging to **neither**. The viewer
has to stop and work it out, which is exactly the cost a dashboard exists to
remove.

**The rule:** the gap from a label to its own value must be *visibly* smaller
than the gap to the nearest other element — aim for at least 1.5–2×. If they're
close to equal, the binding is ambiguous no matter which side the label is on.

**Which side?** Above is the default, because it matches reading order — you
learn what a thing is, then read it. But that's a weak convention and proximity
beats it every time:

- A value in the **middle or top** of its cell: label above is usually fine,
  because there's dead space above and the value directly below.
- A value at the **bottom** of a row, with another row beneath: label above lands
  in the inter-row gutter and becomes ambiguous. Either put the label **below**
  the value, or widen the inter-row gutter so the label is unmistakably closer to
  its own value.

**How to check:** look at the render and ask *"can I tell what this label names
in under a second?"* If you have to trace, it's wrong. Squinting helps — blur
collapses everything except grouping.

**Alternative to proximity: common region.** A divider, a box, or a background
binds elements regardless of distance. LevityDash stacks can draw dividers
(`dividers: {enabled, opacity, size}`) — that's the tool when spacing alone
can't do it.

### 2. One hero per region

Every panel should have an obvious most-important value, and the rest should
visibly defer to it. If everything is the same size, the eye has nowhere to land
and the panel reads as a wall.

Size, weight, and position all signal importance. Prefer *size* — it survives
being viewed from across a room, which is what this dashboard is for.

### 3. Every mark has to earn its place

A gauge whose needle never visibly moves is decoration. A ring around a value
that's already legible is decoration. Gradients that don't encode anything are
decoration.

Ask of each element: **what does this tell me that the number alone doesn't?**
Good answers: position within a known range (UV 8 of 11 *feels* different from
"8"), rate of change, threshold crossing. Bad answer: "it looks nice."

A dial earns itself when angular position carries meaning — wind speed against a
known scale. It does not earn itself for a value with no meaningful range, or one
already obvious as a number.

### 4. Align things, and keep them from jittering

Numbers that change width make a column dance. `29.85 → 29.9` reflows the cell in
a proportional font. Fixed-width digits (`font: Roboto Mono`) stop that, which is
the *functional* argument for monospace here — it's wider per glyph, so it isn't
about density.

Use `matchingGroup` to keep related values the same size across a panel; a row of
readings at slightly different sizes looks broken even when nothing is wrong.

### 5. Design for the physical display, not the pixel count

A 15" screen at 1920px and an 8" screen at 1920px need different layouts. A larger
physical display is read from further away but resolves *more* items — the win is
**more readings, not bigger ones**.

Size text in `mm`/`cm` where it matters, since those are physical units and survive
a resolution change.

### 6. Never pad with data that doesn't exist

A cell whose key has no source renders `•••` forever. That's worse than an empty
space — it looks broken. Before adding a value, confirm something actually
publishes that key. Density built from placeholders is fake density.

## Verification

Render it and **look at the image**. There is a devtool for this:

```bash
poetry run python src/LevityDash/devtools/render_dashboard.py OUT.png \
    --levity CANDIDATE.levity --seed <config-copy>
```

Omit `--seed` to render the real config (real data, but on macOS the Govee
plugin needs a Bluetooth-capable host — see CLAUDE.md). Add `--plugins` for
live values, `--size WxH` to match the actual window.

It renders the scene straight into a `QImage` via `QGraphicsScene.render()`, so
there is no window and no GL context. Prefer it over `view.grab()`, which
captures the *viewport* and therefore needs the window shown and
`[QtOptions] openGL = False` — otherwise the grab comes back blank white.
⚠️ `QGraphicsEffect`s don't composite identically this way (the moon's glow
renders flat); layout, type, spacing and colour are faithful, effects are not.

Two things that make a render lie:

- **Aspect ratio.** Render at the *real* window size. A layout that fits at
  1920×1080 can overflow at a squarer aspect, because relative heights change.
- **Placeholders.** Without live data every value is `•••`, and a layout judged
  on placeholders will be wrong once real numbers arrive — long values overflow,
  short ones look lost. Prefer a render with data; if you can't get one, say so
  rather than pronouncing on the result.

## Traps

Discovered the hard way; each one cost a full build/render cycle.

- **`shared:` overrides a child's `title: false`.** A group's `shared` block
  applies to every child, so a gauge you told not to have a title gets one anyway
  — and if a sibling also has a title, the cell renders two. Set titles per item
  when any child needs to opt out.
- **Panel sizes sum to ~97%, not 100%.** A stack's `spacing` costs real width on
  top of the declared sizes. Five panels with `spacing: 10px` on 1920px eats ~2%.
  Overflow is silent — the last panel just runs off the edge.
- **A lone glyph in a tall cell balloons.** A single character (`0`, `8`) fits far
  larger than `71°` in the same box, and size groups don't always equalise across
  distance (`Groups.py` clusters by proximity). Give short values neighbours, or
  expect them to tower.
- **`value-label: {position: center}` doesn't centre.** Known `_center_transform`
  gap — the value lands beside the ring, not inside it. Don't fight it with radius
  tweaks; compose explicitly instead (gauge with `value-label: {visible: false}`
  plus a sibling `realtime.text`), which also gives you full control of placement.
- **Units are strings, not booleans.** `unit_symbol: True` renders the literal
  word `True` (`61True`). Omit the key or give it a real string.
- **`title: {position: bottom}` is inert.** `DisplayPosition` has no `Top` or
  `Bottom` member (it has `Above`/`Below`), and `ClosestMatchEnumMeta` silently
  fuzzy-matches `bottom` → `Below` rather than erroring — which the splitter's
  layout then ignores. `Splitters.py` itself compares against
  `DisplayPosition.Top`, which also doesn't exist. **Title side is currently not
  controllable from config**; proximity has to come from geometry.
- **Shrinking a cell's height does not pull its value up to its title.** The
  value centres in whatever space it gets, so a shorter cell just centres it in
  a smaller box — the label→value gap barely moves, and you gain clutter as
  other elements (like the staleness indicator) find room. The lever that
  actually governs this is the title/value **splitter ratio**, not the cell.
- **A `.levity` value can be sized in `%`, `px`, `mm`, or `cm`** — mixing them
  within a group is how you get inconsistent-looking titles. Pick one per concern.

## Working with the author

They know this codebase deeply and will tell you plainly when something looks
wrong — *"a lil messy"*, *"kinda boring"*, *"the titles don't look like they're
for the right value"*. Take that as precise signal, not vague dissatisfaction, and
find the structural cause rather than nudging percentages.

When they suggest a feature ("maybe add gradients", "you can do mini gauges"),
they're offering a *possibility*, not an instruction to apply it everywhere. Use it
where it earns its place and say why.
