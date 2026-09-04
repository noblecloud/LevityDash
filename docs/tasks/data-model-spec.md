# Data model + config spec

**Status:** design, 2026-08-05. Not started. Syntax settled in conversation;
implementation not scoped.

Companion to [data-model-multi-domain.md](data-model-multi-domain.md), which
holds the *research* (openHAB / Home Assistant / Grafana / Prometheus / OTel /
InfluxDB, plus the WeatherFlow, Netatmo, Davis and Ambient Weather APIs). This
doc is the resulting **spec** — what the config and dashboards actually look
like. Where the two disagree, this one is newer.

Breaking changes are in scope, per the maintainer, repeatedly.

Supersedes the naming in earlier drafts: `key:` → `connection:`, `room:` →
`where:`, and `source:` disappears entirely.

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

⚠️ `where` and `provider` are **not** the same axis, and both are needed at
once: *"backyard temperature, according to WeatherFlow."* Collapse them and
the ensemble case (§7) becomes inexpressible.

Each name states the *question*. Earlier drafts used `room:` (too narrow —
backyards, roofs and racks are not rooms) and `source:` (already means three
other things in this codebase).

---

## 4. `key:` → `connection:`

```yaml
- type: realtime.text
  connection:
    sensor.temperature.air: {where: bedroom}
  display:
    font: Roboto Mono
```

**Why the rename.** The runtime already calls this a connection —
`__connectedContainer`, `connectRealtime()`, `startConnecting()`. And it
behaves like one: it connects to whatever is available, **re-negotiates** when
a better source appears (`notPreferredSourceOnLastAttempt`), waits pending
until requirements are met, and fails over. A key is a static address; this is
a live binding. It also makes `•••` legible — *not connected yet* rather than
*broken*.

`source:` as a panel property **disappears**, absorbed as the `provider`
label. `key:` + `source:` were two halves of one question.

### YAML shape

`connection` is a **string** (bare) or a **single-key mapping** (with labels):

```yaml
connection: sensor.temperature.air                        # no labels

connection:
  sensor.temperature.air: {where: bedroom, provider: WeatherFlow}
```

Same scalar-or-mapping pattern `title:` already uses, and `statekit` already
has `unwraps`/`singleVal` for it.

⚠️ **Two keys under `connection:` must be a load-time error** — that's the one
shape that can go wrong silently.

⚠️ **Indentation trap:** `- realtime.text:` followed by a same-indent `key:`
parses as *two sibling keys* with `realtime.text: null`. Valid YAML, silently
wrong. A linter should catch it.

---

## 5. Combining

```yaml
combine: {over: provider, using: mean}              # the 95% case

combine: {over: [where, device], using: mean}       # one function, many dims

combine:                                            # full form
  over: [{device: max}, provider, where]
  using:
    default: mean
    where: min
```

### Order lives in the list, never in a mapping

- **`over:`** — *which* dimensions and **in what order** → a **list**
- **`using:`** — *which function per dimension* → a **mapping** (pure lookup,
  order irrelevant)

This matters because multi-dimension reduction is **not commutative**.
Verified with real numbers:

```
data: (A,x)=0  (A,y)=10  (B,x)=8  (B,y)=0
spec: where→mean, device→max

  max first, then mean  →  9
  mean first, then max  →  5
```

Same spec, same data, different answer. Addressing each function to its
dimension does *not* determine the result — only order does.

Order therefore must live somewhere a serializer cannot scramble.
⚠️ **`yaml.dump()` sorts keys by default**, and `CentralPanel._save` does not
pass `sort_keys=False` — so `{where: mean, device: min}` comes back as
`{device: min, where: mean}` after a save. Putting order in the list sidesteps
this entirely.

**Exception worth documenting:** when every function is the same, order does
*not* matter (for equal group sizes), so `over: [a, b], using: mean` is safe.

⚠️ Still to decide: `over: [where, device]` with **unequal group sizes** —
flat mean of all readings, or mean-of-means? Those differ (33.3 vs 40 in a
2-sensor/1-sensor case) and nothing in the syntax says which. Simplest safe
answer: **one dimension per step**, use several steps for more.

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

