# Device model redesign — devices as first-class, not decorated keys

**Status:** design proposal, 2026-08-04. Not started. Supersedes the
architecture half of [govee-multi-device-rewrite.md](govee-multi-device-rewrite.md)
— the Home Assistant research there still stands, the conclusion does not.

Breaking changes are in scope; the maintainer has said so explicitly, twice,
on the condition that the payout justifies them.

## The problem in one line

There is nowhere in LevityDash to say *"this reading came from that physical
thing"*, so it gets smeared into whichever neighbouring concept is closest —
either the plugin or the key — and both are load-bearing workarounds now.

```
Plugin ──────────────> keys        # today: two layers
```

Everyone else has three. The missing middle is a **Device**.

## The two current mechanisms, and why neither is right

| | `identity` (Govee) | `@var` path substitution (WeatherFlow) |
|---|---|---|
| Form | `indoor.temperature.temperature#bedroom` | `device.@deviceSerial.battery` |
| Device lives in | a string suffix on the key | a segment of the key path |
| Base key survives? | yes — `…temperature` still exists | **no** — there is no `device.battery` |
| Addressed by | human alias | hardware serial |

**Identity's flaw** is that it is a single opaque string, so it cannot carry a
second dimension. That limit is already visible on the roadmap: OpenMeteo soil
readings come in depth bands (10cm/40cm/100cm), and the Govee model table
includes multi-*probe* thermometers (H5181-H5198). `#bedroom` has no room for
`{depth: 10cm}` or `{probe: 2}` without stringly-typed cramming.

**`@var`'s flaw is worse, and it is not theoretical.** Two separate incidents
are documented in the tree:

1. [Govee.py:215-219](../../src/LevityDash/lib/plugins/builtin/Govee.py) — the
   `indoor.@deviceName.battery` form resolved the var from *static config*, so
   both devices substituted the same name and a terrarium reading published as
   `indoor.GVH5102_6736.battery#terrarium`. Abandoned for identity because of it.
2. [schema/__init__.py:313-319](../../src/LevityDash/lib/plugins/schema/__init__.py) —
   a **batch-carryover** bug diagnosed 2026-07-27. `sourceData`/`metaData` ride
   on the datagram and can still hold the *previous* batch's value, so
   consulting them first gave every reading the previous device's identity.
   The comment is worth reading in full; its last line —
   *"with two sensors alternating that is a consistent one-off swap, which
   looks exactly like mislabelled config rather than a staleness bug"* —
   is exactly the failure mode that cost hours of debugging in this project
   already.

WeatherFlow's `@deviceSerial` does resolve per-message from the API payload
(traced: `LevityDatagram.parseData` → `sourceData['@deviceSerial']` →
`replaceKeyVars`), so it does **not** have Govee's static-config bug. But it
sits on the same carryover-prone machinery, and it forces dashboards to
hardcode a serial number.

## What every comparable system does

| System | Layers | Device layer | Keyed by |
|---|---|---|---|
| openHAB | Bridge → Thing → Channel → Item | **Thing** (Bridge = a Thing you add to reach other Things) | thing UID |
| Home Assistant | Integration → Config Entry → **Device** → Entity | device registry | `connections` (MAC) + `identifiers` (serial) |
| Prometheus | metric + labels | — | dimensions in labels, never in the name |
| OpenTelemetry | Resource → scope → measurement | **Resource** = the entity producing telemetry | resource attributes |

And every weather API LevityDash might consume already models it:

| API | Hierarchy | Stable ID | Per-device metadata |
|---|---|---|---|
| WeatherFlow Tempest | station → `devices[]` | `device_id`, `serial_number` | `device_type` (AR/SK/ST/HB), `device_meta` (AGL, indoor/outdoor, name), firmware/hardware rev |
| Netatmo | station → `modules[]` | `_id` (MAC) | `module_name`, `data_type[]`, `battery_percent`, `rf_status`, `reachable`, `last_seen` |
| Davis WeatherLink v2 | station → `sensors[]` | `lsid` | `sensor_type` → Sensor Catalog of field/unit defs |
| Ambient Weather | account → `devices[]` | `macAddress` | `info.name`, `location`, `coords`, `elevation` |

