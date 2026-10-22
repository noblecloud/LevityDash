# Data model + config spec

**Status:** design, 2026-08-05; decisions of 2026-10-15 folded in. The
first step is shipped: a `realtime` item reads through a connection object
([#106](https://github.com/noblecloud/LevityDash/pull/106)). The rest is not
started.

Companion to [data-model-multi-domain.md](data-model-multi-domain.md), which
holds the *research* (openHAB / Home Assistant / Grafana / Prometheus / OTel /
InfluxDB, plus the WeatherFlow, Netatmo, Davis and Ambient Weather APIs). This
doc is the resulting **spec** — what the config and dashboards actually look
like. Where the two disagree, this one is newer.

Breaking changes are in scope, per the maintainer, repeatedly.

Supersedes the naming in earlier drafts: `key:` → `connection:`, `room:` →
`where:`, and `source:` disappears entirely.

## Decided on 2026-10-15

These settle questions that were open in the first draft. The sections below
are written to match.

1. **First cut:** `where` (a label on a reading, plus dotted places) and
   named aggregates. No key renames in this cut.
2. **`key:` stays an item property for now.** The rename to `connection:`
   waits for the key-namespace step. The connection is an object that holds a
   `key` (section 4), and `key:` on an item is its short form.
3. **`#bedroom` is kept** as the short form of `where: bedroom`.
4. **Aggregates are built on expressions**, the engine that already makes
   computed keys. A `combine:` syntax comes later, and only for the
   multi-provider ensemble (section 7).
5. **Several dimensions can be combined at once.** Order and flat steps are
   written in `over:` (section 5).
6. **Old mapping form dropped.** `connection: {sensor.temperature.air: {where: bedroom}}`
   is not valid. A connection is `{key: …, where: …}`.
7. **Places are dotted paths** (`upstairs.bedroom`), not a separate registry
   (section 6).
8. **Stale readings:** an aggregate ignores a reading older than one hour. A
   single aggregate can change that bound.
9. **Missing readings:** an aggregate also publishes how many readings it
   used, so a panel can show "1 of 2".

Decided on 2026-10-16:

10. **`avg(a, b, ...)`** is added to the expression language: the mean of two
    or more current values.
11. **`mean` is accepted as another name for `avg`.** Docs use the plain word.

Built in step 2 (aggregates), from Neal's answers of 2026-10-16:

- A place selects with `where=` and with an `@place` suffix on a key. Both mean the
  same. The suffix has no clash inside expressions, which read keys with their own
  pattern. Elsewhere `@` is the schema wildcard and the size-group `key@name`, which
  are separate places in the file.
- `count(key, where=place)` exists, and every expression publishes its reading count
  at its own key with `.count` added.
- Shared variables live in `vars.yaml` beside `config.ini`. A dashboard's own `vars:`
  wins on a name clash.
12. **Named aggregates can be written in two places:** a global vars file that
    every dashboard shares, and the `vars:` of a single dashboard. A dashboard
    entry wins over the global one of the same name.
13. **Labels as well as places.** A reading can carry free-form labels
    (`battery`, `trusted`) beside its `where`.
14. **`.high` and `.low` stay real keys.** Some sources provide them, so they
    are not always calculated. A custom high or low, built from several
    sources, is a computed aggregate (section 8).

---

## 1. Keys say *what*. Labels say *which*.

```yaml
sensor.temperature.air  + {where: bedroom, device: govee-1, provider: Govee}
```

Three things that must **not** be in a key:

| Anti-pattern | Example today | Why |
|---|---|---|
| **Place** in the name | `indoor.*` / `environment.*` | it's a label |
| **Stutter** | `temperature.temperature` | Go's `http.HTTPServer` smell |
| **Time** in the name | `yesterday.*`, `.high`, `.daily` | it's a label |

The governing rule, consistent across OTel / Prometheus / HA / HealthKit /
InfluxDB:

> **The name is the fixed *kind* of measurement — stable across every
> instance. Anything that varies per-instance is a label.**

Prometheus states the damage explicitly: label values in a metric name
*"will cause confusion if the respective labels are aggregated away."* That is
precisely why indoor and outdoor temperature cannot be compared or averaged
today — they are different keys for the same measurement.

Units stay **out** of names (OTel-style metadata). Prometheus bakes units in
only because PromQL has no unit type; WeatherUnits means we don't need that.

### The schema is already right

```python
'indoor.temperature.temperature': {
    'type': 'temperature',   # the KIND (HA calls this device_class)
    'sourceUnit': 'c',       # unit as metadata
    'title': 'Temperature',  # display name
}
```

Kind, unit and title are already separate fields. **Only the key conflates
them.** This migration mostly *deletes* duplication rather than adding a layer.

---

## 2. Keep a prefix — change what it discriminates

| Prefix | Discriminates | |
|---|---|---|
| `environment.` `indoor.` | location | ❌ |
| `sensor.` `calendar.` `service.` `person.` | **shape** | ✅ |

Every system that unifies heterogeneous data successfully keeps a **mandatory
shape discriminator** in the address — never a flat undifferentiated key space.
`sensor.` promises a number with a unit; `calendar.` promises events with
durations; `service.` promises an enum.

The dashboard already picks displays by shape (`realtime.text` vs `gauge` vs
`graph` vs `clock`) — the namespace just never said so.

---

## 3. The dimensions

| Label | Answers |
|---|---|
| `where` | which **place** — hierarchical |
| `device` | which **hardware** |
| `provider` | which **plugin** |
| `period` | which **time window** |
| `resolution` | how **fine-grained** |

`period` is reserved and not part of the first cut (section 12, item 3).

⚠️ `where` and `provider` are **not** the same axis, and both are needed at
once: *"backyard temperature, according to WeatherFlow."* Collapse them and
the ensemble case (§7) becomes inexpressible.

Each name states the *question*. Earlier drafts used `room:` (too narrow —
backyards, roofs and racks are not rooms) and `source:` (already means three
other things in this codebase).

---

## 4. The connection

```yaml
- type: realtime.text
  connection:
    key: sensor.temperature.air
    where: bedroom
    provider: WeatherFlow
  display:
    font: Roboto Mono
```

A connection is an object. It always has a `key`. The other properties are
labels (section 3). It is also what the item reads its data through.

**Why the name.** The runtime already calls this a connection:
`__connectedContainer`, `connectRealtime()`, `startConnecting()`. It behaves
like one. It connects to whatever is available, re-negotiates when a better
source appears (`notPreferredSourceOnLastAttempt`), waits pending until its
requirements are met, and fails over. A key is a static address. A connection
is a live binding. It also makes `•••` readable: *not connected yet*, not
*broken*.

`source:` on an item disappears into the `provider` label. `key:` and `source:`
were two halves of one question.

### Short forms

An object with a `key` property can be written shorter. This is the same
mechanism that Stateful already uses for `title`, `shadow` and the others:
`unwrap` on the item's property, and `singleVal` on the connection's `key`.

```yaml
key: sensor.temperature.air                 # key: on the item is the short form
connection: sensor.temperature.air          # a bare connection is a key
connection: {key: sensor.temperature.air}   # the full form
```

All three load as the same connection. A connection that holds only a key
saves back as `key:` on the item. Today's dashboards keep working without an
edit.

**Shipped (#106).** This works now on `realtime` items, with `key` and `source`
only. Save writes the flat form (`key:` and `source:` side by side on the item),
which is what `unwrap` already does. `source` becomes `provider` and `where`
and `device` arrive with the rename step. Graph, polar and clock items still
take `key:` only.

**Removed.** The earlier draft wrote a connection as a one-key mapping
(`connection: {sensor.temperature.air: {where: bedroom}}`). That is not
valid. It needed a "two keys is an error" rule and an indentation trap
(`- realtime.text:` followed by a same-indent `key:` parses as two sibling
keys). The object form has neither problem.

---

## 5. Combining

```yaml
combine: {over: provider, using: mean}              # the 95% case

combine: {over: [where, device], using: mean}       # two steps, in order

combine: {over: [[where, device]], using: mean}     # one flat step

combine:                                            # full form
  over: [{device: max}, provider, where]
  using:
    default: mean
    where: min
```

### Order lives in the list, never in a mapping

- **`over:`** says which dimensions and in what order. It is a **list**.
- **`using:`** says which function each dimension gets. It is a **mapping**: a
  plain lookup where order does not matter.

Reducing over more than one dimension is not commutative. Real numbers:

```
data: (A,x)=0  (A,y)=10  (B,x)=8  (B,y)=0
spec: where→mean, device→max

  max first, then mean  →  9
  mean first, then max  →  5
```

Same spec, same data, different answer. Naming a function for each dimension
does not decide the result. Only the order does.

So the order must live where a serializer cannot scramble it. `yaml.dump()`
sorts keys by default, and `CentralPanel._save` does not pass
`sort_keys=False`, so `{where: mean, device: min}` comes back as
`{device: min, where: mean}` after a save. A list keeps its order.

**Steps and flat steps.** Each item of `over:` is one step. A step that is a
single dimension reduces that dimension, on the result of the step before it.
That is a mean of means when the function is `mean`. A step that is itself a
list reduces all of its dimensions in one go, over every reading together. That
is the flat mean. Both are written without extra words, and the simple case
(`over: provider`) stays short.

```
2 sensors in the bedroom (20, 22) and 1 in the office (30)

over: [device, where]     → mean per where first (21, 30), then mean of those → 25.5
over: [[device, where]]   → one mean of all three readings                    → 24
```

When every function is the same and every group has the same size, order
does not matter, so `over: [a, b], using: mean` is then safe.

### Precedence cascade

| Priority | Where | Example |
|---|---|---|
| 1 (most specific) | inline in `over:` | `{device: max}` |
| 2 | named in `using:` | `where: min` |
| 3 (fallback) | `default:` in `using:` | `default: mean` |

Same defaults-then-override shape as `.levity`'s existing `shared:` blocks.

⚠️ **`*` does not parse as a YAML key** — it's the alias indicator
(`ScannerError: while scanning an alias`). Use `default:`. `"*"` works quoted
but quoting-to-escape is a papercut.

### Validation

`over:` and `using:` are deliberately redundant — that redundancy is a
checksum:

- `using:` names a dimension not in `over:` → error (catches typos)
- `over:` lists a dimension with no function and no `default:` → error

---

## 6. Places, devices, aggregates

`where` is a dotted path. There is no separate list of places to declare.

```ini
[device:govee-bedroom]
plugin = Govee
id = GVH5102_527D
where = home.upstairs.bedroom
```

- **Asking for a parent matches its children.** `where: home.upstairs` returns
  the bedroom and the office. The depth is not limited, unlike Home Assistant's
  fixed Floor→Area.
- **A place exists when something uses it.** Rename a place by editing the path
  where it is used. This is the trade for having no registry. Home Assistant's
  Area registry follows a rename everywhere. A dotted path does not, and that is
  accepted for the cut: one fewer thing to configure, and the hierarchy is free.
- **Labels sit beside places.** A place answers "where". A label answers
  everything else: `battery`, `trusted`, `outdoor-rated`. Labels are free-form
  text on a device or an entity, and an aggregate can select by label the same
  way it selects by place. Home Assistant needed both for the same reason:
  a location cannot say "battery-powered".
- **`#bedroom` is the short form of `where: bedroom`.** It is kept.
- **`indoor.*` and `environment.*` die here.** They were places all along, and
  now they are places you write.

```yaml
devices:
  govee-bedroom:
    plugin: Govee
    id: GVH5102_527D
    where: home.upstairs.bedroom
```

- **Resolution order**: entity's own `where` if set, else its device's. The
  per-entity override earns its keep — a BLE hub in a closet whose sensors
  live in other rooms.

### Aggregates are model-time, not display-time

openHAB's Group Item model, not HA's Area card. HA deliberately does no core
aggregation. Its Area card medians same-class sensors for glance display only,
so nothing else can reference the result. Conditional panels driven by
aggregate properties need a *referenceable* aggregate.

Members stay separate entities. The aggregate is additional. It never merges
and loses the underlying data.

**An aggregate is a named expression.** LevityDash already has the engine:
`lib/plugins/computed.py` publishes an expression as a computed key
(`computed.x3f9a0c21b7de`) with the source `Computed`. It recomputes when an
input updates, runs in the backend in remote mode, and display code subscribes
to the key like any other. An aggregate is that, with a readable name instead
of a hash and with the members listed by `where`.

```yaml
vars:
  indoor: avg(indoor.temperature.temperature#bedroom, indoor.temperature.temperature#terrarium)
```

Write it in the global vars file to share it across dashboards, or in a
dashboard's own `vars:` to keep it local. If both define the same name, the
dashboard wins.

What is missing from the expression language today:

- `avg(a, b, ...)`, also spelled `mean(a, b, ...)`: the mean of two or more
  current values. `min` and `max` already take a list. `avg` takes only a
  window (`avg(key, 3h)`), so a second argument that is a key, not a window,
  has to mean the list form.
- Members chosen by label: `avg(sensor.temperature.air where indoor)` instead
  of listing every member by hand.
- A name that is stable and readable in the dispatcher, so another panel can
  refer to `indoor.temperature`.

Per-reading age and the member count (section 9) are published by the
aggregate beside its value.

## 7. Two combining operations — do not conflate

| | Collapses | Syntax |
|---|---|---|
| **Combine** | a *dimension* of matching series | `{over: provider, using: mean}` |
| **Expression** | named *operands* | `avg(bedroom.temp, terrarium.temp)` |

Aggregates over operands use expressions (decision 4). `combine:` is kept for
the ensemble across providers, where the members are not listed because the
dimension names them.

Prometheus splits these the same way (`avg by (x)` vs arithmetic between
series).

### And three situations, not two

| | Example | Combine? |
|---|---|---|
| **Duplicate** | Tempest via cloud *and* UDP | ❌ pick one — same sensor |
| **Ensemble** | OpenMeteo + PirateWeather + WeatherFlow | ✅ average — independent estimates |
| **Summary** | bedroom + terrarium → "indoor" | ✅ average — different quantities |

An earlier draft said "sources reconcile, devices aggregate." That's wrong —
it collapses *ensemble* into *duplicate*. The real test is **whether the inputs
are independent estimates of the same quantity.**

```yaml
connection:
  sensor.temperature.air:
    forecast: true
    provider: [OpenMeteo, PirateWeather, WeatherFlow]
    combine: {over: provider, using: mean}
```

🎁 **Free bonus:** an ensemble also yields its *spread*. `using: [mean, min,
max]` gives a confidence band — wide where models disagree. Real information
that is currently invisible, at no extra computation.

---

## 8. Time is five things, not one

| Concept | Example | Where it lives | |
|---|---|---|---|
| **Tense** | observed vs forecast | `isRealtime`/`isForecast`/`isDaily` flags | ✅ already right |
| **Resolution** | 1min · 1h · 1d | `request_timeseries(key, min_period, max_period)` | ✅ already right |
| **Point time** | when this reading happened | on the value | ✅ already right |
| **Window** | today · yesterday · 7d | in the key when a source provides it | ✅ keep reported keys; arbitrary windows are computed |
| **Aggregation** | max · min · sum | in the key (`high`, `low`) when a source provides it | ✅ keep reported keys; custom ones are computed |

**Three of five are already modeled correctly.** Notably `request_timeseries`
takes a min/max period *range*, not a fixed interval — so multi-resolution
negotiation (the hard part, equivalent to Grafana's `$__interval`) already
works. Most projects get that wrong.

**`.high` and `.low` are real keys.** Forecasts often provide them, so they are
not always calculated, and they stay as keys. They are not replaced by a
`period` label.

Two kinds of aggregate exist side by side:

- **Reported:** the source gave it. `temperature.high` from a forecast is a
  normal key with a normal source.
- **Computed:** LevityDash calculated it, from readings or from other keys.
  This is where a custom high or low lives. It can combine sources, for
  example the highest of what two forecasts predict:

```yaml
vars:
  high: max(openmeteo.temperature.high, pirateweather.temperature.high)
```

Such a computed high is published as a key under the source `Computed`, so a
panel uses it like any other.

"Max over the last 3 hours" is today impossible. The expression language
already has `max(key, 3h)`, so it is a computed aggregate, not a new key.

⚠️ If a source only hands you a daily high, you cannot derive an arbitrary
window from it. A panel asking for a window that nothing can supply must fail
honestly rather than show nothing. OTel treats this as first-class
("aggregation temporality").

---

## 9. Known hard parts

| Problem | Notes |
|---|---|
| **Series alignment** | ensembles have different timestamps, resolutions and horizons — needs resampling onto a common grid before averaging. What happens past the shortest horizon needs a stated policy |
| **Stale members** | nobody does this well: openHAB folds a dead sensor's last value in forever. **Decided:** an aggregate ignores a reading older than one hour, and one aggregate can set another bound. LevityDash already tracks value age (`plugins/freshness.py`), so the age is known |
| **Missing members** | HA silently drops them, so a 2-sensor average quietly becomes 1 and still looks authoritative. **Decided:** an aggregate publishes the count of readings it used beside its value ("1 of 2") |
| **Units** | HA's `min_max` refuses mismatched units; openHAB's `SUM` drops the UoM (open bug). WeatherUnits lets us just convert first — a genuine differentiator |
| **Conditional panels** | **two** features: the condition (easy) and **layout reflow** (hard). Grafana needed a whole new grid engine. `.levity` uses absolute geometry, so a hidden panel leaves a hole — but **stacks already reflow**, so start there |
| **Events / lists / non-numeric** | calendars, "top 10 processes", strings, geo — all break a `float + unit` container. The top three things that will break the current model |
| **Save-order safety** | `sort_keys=False` + a round-trip test, before any order becomes load-bearing. Task #20 (save/load corrupts structure) is open and should land first |

## 10. Already right — don't rebuild

- **Tense + resolution + point time** (§8)
- **Schema separation** — `type` / `sourceUnit` / `title` (§1)
- **Formula sandbox** — `parseMathString` + `getBadActors`
  ([Govee.py:30-63](../../src/LevityDash/lib/plugins/builtin/Govee.py)) already
  evaluates user math expressions with a blocklist. Reuse it for "unsafe mode"
  rather than writing a second one with different holes. Read its PEP 667
  comment first.
- **`SharedScanner` / `LifecyclePlugin` / model presets** on
  `feat/govee-multi-device-rewrite` — survive this design unchanged.
  `__instances__` does not: it encodes device≡plugin-instance, which the
  multi-provider requirement contradicts.

## 11. Suggested order

0. **Connection object.** Shipped in #106 for `realtime` items: `key` and
   `source`, with `connection:` and `key:` both read.
1. **`where` and devices.** Dotted places, `#identity` kept as the short form,
   a device registry. No key changes. This is what Govee `where` waits on.
2. **Aggregates.** Named expressions, with `avg(a, b, ...)`, members chosen by
   `where`, the one-hour bound and the member count. The long-wanted feature,
   unblocked by 1.
3. **Key namespace.** The big one. Do it when health or service data actually
   arrives, so the migration serves a real need and not a predicted one. The
   `key:` to `connection:` rename and `source` to `provider` go here.
4. **Conditionals in stacks.** Cheap, any time.

Steps 1-2 deliver most of the value without touching a single existing key.
Step 3 is the scary one and also the most deferrable.

## 12. Still undecided

1. Shape-discriminator vocabulary: a closed set? Does it map to display types?
2. Staging for events, lists and non-numeric values: can numeric and enum land
   first without forcing a second migration?
3. A `period` label for windows that a source does not provide. The
   expression language already covers `max(key, 3h)`, so this may not be
   needed. Decide when a panel needs a window the expressions cannot write.

Settled and removed from this list: flat versus nested semantics for several
dimensions (section 5) and the shape of the connection (section 4), on
2026-10-15; labels beside places, `avg` versus `mean`, the fate of `.high` and
`.low`, and where aggregates are written, on 2026-10-16.