```yaml
places:
  home:
    upstairs:
      bedroom:
      office:
    garage:
  outside:
    backyard:
    roof:

devices:
  govee-bedroom:
    plugin: Govee
    id: GVH5102_527D
    where: bedroom

  indoor:                                     # an aggregate IS a device
    temp: {mean: [govee-bedroom.temp, govee-terrarium.temp]}
```

- **`where` is a reference to a place object**, not a string copied onto the
  device. Rename the place, every reading follows. (HA's Area model.)
- **Resolution order**: entity's own `where` if set, else its device's. The
  per-entity override earns its keep — a BLE hub in a closet whose sensors
  live in other rooms.
- **Hierarchy**: asking a parent matches its children. `where: upstairs`
  returns bedroom + office. Arbitrary depth, unlike HA's fixed Floor→Area.
- **`indoor.*` / `environment.*` die here** — they were places all along, and
  now they're places *you define*.

### Aggregates are model-time, not display-time

openHAB's Group Item model, not HA's Area card. HA deliberately does **no**
core aggregation — its Area card medians same-class sensors for glance display
only, so nothing else can reference the result. Conditional panels driven by
aggregate properties need a *referenceable* aggregate.

Members stay separate entities; the aggregate is **additional**, never a merge
that loses the underlying data.

---

## 7. Two combining operations — do not conflate

| | Collapses | Syntax |
|---|---|---|
| **Combine** | a *dimension* of matching series | `{over: provider, using: mean}` |
| **Expression** | named *operands* | `{mean: [bedroom.temp, terrarium.temp]}` |

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
| **Window** | today · yesterday · 7d | 🔴 in the key | ❌ → `period` label |
| **Aggregation** | max · min · sum | 🔴 in the key (`high`, `low`) | ❌ → `combine` |

**Three of five are already modeled correctly.** Notably `request_timeseries`
takes a min/max period *range*, not a fixed interval — so multi-resolution
negotiation (the hard part, equivalent to Grafana's `$__interval`) already
works. Most projects get that wrong.

The flexibility win: today `temperature.high` exists only because someone wrote
that key, and "max over the last 3 hours" is **impossible**. As a label it's
just `{period: 3h}`.

⚠️ **Reported vs computed aggregates.** If a source only hands you a daily
high, you cannot derive an arbitrary window from it. The model must distinguish
"this aggregate was given to me" from "I calculated it," and a panel asking for
an underivable window must fail honestly rather than show nothing. OTel treats
this as first-class ("aggregation temporality").

---

## 9. Known hard parts

| Problem | Notes |
|---|---|
| **Series alignment** | ensembles have different timestamps, resolutions and horizons — needs resampling onto a common grid before averaging. What happens past the shortest horizon needs a stated policy |
| **Stale members** | nobody does this well — openHAB folds a dead sensor's last value in forever. We already track and display value age, so a max-age bound is natural here |
| **Missing members** | HA silently drops them; a 2-sensor average quietly becomes 1 and still looks authoritative. Expose contributing-member count instead |
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

1. **Places + device registry** — no key changes, immediately useful
2. **Aggregates** — the long-wanted feature, unblocked by 1
3. **Key namespace** — the big one. Do it when health/service data actually
   arrives, so the migration serves a real need rather than a predicted one
4. **Conditionals in stacks** — cheap, any time

Steps 1–2 deliver most of the value without touching a single existing key.
Step 3 is the scary one and also the most deferrable.

## 12. Still undecided

1. Shape-discriminator vocabulary — closed set? maps to display types?
2. Flat vs nested semantics for multi-dimension `combine` with unequal groups
3. Labels *as well as* places? HA needed both; location can't express
   "battery-powered" or "sensors I trust"
4. Staging for events/lists/non-numeric — can numeric+enum land first without
   forcing a second migration?
5. `mean` vs `average` naming — accept both, document the plain word
