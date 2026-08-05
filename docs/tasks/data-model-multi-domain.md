# Data model for a multi-domain dashboard

**Status:** design research, 2026-08-04. Not started.
Supersedes [device-model-redesign.md](device-model-redesign.md), which assumed
a weather-only, device-centric world. That doc's *research* still stands; its
central conclusion — that `Device` is the missing primitive — turns out to be
wrong once the scope widens.

Breaking changes are in scope, per the maintainer, repeatedly.

## Why this exists

The scope changed: LevityDash is becoming a general personal-metrics dashboard
— weather **plus** health metrics, service/infrastructure status, and whatever
comes next — with conditional panels driven by data, and rooms as a
first-class concept.

Three things the maintainer named, which turn out to be one problem:

1. `environment.*` and `indoor.*` "never quite fit and get kinda weird"
2. Rooms, like Home Assistant has
3. Conditional panels based on an aggregate's properties

## What's actually wrong with the key namespace

One key is doing three unrelated jobs:

```
indoor.temperature.temperature#bedroom
└─┬──┘ └────────┬────────────┘ └──┬───┘
where          what            which device
```

**Prometheus names this exactly**, and the second clause is the damning part:

> "Do not put the label names in the metric name, as this introduces
> redundancy and **will cause confusion if the respective labels are
> aggregated away**."
> — [Metric and label naming](https://prometheus.io/docs/practices/naming/)

`indoor.temperature.temperature` and `environment.temperature.temperature` are
*the same measurement* with different location labels. Because location is
baked into the name, they are unrelated keys — so they can never be cleanly
compared or aggregated. **The weirdness and the missing aggregation feature
are the same defect.**

And the doubled leaf (`temperature.temperature`, `humidity.humidity`) is Go's
well-documented **stuttering** anti-pattern (`http.HTTPServer` vs
`http.Server`): a category segment gets a leaf that just restates the
category, because the namespace was busy doing location work and never
introduced a real leaf token.

### The good news

**The schema already gets this right. Only the key is wrong.**

```python
'indoor.temperature.temperature': {
    'type': 'temperature',   # the KIND — HA calls this device_class
    'sourceUnit': 'c',       # unit as metadata, OTel-style
    'title': 'Temperature',  # display name
}
```

Kind, unit, and display name are already separate fields. The key is the only
place where kind, location, and device got mashed into one string.

## The consensus rule

Verified across OpenTelemetry, Prometheus, Home Assistant, HealthKit,
Google Fit and InfluxDB:

> **The name is the fixed *kind* of measurement — stable across every
> instance, regardless of who or where produced it. Anything that varies
> per-instance is a label.**

Units stay out of the name (OTel-style metadata). Prometheus bakes units into
names only because PromQL has no unit type; LevityDash has WeatherUnits, so it
belongs in OTel's camp — no `_celsius` suffixes.

## Correction: the primitive is not `Device`

The previous doc built everything around Device. That breaks immediately
outside weather:

- A **calendar** has no device.
- A **service's** uptime has no device.
- A **heart rate** belongs to a *person*, not a place or a sensor.

Home Assistant's atom is the **entity**; device is *one optional grouping*.
`person.alice`, `zone.home`, `calendar.work`, `sun.sun` have no device at all.
Netdata uses node/instance; Prometheus and Datadog make host just another tag.

**So the primitive is a source/entity**, with device / person / service /
place / account as subtypes. Conveniently this generalises the `source` field
`CategoryItem` already carries rather than inventing a new concept.

## Refinement: keep a prefix, change what it discriminates

"Kill the domain prefix" was too broad. From the survey:

> Every system that unifies successfully does so with a **mandatory
> discriminator baked into the address** that tells consumers what *shape* of
> data lives there — never a truly undifferentiated flat key space.

| | discriminates | verdict |
|---|---|---|
| `environment.` / `indoor.` | **location** | ❌ that's a label |
| `sensor.` / `calendar.` / `service.` / `person.` | **shape** | ✅ structural |

`sensor.temperature` says "expect a number with a unit." `calendar.next` says
"expect events with durations." `service.status` says "expect an enum." The
dashboard already picks displays by shape (`realtime.text` vs `gauge` vs
`graph` vs `clock`) — the namespace just doesn't say so out loud.

Sketch:

```
sensor.temperature   + {room: bedroom, device: govee-bedroom}
sensor.heart_rate    + {person: me, device: watch}
sensor.cpu_usage     + {host: lambda, service: levity-backend}
service.status       + {service: api}
calendar.next        + {account: work}
```

`environment.*` and `indoor.*` both disappear — "indoor" was never a *kind* of
temperature, it was a *place*.

## Rooms — copy Home Assistant's shape exactly

HA's model, verified:

- **Area** is a **separate first-class registry object** with its own id and
  name. Devices (and optionally individual entities) hold a *reference* to it
  — the room is never a string baked into the device. Renaming the area
  updates every pointer at once.
- Resolution order: `entity.area_id` if explicitly set, else `device.area_id`.
  The per-entity override matters in practice — a BLE hub can live in the "IT
  Closet" while its remote sensor entities sit in the rooms they measure.
- **Floors** group areas. Entities can't be assigned to floors directly.
- **Zones** are unrelated — geographic circles for presence, not organisation.
- **Labels** are many-to-many and domain-agnostic ("battery-powered",
  "needs firmware update"), spanning areas and item types. ⚠️ Labels do **not**
  roll up device→entity the way areas do; `label_entities()` returns only
  directly-labelled items.

**Two grouping axes are not redundant** — HA shipped labels *after* areas
precisely because a location hierarchy structurally cannot express
cross-cutting, non-spatial concerns.

### ⚠️ HA deliberately does NOT aggregate in the core model

Two thermometers in one room stay two entities forever. `area_entities()`
returns both, unreduced; the Area *card* medians same-class sensors purely for
glance display (and *sums* cumulative classes like energy).

This is a real fork against openHAB, whose Group Items are first-class
addressable aggregates. Given the maintainer wants `#indoor` addressable *and*
wants conditional panels driven by aggregate properties, **openHAB's model is
the right one here** — but note it stays compatible with HA's principle: the
members remain separate entities, and the aggregate is an *additional* entity,
never a merge that loses the underlying data.

## What will break the current model

Ranked by likelihood, from the multi-domain survey:

1. **Events and states as first-class shapes.** A calendar entry (start+end)
   and a service (up/degraded/down) have no "current value." A container built
   around "one key → one measured value now" has nowhere to put them.
2. **Cardinality.** "Next 5 events", "top 10 processes", "disks in the array"
   are inherently *lists*. Today is strictly one key → one value.
3. **Non-numeric values.** Strings, enums, images, geo-coordinates. A
   `float + unit` value type has to grow a variant, which cascades into every
   consumer that pattern-matches on numeric.

Hierarchical nesting (a host with containers) and person/account identity are
real but only need an *additional addressing axis* — they extend the model
rather than invalidating it.

## Dashboard implications

**"A panel per room" has an established mechanism** — Grafana's *repeat by
variable*: a query variable enumerates the rooms
(`label_values(temperature, room)`), the panel is marked repeat, and Grafana
clones it once per value at render. Add a room, the dashboard file doesn't
change. Nothing else in Grafana generates N panels from one definition.

**Ad hoc filters** are worth stealing: declared once at dashboard level, they
are auto-appended to *every* query on the dashboard with no per-panel wiring —
a dashboard-wide "only show bedroom" knob.

### ⚠️ Conditional panels are two features, not one

Grafana shipped conditional visibility only in **v12, May 2025** — a decade
in. And they had to ship **Auto grid layout** alongside it: a reflow engine
that closes the gap a hidden panel leaves behind.

`.levity` panels are positioned with **absolute geometry**
(`x: 57.9%, y: 49.1%, width: 42.1%`). A conditional panel that hides leaves a
**hole**. So this is:

1. the condition (easy — needs queryable context)
2. **layout that reflows** (the hard part)

Stacks already reflow; absolutely-positioned panels don't. Worth scoping as
two pieces of work rather than one. Note even Grafana's shipped version has
rough edges — show/hide rules on *repeated* panels apply to the whole set
rather than per-instance.

### The road not taken

Grafana deliberately does **not** unify at the data-model level at all — each
panel is scoped to one data source with that source's own query language, and
results are normalised into a common "data frame" only at the *visualisation*
boundary. That is a legitimate alternative architecture: don't unify, normalise
late. It's probably wrong for LevityDash (a single coherent namespace is much
of the app's value) but should be rejected deliberately, not by omission.

## Open questions

1. **Shape discriminator vocabulary.** What's the closed set — `sensor`,
   `state`, `event`, `text`? Does it map 1:1 to display types, or stay
   independent?
2. **Aggregate placement.** Model-time (openHAB Group Item, addressable) vs.
   presentation-time (HA Area card). Leaning model-time, but presentation-time
   aggregation for "glance" views may *also* be wanted.
3. **Does the room live on the entity, the device, or both?** HA does both with
   an override, and the override earns its keep. Copy it or simplify?
4. **Labels as well as rooms?** HA needed both. Adding both now is more
   surface; adding rooms only risks rediscovering why labels exist.
5. **How far to take value types?** Events and lists are the expensive ones. Is
   there a staging where numeric+enum land first and events/lists come later
   without a second migration?
6. **Migration.** Every existing `.levity` key changes. Blast radius is
   genuinely small (shipped templates carry no device-scoped keys; only
   `docs/design-references/temperature-column.levity` and the maintainer's live
   `default.levity`) — but this is a much wider change than the device work,
   since *every* key gains a shape prefix and loses its location prefix.

## Sources

Grafana: [variables](https://grafana.com/docs/grafana/latest/visualizations/dashboards/variables/) ·
[dynamic dashboards](https://grafana.com/whats-new/2025-04-10-dynamic-dashboards/) ·
[timeseries dimensions](https://grafana.com/docs/grafana/latest/fundamentals/timeseries-dimensions/) ·
[transformations](https://grafana.com/docs/grafana/latest/visualizations/panels-visualizations/query-transform-data/transform-data/)
Naming: [OTel naming](https://opentelemetry.io/docs/specs/semconv/general/naming/) ·
[Prometheus naming](https://prometheus.io/docs/practices/naming/) ·
[HealthKit](https://developer.apple.com/documentation/healthkit/hkquantitytypeidentifier) ·
[InfluxDB line protocol](https://docs.influxdata.com/influxdb/v2/reference/syntax/line-protocol/)
Home Assistant: [areas](https://www.home-assistant.io/docs/organizing/areas/) ·
[floors](https://www.home-assistant.io/docs/organizing/floors/) ·
[labels](https://www.home-assistant.io/docs/organizing/labels/) ·
[area card](https://www.home-assistant.io/dashboards/area/) ·
[entity naming](https://developers.home-assistant.io/blog/2022/07/10/entity_naming/)
Multi-domain: [Netdata NIDL](https://learn.netdata.cloud/docs/dashboards-and-charts/nidl-framework) ·
[HA entities & domains](https://www.home-assistant.io/docs/configuration/entities_domains/)