**So this is not "add an abstraction." The sources hand us `station →
devices[] with serial_number and device_meta`, and the plugin layer flattens
it into `device.@deviceSerial.battery` strings.** We are discarding structure
at the boundary and reconstructing it badly downstream.

Two patterns worth stealing outright: Netatmo's `data_type[]` (a device
declaring which measurements it provides — openHAB Channels by another name),
and Davis's **Sensor Catalog** (device-type → field/unit definitions), which is
structurally identical to the Govee model-preset table already built on
`feat/govee-multi-device-rewrite`.

## The requirement that settles it: a device can span plugins

A device must be able to have **multiple plugin sources**. This kills
device-as-plugin-instance outright — under that model, one physical thing
reachable two ways is two unrelated devices.

This is not hypothetical here. WeatherFlow's `start()` already branches on
`socketType: web|udp` — one physical Tempest reachable over cloud websocket
*or* local UDP broadcast, currently handled by an internal `if` because there
is nowhere to say "same device, different transport."

Home Assistant solves precisely this: devices are matched across integrations
by `connections` (MAC) and `identifiers` (serial), so two integrations
reporting the same MAC resolve to **one** device with two providers.

The axes are therefore orthogonal and both necessary:

```
Device  = which physical thing   (stable, cross-plugin, keyed by MAC/serial)
Source  = which plugin told me   (substitutable, reconciled by MultiSourceContainer)
Key     = what was measured      (plain, undecorated)
```

`indoor.temperature.temperature` + `{device: tempest-roof}` arriving from
WeatherFlow-cloud *or* WeatherFlow-UDP is exactly the job
`MultiSourceContainer` already does. Under device≡instance it is impossible.

## Proposed model

```
Plugin   (connection/protocol: BLE scanner, WF account, OpenMeteo API)
   │ provides ▼
Device   (registry entry: stable id, alias, config, metadata, optional lifecycle)
   │ produces ▼
keys     (plain) + dimensions {device: …, depth: …, probe: …}
```

- **Device registry**, keyed by a stable hardware id, matched across plugins.
  ⚠️ [Govee.py:125-140](../../src/LevityDash/lib/plugins/builtin/Govee.py)
  already documents the wrinkle: **on macOS a BLE address is a per-machine
  generated UUID, not a hardware MAC**, so it is not portable as a registry
  key. Use HA's split — `connections` (MAC, when genuinely stable) vs
  `identifiers` (plugin-scoped, e.g. advertised name) — with the user's alias
  as display name only.
- **Dimensions replace the single identity string.** `#alias` stays as
  *sugar* for the common single-device case, which is the maintainer's own
  earlier instinct ("`#` reserved for named devices") now with a general model
  underneath.
- **Device metadata stops being fake measurements.** Battery, RSSI, firmware,
  uptime, last-seen are device properties — as they are in every upstream API
  — not `device.@deviceSerial.battery` weather readings.
- **Lifecycle becomes a device property**, not a different architecture.
  "Can I stop this?" is answered per device; independently-startable BLE
  hardware says yes, a sensor on a shared socket says no.

In `.levity`, addressing gets *more* readable:

```yaml
- key: indoor.temperature.temperature
  device: bedroom            # or `#bedroom` shorthand
```

## Specified vs aggregate devices

A device is either **specified** (a real thing, readings arrive from it) or
**aggregate** (readings are *computed* from member devices). Home Assistant
frames this exactly right: the distinction is about **provenance, not
capability** — a derived entity is still first-class, same state machine, same
surface. openHAB doesn't formalize it at all; a Group Item is simply another
Item.

**So an aggregate device IS a device** — same registry, same addressing, same
wire encoding. `#indoor` is indistinguishable from `#bedroom` to the
dispatcher, the dashboard, gauges and graphs. That is the entire payoff: no
aggregate-specific code anywhere downstream.

```ini
[device:indoor]
aggregate = mean
members = bedroom, terrarium
```

