# AGENTS.md — LevityDash

A desktop-native, multi-source weather dashboard. Qt (PySide6) QGraphicsScene frontend; plugin-driven data layer. Beta, used daily. This file is general-purpose guidance for AI agents (OpenCode/DeepSeek, Kimi, and similar) working anywhere in this repo — it isn't scoped to one subsystem.

> [CLAUDE.md](CLAUDE.md) covers the same repo from Claude Code's side (package layout, dependency direction, environment gotchas) — the two should stay roughly in sync. Direction/roadmap lives in [docs/roadmap.md](docs/roadmap.md). Deep-dive investigations, including a full trace of the schema/data-ingestion engine, live in `docs/reviews/` (see `docs/reviews/schema-pipeline.md`).

## Before you start a task

- **Task briefs live in `docs/tasks/`.** Each file there is a self-contained brief for one piece of work (bug fix, cleanup, investigation) with context, the concrete change expected, verification steps, and a suggested branch name. If you were pointed at this repo for a specific task, check there first — the human maintainer uses this directory to hand off work.
- **This clone's `origin` is a local path, not GitHub** (check `git remote -v` — it should point at another directory on this machine, e.g. `/Users/noblecloud/Code/LevityDash`, not a `github.com` URL). Nothing pushed from here reaches GitHub or the public internet; `origin` here is just the maintainer's own working copy. No `gh`/GitHub auth is needed or expected for this workflow.
- **Sync before you branch** — new task briefs and unrelated fixes land continuously: `git fetch origin && git checkout dev && git merge origin/dev` (or `git pull origin dev`). "Already up to date," a fast-forward, or a clean merge means you're good. A conflict means stop and flag it rather than resolving blindly — someone else's in-flight work likely overlaps with yours.
- **Work on your own branch, off `dev`.** Each task brief includes a suggested branch name.
- **When you're done: push your branch and stop there.** `git push origin <branch-name>` — this lands the branch in the maintainer's local repo without touching their checked-out `dev` (pushing to whatever branch they currently have checked out is refused by git itself, by design; pushing any other branch name always works). **Never merge into `dev` yourself, under any circumstances, even locally.** The maintainer (or Claude, when asked) reviews your branch with `git log`/`git diff` and merges it into `dev` themselves — that review step is the entire point of this setup.
- **Stay inside the task's stated scope.** Several task briefs explicitly call out what NOT to touch (usually because that code is tracked separately, or because it's mid-refactor elsewhere). Respect those boundaries even if you notice something else that looks wrong nearby — flag it instead of fixing it.

## Commands

```sh
poetry install                          # install deps (has local dev dep: ../WeatherUnits)
poetry run LevityDash                   # run desktop app (mode=live by default)
poetry run LevityDash-backend           # standalone headless backend (WebSocket server)
poetry run LevityDash-backend-watch     # dev only: debounced restart-on-change, gated on pytest passing
poetry run pytest                       # run all tests
poetry run pytest -xvs tests/ui/test_smoke.py
poetry run pytest -m unwired            # xfail-marked (unimplemented) tests
poetry run pytest tests/wire/           # wire-protocol tests (codec, transport, containers)
LEVITY_LOG_PLAIN=1 poetry run LevityDash  # plain logging: no rich console, markup or rich tracebacks ([Logging] plain = 1 in config does the same)
```

No linter, no formatter, no pre-commit hooks — `pytest` is the only gating command. Poetry uses an in-project `.venv` per directory, not a shared one: a fresh clone or worktree needs its own `poetry install` before anything runs (`poetry run pytest` failing with "command not found" means this step was skipped, not a real error).

## Project structure

