# Roadmap

*Last updated: 2026-10-06 (plan for first stable cut and lanes merged in).*

This organizes and supersedes the raw idea list in [`_planned-features.md`](_planned-features.md) — every item from that list is either placed in a section below, marked as already done, or parked with a reason. Status notes reference the code so claims stay checkable.

---

## Where things stand

The 2026 revival brought the project from a long-dormant WIP tree to a healthy, tested, modern codebase:

- **Modern floor** — Python 3.14 + PySide6 6.11 + numpy 2.x (was Python 3.11 + Qt 6.6; the docs' PySide2/Qt5 era is long gone).
- **Graph pipeline off the GUI thread** — data prep, path building, and painting now run on pooled workers with render coalescing; the felt lag and the "something in graph is not on the proper thread" suspicion are both resolved.
- **Size-group text fitting rewritten** — stateless refit engine (`lib/ui/Groups.py`), with proximity clustering and baseline alignment actually wired for the first time.
- **`statekit` + `qolkit` extracted** — the declarative state/YAML-persistence layer (`src/statekit/`) and generic Python utilities (`src/qolkit/`) are now standalone, Qt-free, in-repo packages with pure-Python test suites. `lib/stateful.py` remains as a thin Qt facade, so no consumer code changed.
- **First real test harness** — `tests/` covers statekit, qolkit, and headless (offscreen) UI/dashboard behavior.

## Plan: first stable cut, then lanes

Draft, 2026-10-06. Two questions are open (last part of this section).

**Diagnosis.** Code is no longer the bottleneck. On 2026-10-05 and 06, threads opened and merged 11 PRs (#18 to #28). The limits now are attention, the token budget, and verification. Verification still needs the Mac too often. So: fewer things, finished, and checks that run without a person.

**The spine: the render pipeline.** `render_dashboard.py`, `render_service.py`, the scenarios and the render_diff harness do four jobs:

- CI: render every reference board and compare it with a baseline.
- Agent checks: a thread sees its change without a real window.
- Design: a mockup becomes a real board that is rendered and compared.
- HUDs: the same renderer makes frames for e-paper devices.

Invest here first. Every lane uses it.

**Phase 0: now.** Smoke-test the merge at `e899cb0`. The live display log is clean. Still to run, after a go: the full suite on Python 3.14, and offscreen renders of the 32 `.levity` files under `docs/design-references/`.

**Phase 1: foundation.** Small tasks. Each makes later tasks cheaper.

1. CI on GitHub Actions. Run the suite and render_diff on every PR. Report the result. Do not block a merge on it.
2. Cloud threads on Python 3.14 with the en_US locale, so a thread's test result matches the Mac.
3. Fail-soft load. When one item fails to load, show an error tile in its place. Never blank the whole board.
4. Fix the known segfaults: the mini-graph debug repr in a worker thread, and the crash after the QBasicTimer cross-thread warning.

**Phase 2: first stable cut.**

1. Fix the rain `0.0` bug (a true zero shows as trace) and the WeatherUnits percent bug (0.1% shows as 10%).
2. Build one or two real weather boards from the paused design (Station, Core + rotation). Use themes, `switch` and `vars`. The handoff is `docs/tasks/dashboard-design-handoff.md` on branch `claude/dashboard-design-uy2w74`.
3. Document themes, variables, the switch slot and unit literals. Threads write draft notes. The docs owner edits the `docs` branch.
4. Close out value-sources.
5. Merge `feat/value-sources` into `main` and tag a version. After that, work on short branches off `main`.

**Phase 3: lanes, one at a time.**

- HUD: serve frames from `render_service` at device size and palette. Add an e-paper theme. Write the ESP32-S3 client that fetches a frame and keeps the last one. Builds on the surface frontend in [render-service-and-surface-frontend.md](tasks/render-service-and-surface-frontend.md).
- Data: a psutil plugin for host vitals, which also feeds the processes table. Rooms from Govee BLE with value-sources `where`. Rates and compound units (in/hr, kWh, W/m²), which need the parked WeatherUnits `dimensional-analysis` branch.
- Look: rename `needle` to `pointer`, linear meters and bars, and theme polish (gradient background, themed glow and moon, a theme picker).
- Editor: Studio snapping and guides. Decide whether Studio ships as the board editor.

**How we work.**

- One or two threads at a time, with one line per thread in the project chat.
- Decisions come in batches. The current batch: beam colour space, beam keys, sweep length, glow defaults, gradient-edit details, tick-label `position: inside`, and `needle` to `pointer`.
- Sonnet writes code. The coordinator plans and reviews. Opus works only on request.
- Mac-only steps go to a Remote Control session on the Mac.

**Open questions.**

1. Who is the first stable cut for? Options: the author only; weather-station owners such as Tempest and PiConsole users (recommended, since a concrete audience gives the cut a finish line); everyone.
2. Which lane comes first after the cut? Options: HUD (recommended: it is the north star, and `render_service` already renders frames); data; look; editor.

---

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

- **Key addressing: `@source` and `#identity`** — ~~`#identity`~~ **done 2026-07-27**: `CategoryItem` carries an `identity` (`indoor.temperature.temperature#bedroom`), with `withIdentity`/`withoutIdentity`. It participates in equality, hashing *and* the `__existing__` interning key — two identities are never merged, unlike sources which are reconciled. `#` rather than `@` because `@` is already a registered wildcard used for schema placeholders (`@deviceName`). ~~Still to do: **`@source` in string form**~~ — **done 2026-09-04**: sourced keys now round-trip. `str()` emits `source:path#identity` and the constructor splits both affixes off before tokenizing (`splitKeyString`), so the `:`-prefix parses back instead of folding the source into the path atoms. The sigil stays `:` rather than `@`, for the same reason identity is `#`: `@` is a registered wildcard used by schema placeholders. `__new__` and the `source` setter now share one normaliser, so `source=['X']` and `source=('X',)` no longer intern to two different instances. Consumer: [govee-multi-device.md](tasks/govee-multi-device.md).
- **Dynamic property bindings** — use any value as an input to any display property, e.g. `color: TemperatureGradient(temp.feelslike)` on a panel whose text shows a different key. The gradient half already exists (`ColorGradientMixin`); the binding layer (parse expression → subscribe to referenced keys → recompute on change) is new. This also delivers "global colors linked to a value gradient map" in a more general form.
- **Persistent data** (old-list milestone) — backend caches observations across restarts, so the dashboard isn't empty while plugins warm up. Belongs in the backend once the split lands; supersedes the pickle-on-close / `__reduce__` / dill notes.

## Long-term vision

Multiple frontend types on different platforms — desktop Qt, web, and small embedded heads-up displays around the house. HUD nodes are **bidirectional**: a garage display with a temp sensor is also a data *source*, feeding the backend like any plugin (the multi-source merge layer already models this). Implications tracked against every design decision:

- Wire protocol must be language-agnostic and compact (msgpack/CBOR candidates; JSON first).
- The client/server boundary blurs toward a broker/bus topology — MQTT deserves a serious look. **An adapter layer is required regardless**, so key↔topic mismatches are its job rather than constraints on the key syntax:
  - separators differ (`.` vs `/`), and both `#` (multi-level wildcard) and `+` (single-level) are reserved. `#` is *also* LevityDash's identity separator (`…temperature#bedroom`), so an identity-bearing key is never a valid topic verbatim.
  - the deeper mismatch: **source and identity are two orthogonal axes, and a topic space is one hierarchy.** Any flattening picks an order and makes the other axis awkward to subscribe against.
  - **MQTT v5 user properties look like the better fit than topic segments** — carry the key as the topic and let source/identity ride as properties. Sidesteps escaping entirely and keeps both axes independently filterable.
  - **Last Will and Testament maps onto the control plane** better than heartbeats do: in a broker topology the broker announces a dead client, so `plugin_status`/`heartbeat` (`lib/wire/messages.py`) would become a birth/LWT pair rather than a poll.
- The core state/notification layer must stay Qt-free — statekit already is.
- Open problem: `.levity` layout files are Qt-rendering-coupled; heterogeneous frontends need their own layout model or a shared abstract one.
- **Candidate answer — a "fixed"/baked layout mode.** *Not a priority; recorded so the option isn't rediscovered from scratch.* Once a dashboard is locked, bake the resolved layout — absolute rects, font sizes, baselines — and ship *that* over the wire. A thin frontend then does no layout at all: it draws strings at known coordinates and swaps values as messages arrive. That is a far smaller thing to implement than a second LevityDash, and it's what would make genuinely low-end heads (a Pi-class board, a framebuffer/LVGL renderer, a plain web page) viable, since the hardest component to port is `lib/ui/Groups.py`'s clustering/shared-scale fitting.
  - Secondary win on the Qt side too: it removes the startup fit cascade (the biggest chunk of time-to-first-paint) and stops value-driven refits — a shared scale of `min(...)` means one value widening (`9.0` → `10.0`) currently shrinks its whole group, which is both a recompute and a visible glitch on data arrival.
  - **Bake against worst case, not current values**, or the first three-digit reading breaks the layout. The widest possible rendering per field is derivable rather than observed: `digit_budget` caps the digit count and the format spec pins unit and separators.
  - Keep it a **sidecar, not part of the `.levity`** — the dashboard file stays portable and hand-editable while the bake stays machine-specific and disposable. Fingerprint on `(viewport, DPI, font families actually resolved)` and recompute on mismatch; a silently-stale bake fails as overflowing or floating text with no error.
  - Fixed-width digits make a bake meaningfully safer (a numeric field's width stops depending on *which* digits), which the current dashboard already leans on.
  - **Lighter still: push rendered *surfaces* rather than layout.** The client blits images and draws no text at all — no fonts, no shaping, no `Groups.py`. See [render-service-and-surface-frontend.md](tasks/render-service-and-surface-frontend.md), which also proposes the warm render service that is both a dev convenience and the prototype of this. Baked layout suits a client that *can* draw and wants low bandwidth; surfaces suit a client that can barely do anything (e-ink, microcontroller). Not rivals.

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

- **Stale-value indicator is too eager.** The "X mins ago" marker appears whenever a value is older than a fixed threshold, but "old" only means anything relative to *that source's* refresh period — a BLE thermometer advertising every ~20s and an hourly forecast poll are both perfectly fresh at 5 minutes. It should stay hidden while a value is within the plugin's expected interval and only surface once a refresh has actually been *missed*.
  - Regular sources can declare their period. **Irregular ones (BLE, push) should infer it** from observed update intervals — a rolling median of recent gaps, so the threshold adapts instead of being guessed. That also makes the indicator meaningful: it then means "this source has gone quiet relative to its own habits", which is the thing worth knowing.
  - Related: the backend now tracks `lastPublish` per plugin for the control plane (`lib/wire/messages.py`), which is the same measurement one layer up — worth sharing the inference rather than computing staleness twice.
- **Graph Y-axis labeling** — the graph only labels peaks/troughs and the time axis today.
- **Carousel-style direction display** — `[w N e]` sliding compass.
- **String plots with a placement key** — plot glyph/condition strings positioned by a second key; combined with position-matched offset plots this enables mini forecast infographics.
- **Items menu with live preview** — insert menu shows a summary + two-day mini graph per item.
- **Duotone / two-color icons** — `fa:`/`mdi:`/`wi:` packs exist, single-color only.
- **Morphing glyphs (Morphicons-style icon transitions)** (tentative — 2026-08 feature-discussion thread; reference: morphicons.com, 6.5 KB JS lib that morphs any SVG icon pair via path normalization) — icons morph smoothly between weather conditions instead of popping. Qt port: parse SVG `d` → `QPainterPath` → normalize structure → interpolate per frame (`QPainterPath::interpolated` for same-structure pairs; fade-through fallback for bad matches). Notes: `fa:`/`mdi:` charMaps already carry raw SVG paths (`getIconSvg`); the `wi:` pack (what condition icons actually use) is chars-only today — needs SVG data or glyph-outline extraction first. Rendering must move from font glyph to path item (see `IndoorIcon`, `Handles/Various.py`). Shared prerequisite with duotone icons. Pairs with the sky-gradient background (condition-transition delight on a living background).
- **Day-progressing sky background** (tentative — 2026-08 feature-discussion thread) — a full-scene background that renders the sky as it *should* look right now and progresses through the day (sunrise → day → sunset → twilight → night) on a ~10-minute display timer. Split by cost: the **palette** is analytic — evaluate a sun/sky model (andrewwillmott/sun-sky — Hosek/Preetham; night/twilight transitions built in; C++, needs a Python port, though the math is small) at the current sun elevation (local astronomy, ~30 lines); the **clouds** come from baked forecast states (~8–24 per day, blended between) driven by the OpenMeteo plugin's existing `environment.clouds.cover.{cover,low,mid,high}` keys. No batch job needed — 10-min cadence is a display refresh, not a render; even the naive full-physics bake (144 frames/day, ray-marched like the deleted `marcopavanello/sky-generator`, whose only surviving copy is `~/Code/sky-generator`) is only ~1–2 min/day. New machinery: a scene background layer with a z-order convention (nothing today paints behind panels). Caveat: palette is exact physics; cloud placement is forecast-shaped stylization. Pairs with the sunset-quality forecast (render the *predicted* sunset palette on high-score evenings) and morphing glyphs.
- **Graph annotations as items** rather than an attribute.
- **More plot types** — bar and violin plots landed (`plot: {type: bar}`, `{type: violin, bucket: 1h}`, see `docs/design-references/bar-plots.levity`); area fills and string plots are still open.
- **Larger module ideas** (from the old docs' "planned modules"): weather radar, multiline text, RSS feeds, calendar.
- **Agent status panels** (tentative — 2026-08-08 feature-discussion thread) — a panel type that renders an agent's (Blackfish's) live status: busy/idle light, current task, progress bar, last result. Show when active, hide when idle — pairs with the conditional-panels backlog item ("show when status ≠ idle"). Data flow is the interesting half, and the state already exists upstream:
  - **HARK activities** (hark.ryan.ceo — the webhook service driving the iPhone Live Activity) expose current task/status/progress as an API; a tiny polling plugin turns `activities` into keys (`agent.status`, `agent.task`, `agent.progress`).
  - **Agent-written status file** — the agent (Hermes) writes `status.json` per task (task, model, progress, ETA, last-verdict); a file-watcher plugin publishes it. Simplest possible contract, no API to build.
  - **Hermes session state** — what session is active, last activity (heavier; the two above cover 90%).
  - Payload shape should be the same regardless of source (a `status` source with `state ∈ {idle, busy}` + free-form detail), so the panel and the conditional rule don't care which feed they ride. Verified live alongside the "Sweep round 2" model tests (2026-08-08) — the HARK activity was effectively this panel on a phone.

### Data layer

- **Filter functions by key** — registerable functions that transform values matching a key.
- **Live value smoothing** — generalize `rollingAverage` (`observation.py:954`; currently used only for wind speed feeding wind-chill) into a per-key plugin-scheme option.
- **WeatherUnits: expose conversion factors.**
- **Sunset/sunrise quality forecast** (tentative — from the 2026-08 feature-discussion thread; reference: Sunsethue's published whitepaper, sunsethue.com/whitepaper) — a 0–100 score for how spectacular tonight's sunset will be, computed locally from Open-Meteo data (no third-party API). The services' models are simple and public: Sunsethue = ray casting through weather-model cloud layers (reflection potential per layer → observer rays → average), post-processed by surface humidity + golden-hour duration by latitude/season; Sunset Predictor = plain weighted heuristic (cloud 30–70% ideal, humidity 30–60%, visibility >10 km, wind, precip). Local difficulty: heuristic ≈ an afternoon, ray-based 3-layer version ≈ a weekend (sun azimuth/elevation math is ~30 lines). The OpenMeteo plugin schema already exposes `environment.clouds.cover.{cover,low,mid,high}`, `environment.humidity.humidity`, `environment.light.{sunrise,sunset}` — missing pieces are hourly *forecast* data at the sunset hour and `visibility` (one-line API additions, still free/no-key). Cost is negligible at one location (sub-ms; the world-scale grid only exists for their global maps) — a once-a-day recompute is the same cadence SunsetWx itself uses (~1pm), and riding the plugin's existing refresh is free. Natural fit: the "filter functions by key" pattern, or a computed key. Pairs with the sky-gradient background idea (render the *predicted* sunset palette on high-score evenings) and "Event notifications" (alert when tonight scores high).
- ~~**WeatherUnits `.withUnit` force-show defect**~~ — fixed in WeatherUnits `7b59613`. Root cause was narrower than "parameter threading": `FormatSpec.params` only matched `key=value`, so `.withUnit`'s `showUnit: True` spec was silently discarded and forced nothing. Same bug also made `format: {unit}` (used by `Realtime.unitPosition` to isolate a bare unit symbol) return the whole rendered measurement. The `expectedFailure` marker in `test_temperature.py` is gone and `tests/test_format_spec.py` guards both.

### Plugins

- **Watchdogs / health checks** — auto-restart and heartbeat for wedged plugins. The `health_check_worker` scaffold in `lib/backend.py` needs rebuilding now that backend.py is the live headless process.
- **Network failure/recovery hardening** — REST plugins already retry (`ScheduledEvent.retry`); the UDP socket path only logs `connection_lost` and never reconnects.
- **Govee: broader device support** — `closest`/`first`/MAC/UUID selection all work; only GVH5102 is tested. Extend model coverage and parsing presets.
- **Bluetooth-unavailable handling** — test/degrade gracefully when the adapter is missing or permission-blocked (macOS TCC).

### App & platform

- **Keep-awake option** — prevent *system/display* sleep for an always-on kiosk display: `caffeinate` (macOS), `xdg-screensaver`/`systemd-inhibit` (Linux), `powercfg`/`SetThreadExecutionState` (Windows). Distinct from macOS App Nap (a per-process background-timer throttle, independent of system sleep settings) — App Nap is already opted out of unconditionally at startup via `preventAppNap()` (`lib/utils/shared.py`), both frontend and backend.
- ~~**Runtime log-level menu**~~ — **done 2026-10-07**: Logs > Log Level (file and console) and Logs > Status Bar Level, each a radio list from Error to Verbose (`app.py` `_levelMenu`, `_LevityLogger.setRuntimeLevel`). A change applies at once and lasts until restart; nothing is written to the config.
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
| Value-sources, themes, variables, switch slot, unit literals, gauge vocabulary | Done 2026-10 — merged in PRs #18 to #28 into `feat/value-sources` (tip `e899cb0`). Still to do before release: see the plan above. |

## Parked (kept for reference, no current plan)

- **AnyIO** — staying on plain asyncio; per-plugin loops work fine and the split reduces pressure further.
- **redis / keyring / dill / marshmallow / `__reduce__` everywhere** — superseded by the backend-persistence plan above.
- **better-regex / pyparsing** — no current parsing pain that warrants them; the `@`/`#` key parser may revisit.
- **appdirs → platformdirs** — appdirs works today; revisit only if it breaks on a new OS version.
- **sortedcontainers for MeasurementTimeSeries** — superseded by the split (series ownership moves backend).
- **Font shortlist, rich color list, sidekick** — raw notes preserved in `_planned-features.md`.
- **"Replace indoor temperature with wind box"** — dashboard-specific note, not a feature.