**This is also what proves device and source must stay separate axes.** Two
superficially similar situations demand opposite handling:

- `bedroom` + `terrarium` → **aggregate** (mean). Two real devices, both wanted.
- `bedroom`-via-cloud + `bedroom`-via-UDP → **reconcile** (pick one). One
  device, two transports; averaging would average a value with itself.

Collapse device into source — which is precisely what device≡plugin-instance
does — and these become indistinguishable, so the system silently averages
duplicate readings of one sensor. That is a correctness bug, not a preference.

It also keeps the bare key honest: bare stays "pick one" (today's
`defaultContainer` behaviour, predictable), and averaging is explicit opt-in
via a named aggregate, rather than the bare key silently changing meaning once
a second sensor appears.

**Prior art on functions:** openHAB's Group Items support `SUM`, `AVG`,
`MEDIAN`, `MIN`, `MAX` for numbers and `EARLIEST`/`LATEST` for timestamps,
with groups nesting and an item allowed in several groups at once. HA's
`group` offers `min`/`max`/`mean`/`median`/`last`/`first_available`/`range`/
`sum`/`product`/`stdev`. Both **pre-declare** membership; Prometheus is the
road not taken (`avg by (room) (…)` at query time — trivially ad-hoc, but no
stable addressable entity to hang a dashboard panel on). For a dashboard,
pre-declared is right.

### Three policies to decide explicitly — where the incumbents are weak

Worth doing better than the references here, because LevityDash already has
the infrastructure that HA and openHAB lack:

1. **Units — convert before combining.** HA's `min_max` *refuses*, going
   `unknown` unless every member shares a unit; openHAB's `SUM` has an open
   bug ([openhab-core#2449](https://github.com/openhab/openhab-core/issues/2449))
   silently dropping the unit-of-measure. Neither converts automatically.
   LevityDash has WeatherUnits and can simply convert to a common unit first —
   a genuine differentiator, not a nice-to-have.
2. **Staleness — bound it.** *None* of these systems timestamp-align members;
   the aggregate is computed from whatever each member's current state is,
   however old. The openHAB community reports the obvious consequence: if a
   sensor gets stuck, the group value keeps including its last received value
   indefinitely. LevityDash already tracks and *displays* value age (the
   "16 mins ago" annotations), so a max-age bound on member contribution is
   natural here in a way it isn't for the incumbents.
3. **Missing members — don't silently degrade.** HA skips unavailable members
   and recomputes from the rest, only going unavailable when *all* are down —
   so a two-sensor average silently becomes a one-sensor reading that still
   looks completely fine. Recommend instead that an aggregate expose its
   contributing-member count so the UI can show a degraded state, rather than
   presenting a quietly different number as if nothing changed.

**Possible third category:** *synthetic* devices — OpenMeteo is neither
hardware nor an aggregate of local sensors, it's a model for a location. HA
would treat this as a virtual entity (provenance differs, capability doesn't).
Relates to open question 3 below.

## Blast radius — smaller than expected

Surveyed 2026-08-04. The good news is that **device addressing has barely
escaped into user-facing files**:

- **Shipped templates: zero exposure.** No `#identity` keys and no
  `@deviceSerial` keys in any of the four templates under
  `resources/example-config/templates/dashboards/`. They carry only `source:`
  plugin pins (`WeatherFlow.levity` L198/234/241/249/373/379,
  `WeatherFlow-Govee.levity` L293/302/309/317/440/446, `OpenMeteo.levity`
  L349/355).
- **Design references: 4 lines**, all in
  `docs/design-references/temperature-column.levity` (L48, L50, L93, L95).
- **The maintainer's live `default.levity`** — uses `#bedroom`/`#terrarium`.
- **UI: nothing to migrate, because nothing displays a device today.** Every
  user-visible "source" string resolves to `Plugin.name` —
  `Realtime.py:558` (tooltip), `app.py:433` (Plugins menu), `app.py:687`/`713`
  (insert menu + drag tooltip). Per-device display is greenfield, and this is
  also the root of the open "Govee labels show plugin name" bug.

Core surface that does need work:

- **`CategoryItem`** — identity participates in `__eq__` (`:751`), `__hash__`
  (`:671`), `__str__` (`:678`), and **the `__existing__` interning key**
  (`:554`, verified). Note `__repr__` (`:683-687`) omits identity entirely —
  a pre-existing inconsistency to resolve rather than preserve.
- **Schema** — identity is correctly stripped before lookups in `getExact`
  (`:804-805`) and `getUnitMetaData` (`:912-913`); CLAUDE.md's claim verified.
- **Dispatcher** — `MultiSourceContainer` is keyed by `plugin.name` strings
  (`addValue` `:364`, `defaultContainer` `:302/306/309`), with one
  inconsistency where `checkAwaiting` (`:347`) keys by the `Plugin` object and
  gets away with it via duck-typed `__getitem__`.
- **Wire** — keys are encoded with `str(key)` (`backend.py:122`) and reparsed
  with `CategoryItem(key_str)` (`backend.py:213`, `frontend.py:65`). Identity
  round-trips; **`source` does not** (`__str__` emits a `source:` prefix the
  constructor never parses back, folding it in as a leading path atom). Any
  device-in-key scheme must not repeat that mistake — dimensions should be a
  structured wire field, not string-encoded.
- **WeatherFlow** — 12 `@deviceSerial` schema keys (L103-116) plus reuse in
  `dataMaps` (L125, L154, L157, L172-173, L180) and an unresolved sibling
  `device.@deviceID.deviceID` (L137).

Note `@var` substitution is **not** exclusively a device mechanism — `@period`,
`@timezone`, `@timestamp`, `@conditionIcon`, `@type` serve metadata and unit
resolution across PirateWeather/OpenWeatherMap/OpenMeteo. Only the
device-related vars (`@deviceSerial`, `@deviceID`, `@hubSerial`,
`@deviceName`, `@deviceIdentity`, `@deviceAddress`) are in scope; the
machinery itself stays.

## Impact on `feat/govee-multi-device-rewrite`

**Survives unchanged** — `SharedScanner`, `LifecyclePlugin` (absorbing the five
duplicated bootstrap closures), and the model-preset table. These are exactly
the plumbing a `Device` implementation needs, and the preset table is the
Davis Sensor Catalog pattern already done right.

**Does not survive** — `PluginsLoader.__instances__` as a device-multiplier.
It encodes device≡plugin-instance, which the multi-source requirement
contradicts. It may return as a *device* factory.

**Recommendation:** tell Blackfish to pause further multi-device architecture
and land only the parts above, rather than building more on `__instances__`.

## Open questions

1. Are dimensions a general dict, or a fixed `device` slot plus escape hatch?
   General is more Prometheus-like and handles depth/probe; fixed is cheaper
   and enough for today. (Prometheus cardinality warnings do **not** apply at
   this scale — two thermometers, not millions of series.)
2. Does `MultiSourceContainer` stay keyed by plugin name, or move to keying by
   `(device, plugin)`? The multi-source-per-device requirement pushes toward
   the latter.
3. Do plugins with no meaningful device (OpenMeteo, PirateWeather) get one
   implicit device (the location), or is `device` optional? Implicit-device is
   more uniform; optional is less ceremony.
4. Migration for the live `default.levity`: a compat shim reading `#alias`, or
   a one-shot rewrite? Given the tiny blast radius, a rewrite plus keeping
   `#alias` as permanent sugar may be simplest.

## Verification

- Pure-Python tests for the registry: same MAC from two plugins resolves to
  one device; macOS-UUID fallback picks the plugin-scoped identifier; alias
  changes don't re-key.
- `tests/plugins/test_categories.py` already covers identity round-trip
  (L55/65/90-104) — those tests define what must keep working or change
  deliberately.
- The end-to-end proof is the one still unmet on the Govee branch: **two
  physical thermometers reporting simultaneously through a stop/start cycle**,
  which needs a Bluetooth-entitled terminal (see CLAUDE.md's macOS BLE gotcha).