```
src/
  qolkit/      generic Python QOL utilities (sentinels, DotDict, DeepChainMap,
               OrderedSet, descriptors) — zero domain/Qt coupling
  statekit/    declarative state + YAML persistence (StateProperty, Stateful,
               loaders/dumpers, ActionPool) — Qt-free, depends only on qolkit
  LevityDash/  the app (imported as `LevityDash`)
    lib/stateful.py            Qt facade over statekit — consumers import from
                               HERE, never from statekit directly
    lib/plugins/               data layer: plugins, observations, schema engine,
                               dispatcher ({key → MultiSourceContainer})
    lib/plugins/schema/        schema engine (Schema, LevityDatagram, Subdatagram) —
                               see "Schema engine" below, or docs/reviews/schema-pipeline.md
    lib/plugins/builtin/       OpenMeteo, PirateWeather, WeatherFlow, Govee (BLE),
                               OpenWeatherMap
    lib/wire/                  backend/frontend split wire protocol — see "Wire
                               protocol" below
    lib/ui/frontends/PySide/   the Qt frontend (app.py, Modules/Displays/…)
    lib/config.py              ConfigParser with ExtendedInterpolation
    lib/backend.py             headless backend process (live Plugins + WireServer);
                               entry point is the sibling backend.py, below
    backend.py                 package-level entry module — pins mode=live before
                               any lib import (see "Wire protocol"); LevityDash-backend
                               console script points here, not at lib/backend.py
    devtools/                  dev-only tooling, never imported by the shipped app —
                               backend_watch.py: watches src/tests, restarts the
                               backend on change gated on pytest passing (debounced),
                               serves GET /health + /status on :8669
    __init__.py                LevityDashboard singleton (immutable after init)
    __main__.py                entrypoint (main())
```

Dependency direction is strict: `qolkit ← statekit ← LevityDash`. Never import Qt or LevityDash from statekit/qolkit.

- `docs/` — docsify docs site; `docs/tasks/` = agent task briefs (see above); `docs/reviews/` = deep-dive investigations; `docs/roadmap.md` = direction (the Sphinx skeleton under `docs/source/` is vestigial)
- `build-to-app/` — PyInstaller build script + per-platform specs

## Schema engine (one subsystem, not the whole repo)

Plugin data ingestion, transformation, mapping, unit conversion, and validation. Worth its own section since it's dense and easy to get wrong — but it's one part of the app, not this file's whole scope. Full trace: `docs/reviews/schema-pipeline.md`.

- **`Schema`** (`lib/plugins/schema/__init__.py:606`): per-plugin registry mapping source keys to `UnitMetaData` (unit type, validation rules, source-key aliases, data-maps). Registered in `Schema.__schemas__` for cross-plugin lookup.
- **`LevityDatagram`** (`lib/plugins/schema/__init__.py:47`): dict subclass that parses raw data through the schema — key mapping, variable substitution, array expansion into `Subdatagram` lists, auto-validation.
- **`unitDict`** (`lib/plugins/schema/units.py`): maps ~50 unit codes to `WeatherUnits` types (`wu.temperature.Fahrenheit`, `wu.pressure.Hectopascal`, etc.). Drives automatic conversion and display formatting.
- **Schema config**: each plugin declares its schema as a Python dict in its own module (e.g. `builtin/OpenMeteo.py` `schema = {...}`) with `sourceKey`, `dataMaps`, `keyMaps`, `properties`, `metaData`, and `ignored` keys — not YAML.
- It's deliberately lenient in production (fuzzy-matches/degrades rather than crashing) — see `docs/tasks/loud-failure-dev-mode.md` if that's the task at hand.

## Wire protocol (backend/frontend process split, `lib/wire/`)

Splits the GUI app from a headless plugin backend over a WebSocket. Two modes:
`live` (single process, plugins straight to the dispatcher — what `LevityDash-backend`
always runs, and the GUI app's default) and `remote` (a *frontend*-only setting —
the Qt app attaches to an already-running standalone backend instead of starting
plugins itself; no spawned-local-backend path exists). See `docs/roadmap.md`
for the settled design decisions.

- **`codec.py`**: plain-value codec, Measurement/datetime/CategoryItem ↔ JSON-safe
  dicts (JSON, not msgpack). `_resolve_measurement_class` prefers a non-generic
  specialized class (by name, then by unit symbol) so derived units like Wind
  reconstruct correctly instead of degrading to a bare float.
  `encode_timeseries_values`/`decode_timeseries_values`: a columnar
  `{unit, cls, timestamps, values}` shape for a full series — unit/cls resolved
  once per batch, not once per point.
- **`messages.py`**: plain dict-building functions, not message dataclasses —
  `encode_container`/`apply_container_update` (per-key) wrapped by
  `encode_update_message`/`parse_update_message` (the backend→frontend-only
  envelope), plus `build_ts_request`/`encode_ts_response`/`decode_ts_response`
  (the frontend↔backend request/response pair for timeseries, correlated by a
  `uuid` `id`).
