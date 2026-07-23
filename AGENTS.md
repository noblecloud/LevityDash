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
poetry run pytest                       # run all tests
poetry run pytest -xvs tests/ui/test_smoke.py
poetry run pytest -m unwired            # xfail-marked (unimplemented) tests
poetry run pytest tests/wire/           # wire-protocol tests (codec, transport, containers)
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
  requirement, not an optimization (see `docs/roadmap.md`).
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
