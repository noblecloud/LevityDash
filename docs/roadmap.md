# Roadmap

*Last updated: 2026-07-22 (v0.3.0-beta.1, timeseries over the wire merged).*

This organizes and supersedes the raw idea list in [`_planned-features.md`](_planned-features.md) — every item from that list is either placed in a section below, marked as already done, or parked with a reason. Status notes reference the code so claims stay checkable.

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

- ~~wire codec~~ → ~~`RemoteContainer` + in-process loopback~~ → ~~standalone backend process~~ → ~~frontend WS client (reconnect/attach)~~ → ~~timeseries over WebSocket (request/response)~~ (all done — `RemoteContainer.timeseries` is now populated by a real request/response round trip; graphs render in remote mode, verified against a real two-process run) → **plugin control plane**: ~~health + heartbeat~~ (done 2026-07-27 — `plugin_status` on change with late-joiner replay, plus an unconditional 5s `heartbeat`; `RemoteConnection.plugins`/`pluginsChanged` and a `backendAlive` watchdog that is deliberately distinct from `state == 'connected'`, since a wedged Qt loop keeps its socket open. Verified against a real two-process run) → **start/stop/restart commands** (not started; needs a UI to drive them to be worth much)

Timeseries shipped, including a follow-up pass making the wire-fetched window match the Graph panel's actual configured timeframe instead of a fixed ±3h (verified visually via an on-screen `.grab()` screenshot harness - see `docs/tasks/timeseries-viewport-and-control-plane.md`). The control plane adds watchdog heartbeats and remote plugin lifecycle.

## Next, after the split

- **Key addressing: `@source` and `#identity`** — ~~`#identity`~~ **done 2026-07-27**: `CategoryItem` carries an `identity` (`indoor.temperature.temperature#bedroom`), with `withIdentity`/`withoutIdentity`. It participates in equality, hashing *and* the `__existing__` interning key — two identities are never merged, unlike sources which are reconciled. `#` rather than `@` because `@` is already a registered wildcard used for schema placeholders (`@deviceName`). Still to do: **`@source` in string form**. `CategoryItem.source` exists and round-trips only partially — `str()` renders it as a `:`-prefix (`Govee:indoor.…`) which the constructor does *not* parse back, so sourced keys are not round-trip safe despite CLAUDE.md claiming they are. Consumer: [govee-multi-device.md](tasks/govee-multi-device.md).
- **Dynamic property bindings** — use any value as an input to any display property, e.g. `color: TemperatureGradient(temp.feelslike)` on a panel whose text shows a different key. The gradient half already exists (`ColorGradientMixin`); the binding layer (parse expression → subscribe to referenced keys → recompute on change) is new. This also delivers "global colors linked to a value gradient map" in a more general form.
- **Persistent data** (old-list milestone) — backend caches observations across restarts, so the dashboard isn't empty while plugins warm up. Belongs in the backend once the split lands; supersedes the pickle-on-close / `__reduce__` / dill notes.

## Long-term vision

Multiple frontend types on different platforms — desktop Qt, web, and small embedded heads-up displays around the house. HUD nodes are **bidirectional**: a garage display with a temp sensor is also a data *source*, feeding the backend like any plugin (the multi-source merge layer already models this). Implications tracked against every design decision:

- Wire protocol must be language-agnostic and compact (msgpack/CBOR candidates; JSON first).
- The client/server boundary blurs toward a broker/bus topology — MQTT deserves a serious look. ⚠️ **`#` is MQTT's multi-level wildcard, and it is now also LevityDash's identity separator** (`…temperature#bedroom`), so an identity-bearing key cannot be used as an MQTT topic verbatim — the mapping must escape it, or identity must ride as a topic segment/property instead. Decided knowing this: `@` was unavailable (schema wildcard) and identity needed a separator that reads naturally in a `.levity` file.
- The core state/notification layer must stay Qt-free — statekit already is.
- Open problem: `.levity` layout files are Qt-rendering-coupled; heterogeneous frontends need their own layout model or a shared abstract one.
- **Candidate answer — a "fixed"/baked layout mode.** *Not a priority; recorded so the option isn't rediscovered from scratch.* Once a dashboard is locked, bake the resolved layout — absolute rects, font sizes, baselines — and ship *that* over the wire. A thin frontend then does no layout at all: it draws strings at known coordinates and swaps values as messages arrive. That is a far smaller thing to implement than a second LevityDash, and it's what would make genuinely low-end heads (a Pi-class board, a framebuffer/LVGL renderer, a plain web page) viable, since the hardest component to port is `lib/ui/Groups.py`'s clustering/shared-scale fitting.
  - Secondary win on the Qt side too: it removes the startup fit cascade (the biggest chunk of time-to-first-paint) and stops value-driven refits — a shared scale of `min(...)` means one value widening (`9.0` → `10.0`) currently shrinks its whole group, which is both a recompute and a visible glitch on data arrival.
  - **Bake against worst case, not current values**, or the first three-digit reading breaks the layout. The widest possible rendering per field is derivable rather than observed: `digit_budget` caps the digit count and the format spec pins unit and separators.
  - Keep it a **sidecar, not part of the `.levity`** — the dashboard file stays portable and hand-editable while the bake stays machine-specific and disposable. Fingerprint on `(viewport, DPI, font families actually resolved)` and recompute on mismatch; a silently-stale bake fails as overflowing or floating text with no error.
  - Fixed-width digits make a bake meaningfully safer (a numeric field's width stops depending on *which* digits), which the current dashboard already leans on.

---

## Feature backlog

Triaged from `_planned-features.md`, grouped by area. ~~Struck~~ items are already done (see the last section).

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
- ~~**WeatherUnits `.withUnit` force-show defect**~~ — fixed in WeatherUnits `7b59613`. Root cause was narrower than "parameter threading": `FormatSpec.params` only matched `key=value`, so `.withUnit`'s `showUnit: True` spec was silently discarded and forced nothing. Same bug also made `format: {unit}` (used by `Realtime.unitPosition` to isolate a bare unit symbol) return the whole rendered measurement. The `expectedFailure` marker in `test_temperature.py` is gone and `tests/test_format_spec.py` guards both.

### Plugins

- **Watchdogs / health checks** — auto-restart and heartbeat for wedged plugins. The `health_check_worker` scaffold in `lib/backend.py` needs rebuilding now that backend.py is the live headless process.
- **Network failure/recovery hardening** — REST plugins already retry (`ScheduledEvent.retry`); the UDP socket path only logs `connection_lost` and never reconnects.
- **Govee: broader device support** — `closest`/`first`/MAC/UUID selection all work; only GVH5102 is tested. Extend model coverage and parsing presets.
- **Bluetooth-unavailable handling** — test/degrade gracefully when the adapter is missing or permission-blocked (macOS TCC).

### App & platform

- **Keep-awake option** — prevent *system/display* sleep for an always-on kiosk display: `caffeinate` (macOS), `xdg-screensaver`/`systemd-inhibit` (Linux), `powercfg`/`SetThreadExecutionState` (Windows). Distinct from macOS App Nap (a per-process background-timer throttle, independent of system sleep settings) — App Nap is already opted out of unconditionally at startup via `preventAppNap()` (`lib/utils/shared.py`), both frontend and backend.
- **Runtime log-level menu** — change log level (and status-bar update level) from the menu bar; the Logs menu currently only opens/submits logs.
- **Dashboard-level config overrides** — per-dashboard settings that override global config.
- **Event notifications** — user-facing alerts (lightning nearby, rain starting, etc.).
- **Self-installer & packaging** — PyInstaller flow is unblocked (6.x) but unverified on the 3.14 stack; multi-OS builds via GitHub Actions.
- ~~Dev auto-restart watcher~~ — done: `poetry run LevityDash-backend-watch` (`devtools/backend_watch.py`) watches `src/LevityDash`/`tests`, debounces, restarts the supervised backend only if the test suite passes, and serves a standard `GET /health`/`GET /status` API on `:8669` for any generic monitor/widget. The frontend's own in-app connection indicator (top-right dot, mode=remote only) is separate — driven directly by `RemoteConnection.connectionStateChanged` (`lib/wire/remote.py`), not by polling this tool.

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
| Phase 4.2 backend/frontend process split | Done — wire codec (`lib/wire/codec.py`), typed messages (`messages.py`), aiohttp WebSocket server (`server.py`) + client (`client.py`), `RemoteBackend`/`RemoteFrontend` adapters, `RemoteContainer`/`RemoteObservationValue` stand-ins, `GuiMarshal` single-hop bridge, standalone backend entry point (`LevityDash-backend` / `python -m LevityDash.backend`). Merge `fce2568`. Full dashboard renders on first paint in remote mode; 125-pass test suite. Follow-ups tracked in `docs/tasks/phase-4.2-follow-ups.md`. |
| Timeseries over the wire | Done — columnar codec (`encode_timeseries_values`/`decode_timeseries_values`), `ts_request`/`ts_response` messages, unicast dispatch in `WireServer`, request correlation in `WireClient`, `RemoteBackend.handle_ts_request`'s Qt-thread/thread-pool/asyncio-thread hop (mirrors `Container.prepare_for_ts_connection`'s own thread-pool pattern), `RemoteTimeSeries` stand-in. Verified against a real two-process run, not just unit tests — which is also how a `dispatcher.getTimeseries` fast-path bug (returned a flag-ready-but-not-yet-fetched `RemoteContainer` without ever triggering the fetch) got caught; fixed with a `timeseries is not None` guard, no-op for live mode. 150-pass test suite. Known gaps in `docs/tasks/timeseries-viewport-and-control-plane.md`. |

## Parked (kept for reference, no current plan)

- **AnyIO** — staying on plain asyncio; per-plugin loops work fine and the split reduces pressure further.
- **redis / keyring / dill / marshmallow / `__reduce__` everywhere** — superseded by the backend-persistence plan above.
- **better-regex / pyparsing** — no current parsing pain that warrants them; the `@`/`#` key parser may revisit.
- **appdirs → platformdirs** — appdirs works today; revisit only if it breaks on a new OS version.
- **sortedcontainers for MeasurementTimeSeries** — superseded by the split (series ownership moves backend).
- **Font shortlist, rich color list, sidekick** — raw notes preserved in `_planned-features.md`.
- **"Replace indoor temperature with wind box"** — dashboard-specific note, not a feature.