- **`server.py`** (`WireServer`) / **`client.py`** (`WireClient`): transport.
  Server broadcasts `'update'` messages to every connected client and replays
  the last snapshot to late joiners; an optional `on_request` hook answers
  `'ts_request'` unicast (not broadcast) to the requesting connection only.
  Client's `request()` correlates a request/response pair via a pending-futures
  map keyed by `id`; ordinary `'update'` messages still flow to `on_message`
  unaffected.
- **`backend.py`** (`RemoteBackend`): send side — attaches to each real
  plugin's `Publisher`, encodes changed containers on publish.
  `handle_ts_request` answers a timeseries request: a `_QtInvoker` marshals the
  plugin/container lookup onto the Qt main thread, then
  `plugin.thread_pool.run_threaded_process(..., direct=True)` runs the
  potentially-slow full-series rebuild off *both* the Qt and asyncio loops —
  mirrors `Container.prepare_for_ts_connection`'s own thread-pool pattern
  (`lib/plugins/observation.py`) rather than a new threading idiom.
- **`frontend.py`** (`RemoteFrontend`) / **`remote.py`** (`RemoteConnection`):
  receive side. `RemoteConnection` owns a dedicated thread + asyncio loop with
  a `WireClient` inside a reconnect/backoff loop; every message crosses to the
  GUI thread *exactly once* via `_GuiMarshal` (a queued Qt signal) before
  `RemoteFrontend` touches anything the scene graph can see — a design
  requirement, not an optimization (see `docs/roadmap.md`). `RemoteConnection`
  also exposes `.state`/`.connectionStateChanged` (`'connecting'`/
  `'connected'`/`'disconnected'`) — a plain last-known-state attribute
  alongside the Signal, so a late subscriber (the frontend's own in-app
  status dot, `app.py`'s `BackendConnectionIndicator`, mode=remote only) can
  seed itself correctly instead of assuming a state that may have already
  changed before it existed.
- **`containers.py`**: `RemoteSource`/`RemoteContainer`/`RemoteObservationValue`/
  `RemoteTimeSeries` — frontend stand-ins mirroring the live
  `Plugin`/`Container`/`ObservationValue`/`MeasurementTimeSeries` interfaces
  closely enough that `MultiSourceContainer` reconciliation and widgets (Graph
  included) run *unmodified* against them. `RemoteContainer.prepare_for_ts_
  connection` reads an optional `wireTimeseriesPeriod` duck-typed off the
  requester (Graph.py's `GraphItemData` implements it) to match a wire fetch to
  whatever timeframe the requester actually needs, falling back to a fixed
  default window when absent.
- **`bridge.py`** (`LoopbackBridge`): `mode=loopback` — both halves in-process,
  still a genuine JSON round-trip through the same codec/messages functions,
  for fast dev-loop testing without a real socket.

## Test quirks

- **`conftest.py`** sets `QT_QPA_PLATFORM=offscreen` and `LEVITYDASH_CONFIG_DEBUG=1` **before any PySide6 import** (top-level, not in a fixture).
- **`LEVITYDASH_CONFIG_SEED`** (also set by conftest) points at `tests/resources/config-seed/` — an *established* user config (onboarding pre-answered, real OpenMeteo dashboard with graphs) layered over the throwaway debug config dir, so integration tests exercise real render paths instead of the fresh-install/`Empty.levity` state. Unset it for tests that specifically want the onboarding path.
- Session-scoped `dashboard` fixture boots a real Qt app headlessly without entering `exec_()`. Plugins loaded, never started.
- `frozen_time` fixture freezes `shared.now`, `strftime`, `datetime.now`, and the Moon module's `datetime.now(tz)` (patched separately — it reads the module directly) to `2025-06-18 14:30`.
- `pump(app, seconds)` helper processes Qt events without `exec_()`.
- `unwired` marker = xfail (behaviour not yet implemented).
- Plugin tests exercise `normalizeData`/schema as unbound logic against captured, sanitized real API responses as golden fixtures — no network, no full `Plugin` bootstrap needed (see `tests/plugins/test_openweathermap.py` for the pattern).
- `tests/wire/` mostly avoids a full app/plugin bootstrap too — hand-built `Plugin`/`Container`/timeseries stand-ins over real `WireServer`/`WireClient`/`RemoteBackend` sockets (see `test_wire_ts_end_to_end.py` for the fullest example). `test_remote_boot.py` is the exception: a real subprocess boots a real `WireServer` against real (fabricated) OpenMeteo-shaped data, asserting zero tracebacks on stderr.

## Style & config

- **Indentation**: tabs (2-width) for `.py`, spaces for `.yaml`/`.spec` (`.editorconfig`).
- **Max line length**: 240.
- **Python**: 3.13–3.14.
- **Config**: `ConfigParser` with `ExtendedInterpolation`; `LEVITYDASH_CONFIG_DEBUG=1` redirects paths to temp dirs.
- **Logging**: Custom verbosity levels (0–5), Rich console + rotating file handler. Traceback locals off by default (live Qt objects crash on concurrent repr).

## Notable quirks

- **`cached_property` lock**: Python <3.12 gets an unlocked backport (`__init__.py:20`) to prevent Qt signal deadlocks.
- **`LEVITY_BUILDING=TRUE`**: bypasses compile-time checks during PyInstaller build.
- **PyInstaller**: per-platform specs at `build-to-app/specs/{macOS,windows,linux}.spec`.

<!-- BEGIN OPENLORE (managed — edits inside this block will be overwritten) -->
<!-- openlore-fingerprint: 25cdd746ebf39b56 -->
This project uses OpenLore for persistent architectural memory.

ALWAYS call `orient()` (via the openlore MCP server, or `npx openlore orient --json`)
before reading source files when starting a new task. This returns the relevant
functions, callers, spec sections, and insertion points for the task at hand —
one structural lookup instead of file-by-file rediscovery.

OpenLore prefixes tool responses with a brief, factual freshness note (the
Epistemic Lease) once your cached context has aged or the repo has moved since
your last `orient()`. It is informational — re-`orient()` if you are relying on
cached cross-module structure; otherwise carry on.

For the MCP setup, ensure `openlore mcp` is configured as an MCP server.
See https://github.com/clay-good/OpenLore for details.
<!-- END OPENLORE -->

<!-- CODEGRAPH_START -->
## CodeGraph

In repositories indexed by CodeGraph (a `.codegraph/` directory exists at the repo root), reach for it BEFORE grep/find or reading files when you need to understand or locate code:

- **MCP tool** (when available): `codegraph_explore` answers most code questions in one call — the relevant symbols' verbatim source plus the call paths between them, including dynamic-dispatch hops grep can't follow. Name a file or symbol in the query to read its current line-numbered source. If it's listed but deferred, load it by name via tool search.
- **Shell** (always works): `codegraph explore "<symbol names or question>"` prints the same output.

If there is no `.codegraph/` directory, skip CodeGraph entirely — indexing is the user's decision.
<!-- CODEGRAPH_END -->

<!-- graft:start -->
## Graft — repo context graph

This repo is indexed in `graft/`: small linked markdown nodes that explain each
system and carry exact file:line spans, kept in sync with the code through git.

For ANY task here — understanding how something works, finding where code lives,
or scoping a change — get context from the graph before grepping or opening
source files. Re-ask freely (it's cheap) and reuse literal identifiers you
already have (symbol, error string, file name) as the query. New to this repo?
Run `graft map` first — a token-budgeted orientation (dir clusters, hubs,
hotspots), no LLM, no key.

- Run `graft ask "<your question>" --source` → ranked nodes with the relevant
  code spans inlined (each hit's ≤8-line crux by default; `--full` for whole
  definitions when the crux isn't enough). Match the tool to the task shape:
  for understanding or editing, the top node IS the answer — cite its
  `covers:` file:line spans and edit straight from `--source`. For
  exhaustive tasks ("every occurrence / every caller of this pattern"), ranked
  results are top-N, not complete — run `graft grep "<literal>"` instead
  (exhaustive over indexed files, grouped by enclosing symbol), falling back
  to raw `grep -rn` only for unindexed files.
- `graft skeleton <file>` → every definition's signature + span, ~10× cheaper
  than reading the file; use it to skim an API surface.
- `graft callers <symbol>` gives precomputed, exact edges — who calls this.
  Add `--direction out` for what it calls, or `--depth N` to walk
  transitively for the full blast radius. For structural questions, skip
  ranking and use this directly.
- Or browse: `graft/INDEX.md` lists every node; follow the links.
- Monorepos and folders of multiple repos rank fairly across sub-projects —
  hits carry `[scope/]` labels naming which one they're from. Narrow with
  `graft ask "<task>" --in <scope>/` once you know where you're working.

If a returned span is truncated ("+N more lines"), open the file at that exact
range before finalizing. Only open source files when a node genuinely lacks a
needed detail, and then at the exact file:line the node points to — never
re-read whole files.

After big code changes, refresh the graph with `graft build` (deterministic,
no API key, $0).
<!-- graft:end -->


## Presets

A preset is a whole item written once: `resources/presets/<name>.yaml` (user ones in `<config>/presets/`, found first) holds `props:` (names with defaults, optional `type`/`min`/`max`/`doc`) and a `template:` that uses them as `$prop`. A board item says `preset: name`, `props: {...}` and any fields it changes, which merge over the template (mappings merge, lists replace). `lib/presets.py` is Qt-free, like `lib/variables.py`: `expand` runs in `CentralPanel._load` before `resolveVariables`, so `$name` resolves item props, preset defaults, `vars:`, theme. A bad use becomes an error tile (`type: preset-error`, raised in `utils._loadItemGroup`). On save, `collapse` writes `preset`, the file's `props` and only the fields that differ from `CentralPanel._loaded`, the app's own dump taken right after loading (the raw expansion is not a usable baseline, because a dump adds keys). `preset:` on a stack whose value is not a preset file is still `Stack.preset`. A property that is `null` and used as a whole value, a key or a list item leaves that entry out (`_apply`), so an optional setting costs nothing; a property can name a series (`$key: {...}`). Shipped library: `stat-row`, `reading-list`, `list-panel`, `callout`, `headline-panel`, `meter-card`, `room-card`, `compass`, `ring`, `sparkline`, `day-column`, `zone-dial`, `readout-bar`, `hero-readings`; the `station`, `storm`, `sky` and `week` design boards use them, and `tests/test_preset_library.py` expands every shipped preset and board. Docs: `docs/config/dashboard/presets.md`. Known: until PR #66, a gauge saved as `type: realtime` (an error tile on reload) and wrote a derived `center_offset`, with or without presets.

## Themes

A dashboard picks one colour theme and writes `$tokens` instead of raw values. `lib/ui/colors/theme.py` (Qt-free) holds the engine; themes are YAML in `resources/themes/` (user ones in `<config>/themes/`, found first). `default.yaml` is the original white-on-black look, so a dashboard without `theme:` renders pixel-identical to before.

- **Select**: a root mapping, `theme: dusk` or inline `theme: {extends: dusk, colors: {solar: '#ffd400'}}`, with the board under `items:` (a root list has no room for it). `render_dashboard.py --theme NAME` forces one over the file. Applied in `CentralPanel._load` before any item decodes; switching needs a reload (`Ctrl+R`).
- **Write**: `color: $accent`, `font: $mono`, `gradient: $temperature`. One token namespace across three groups in the theme file: `colors`, `fonts`, `scales` (named gradients; unit-pinned stops work inside them). A raw value on an item always wins; a missing token comes from `extends` (default: `default`); an unknown token is a `ThemeError` that names the known ones.
- **Standard tokens** every theme defines: colours `background surface text muted faint rule accent good warn bad info series-1..6`; fonts `display mono body`; scales `load temperature`. A theme may add more (per-source colours like `$solar`).
- **Existing presets**: the named gradients dashboards already use (`TemperatureGradient`, `UVIndexGradient`, `WindSpeedGradient`, …) and the web colour names are untouched. `$temperature` is `TemperatureGradient` in the default theme, and a theme recolours any preset by listing its name under `scales`.
- **Modifiers**: `{color: $accent, alpha: 0.4 | lighten: 0.1 | darken | chroma: 0.8 | hue-shift: 30 | mix: {with: $background, by: 0.3}}`; lightness, chroma and hue work in Oklch, mixing in Oklab. A token can be built from another one inside a theme file.
- **A `Color` from a token keeps the name** (`str()` gives `$accent`), so saving writes the token back. `Color.role('text')` is a shared live colour retargeted in place when the theme changes; `Color.text`/`Color.default`, Text, dividers, the Graph line and the view background use it. Use it for class-level defaults; never hard-code `#ffffff` for "the text colour".
- **Qt palette**: the theme also fills the dashboard's `QPalette` (`applyThemeToPalette`: background, text, surface, faint, rule, accent), set on the dashboard viewport only. The QApplication and window chrome keep the system palette.
- Beam `theme: auto` (the default) follows the theme's `mode`. Not themed yet: the needle's dark glow, the moon, any colour still literal in code.
