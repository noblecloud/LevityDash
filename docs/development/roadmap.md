# Roadmap

*Last updated: 2026-07-22 (v0.3.0-beta.1, timeseries over the wire merged).*

This organizes the project's raw idea list into a triaged plan — every item is either placed in a section below, marked as already done, or parked with a reason. Status notes reference the code so claims stay checkable.

---

## Where things stand

The 2026 revival brought the project from a long-dormant WIP tree to a healthy, tested, modern codebase:

- **Modern floor** — Python 3.14 + PySide6 6.11 + numpy 2.x (was Python 3.11 + Qt 6.6; the docs' PySide2/Qt5 era is long gone).
- **Graph pipeline off the GUI thread** — data prep, path building, and painting now run on pooled workers with render coalescing; the felt lag and the "something in graph is not on the proper thread" suspicion are both resolved.
- **Size-group text fitting rewritten** — stateless refit engine (`lib/ui/Groups.py`), with proximity clustering and baseline alignment actually wired for the first time.
- **`statekit` + `qolkit` extracted** — the declarative state/YAML-persistence layer (`src/statekit/`) and generic Python utilities (`src/qolkit/`) are now standalone, Qt-free, in-repo packages with pure-Python test suites. `lib/stateful.py` remains as a thin Qt facade, so no consumer code changed.
- **First real test harness** — `tests/` covers statekit, qolkit, and headless (offscreen) UI/dashboard behavior.

## Now: plugin control plane

Settled design decisions carried forward from Phase 4.2 (the full split is now merged):

- **Seam**: Publisher → dispatcher boundary. The dispatcher, `MultiSourceContainer`, and all widget wiring stay frontend-side.
- **Source reconciliation stays frontend** — the "best available value until the preferred source arrives" logic runs unchanged, operating on `RemoteContainer` stand-ins fed by raw per-source pushes.
- **Timeseries never stream as objects** — request/response with columnar payloads, which also eliminates today's UI-thread series rebuilds.
- **Key-first subscriptions** — a panel can subscribe to any number of keys.
- **Data crosses onto the GUI thread at the wire boundary** — every update is marshaled once at the wire→frontend seam.
- **`live` mode unchanged; `remote` is attach-only** — no spawned local backend subprocess.

Active milestones:

- ~~wire codec~~ → ~~`RemoteContainer` + in-process loopback~~ → ~~standalone backend process~~ → ~~frontend WS client (reconnect/attach)~~ → ~~timeseries over WebSocket (request/response)~~ (all done — `RemoteContainer.timeseries` is now populated by a real request/response round trip; graphs render in remote mode, verified against a real two-process run) → **plugin control plane (start/stop/health)**

Timeseries shipped with two known gaps tracked in `docs/tasks/timeseries-viewport-and-control-plane.md`: the wire-fetched window is a fixed ±3h, not viewport-aware, and a pre-existing `Graph.py` smoothing fragility surfaces more easily against that narrower window. The control plane adds watchdog heartbeats and remote plugin lifecycle.

## Next, after the split

- **Key addressing: `@source` and `#identity`** — formalize "keys that can also include a source" from the old list. `@source` names *who provides* a value (reconciled/merged across providers — `CategoryItem.source` already exists); `#identity` names *which* value it is (bedroom vs. garage temp — never merged). Needs parser + hashing work in `categories.py` and care around the existing `@`-wildcard convention.
- **Dynamic property bindings** — use any value as an input to any display property, e.g. `color: TemperatureGradient(temp.feelslike)` on a panel whose text shows a different key. The gradient half already exists (`ColorGradientMixin`); the binding layer (parse expression → subscribe to referenced keys → recompute on change) is new. This also delivers "global colors linked to a value gradient map" in a more general form.
- **Persistent data** (old-list milestone) — backend caches observations across restarts, so the dashboard isn't empty while plugins warm up. Belongs in the backend once the split lands; supersedes the pickle-on-close / `__reduce__` / dill notes.

## Long-term vision

Multiple frontend types on different platforms — desktop Qt, web, and small embedded heads-up displays around the house. HUD nodes are **bidirectional**: a garage display with a temp sensor is also a data *source*, feeding the backend like any plugin (the multi-source merge layer already models this). Implications tracked against every design decision:

- Wire protocol must be language-agnostic and compact (msgpack/CBOR candidates; JSON first).
- The client/server boundary blurs toward a broker/bus topology — MQTT deserves a serious look (note: `#` is MQTT's wildcard, so key↔topic mapping must escape it).
- The core state/notification layer must stay Qt-free — statekit already is.
- Open problem: `.levity` layout files are Qt-rendering-coupled; heterogeneous frontends need their own layout model or a shared abstract one.

---

## Feature backlog

Triaged and grouped by area. ~~Struck~~ items are already done (see the last section).

### Dashboard authoring

- **Conditional dashboards / panels** — show/hide panels (or switch whole dashboards) based on conditions, including plugin status. Today there's only a static `disabled-` type prefix and template auto-selection by enabled plugin.
- **Position relative to sibling items** — "center this item with the center of that item." All current positioning is relative to the parent only.
- **Migrate `shared:` → named `preset:`** — both exist today (`preset` at `Stacks.py:892`, `Stateful.shared` at `statekit/core.py:1925`); the direction is named, reusable presets over anonymous inheritance.
- **Screen-size conditions for size options** — different sizing rules per display size.
- **Scrolling in overfilled stacks.**
- **Condensed-title option** — possibly automatic by available size.
- **Corner radius** on panels.
- **Fill object** — one abstraction accepting colors, gradients, images, and patterns; today `FillBrushMixin` handles color + gradient only. Include dynamic color functions and plot-line section dividers.
- **Value templates** — file-loadable templates combining multiple values into one composite display.
- **Layout in a separate file** — split panel layout from the rest of the dashboard spec.
- **Groups default to grid/stack** unless specified; explicit item geometry overrides.
- **`type: split` in YAML** — `SplitPanel` exists but is only insertable from the context menu; it isn't wired into `itemLoader`.

### Display modules

- **Graph Y-axis labeling** — the graph only labels peaks/troughs and the time axis today.
- **Carousel-style direction display** — `[w N e]` sliding compass.
- **String plots with a placement key** — plot glyph/condition strings positioned by a second key; combined with position-matched offset plots this enables mini forecast infographics.
- **Items menu with live preview** — insert menu shows a summary + two-day mini graph per item.
- **Duotone / two-color icons** — `fa:`/`mdi:`/`wi:` packs exist, single-color only.
- **Graph annotations as items** rather than an attribute.
- **More plot types** — bar plots are still not fully implemented.
- **Larger module ideas** (from the old docs' "planned modules"): weather radar, multiline text, RSS feeds, calendar.

### Data layer

- **Filter functions by key** — registerable functions that transform values matching a key.
- **Live value smoothing** — generalize `rollingAverage` (`observation.py:954`; currently used only for wind speed feeding wind-chill) into a per-key plugin-scheme option.
- **WeatherUnits: expose conversion factors.**
- **WeatherUnits `.withUnit` force-show defect** — format-spec parameter threading doesn't override instance defaults (documented as an expected-failure test in WeatherUnits' `test_temperature.py`).

### Plugins

- **Watchdogs / health checks** — auto-restart and heartbeat for wedged plugins. The `health_check_worker` scaffold in `lib/backend.py` needs rebuilding now that backend.py is the live headless process.
- **Network failure/recovery hardening** — REST plugins already retry (`ScheduledEvent.retry`); the UDP socket path only logs `connection_lost` and never reconnects.
- **Govee: broader device support** — `closest`/`first`/MAC/UUID selection all work; only GVH5102 is tested. Extend model coverage and parsing presets.
- **Bluetooth-unavailable handling** — test/degrade gracefully when the adapter is missing or permission-blocked (macOS TCC).

### App & platform

- **Keep-awake option** — `caffeinate` (macOS), `xdg-screensaver`/`systemd-inhibit` (Linux), `powercfg`/`SetThreadExecutionState` (Windows).
- **Runtime log-level menu** — change log level (and status-bar update level) from the menu bar; the Logs menu currently only opens/submits logs.
- **Dashboard-level config overrides** — per-dashboard settings that override global config.
- **Event notifications** — user-facing alerts (lightning nearby, rain starting, etc.).
- **Self-installer & packaging** — PyInstaller flow is unblocked (6.x) but unverified on the 3.14 stack; multi-OS builds via GitHub Actions.

---

## Already done (items from the old list)

| Old-list item | Where it landed |
|---|---|
| Gauges "nearly complete" | Done — `displayType: gauge` under realtime (`Displays/Gauge.py`, registered in `PySide/utils.py:503`) |
| Mini graphs | Done — top-level `type: mini-graph` (`PySide/utils.py:355`) |
| Cache graph renders / graph thread suspicion | Done — Phase 2: off-thread painting, render coalescing, shared shadow-bake scene |
| Plugins with included templates | Done — per-plugin dashboards in `resources/example-config/templates/dashboards/` |
| Proper log names for all modules | Done — consistent `getChild()` hierarchy throughout |
| Proper device filtering for Govee | Mostly done — `closest`/`first`/MAC/UUID selection implemented |
| `stateful prep_init` / StateProperty factory+update | Absorbed into the statekit extraction |
| Keys that include a source | Partially — `CategoryItem.source` exists; full `@`/`#` addressing is in "Next" |
| refresh handles iterating all children | Fixed (was marked "probably fixed" — confirmed during the revival) |
| Fix delayed/blocked parent-resized signals while loading | Effectively resolved by the size-group engine rewrite + settle-time refits |
| OpenWeatherMap plugin | Done — was a disabled skeleton (schema shadowed by an empty class attr); rebuilt against the free Current Weather Data endpoint (One Call requires a paid plan), with a `normalizeData` flatten step for its nested response shape. Verified live against the real API. |
| Phase 4.2 backend/frontend process split | Done — wire codec, typed messages, aiohttp WebSocket server + client, RemoteBackend/Frontend adapters, RemoteContainer stand-ins, GuiMarshal single-hop bridge, standalone backend entry point (`LevityDash-backend`). Merge `fce2568`. Full dashboard renders on first paint in remote mode; 125-pass test suite. |
| Timeseries over the wire | Done — columnar codec, ts_request/ts_response messages, unicast dispatch in WireServer, request correlation in WireClient, RemoteBackend's Qt-thread/thread-pool/asyncio-thread hop, RemoteTimeSeries stand-in. Verified against a real two-process run, which also caught a dispatcher.getTimeseries fast-path bug (fixed with a `timeseries is not None` guard). 150-pass test suite. Known gaps in `docs/tasks/timeseries-viewport-and-control-plane.md`. |

## Parked (kept for reference, no current plan)

- **AnyIO** — staying on plain asyncio; per-plugin loops work fine and the split reduces pressure further.
- **redis / keyring / dill / marshmallow / `__reduce__` everywhere** — superseded by the backend-persistence plan above.
- **better-regex / pyparsing** — no current parsing pain that warrants them; the `@`/`#` key parser may revisit.
- **appdirs → platformdirs** — appdirs works today; revisit only if it breaks on a new OS version.
- **sortedcontainers for MeasurementTimeSeries** — superseded by the split (series ownership moves backend).
- **Font shortlist, rich color list, sidekick** — raw notes, kept for reference.
- **"Replace indoor temperature with wind box"** — dashboard-specific note, not a feature.
