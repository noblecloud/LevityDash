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
poetry run LevityDash                   # run desktop app
poetry run pytest                       # run all tests
poetry run pytest -xvs tests/ui/test_smoke.py
poetry run pytest -m unwired            # xfail-marked (unimplemented) tests
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
    lib/wire/                  backend/frontend split wire protocol (in progress)
    lib/ui/frontends/PySide/   the Qt frontend (app.py, Modules/Displays/…)
    lib/config.py              ConfigParser with ExtendedInterpolation
    lib/backend.py             UNWIRED scaffold for the headless backend (nothing
                               imports it yet; being rebuilt — see docs/roadmap.md)
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

## Test quirks

- **`conftest.py`** sets `QT_QPA_PLATFORM=offscreen` and `LEVITYDASH_CONFIG_DEBUG=1` **before any PySide6 import** (top-level, not in a fixture).
- Session-scoped `dashboard` fixture boots a real Qt app headlessly without entering `exec_()`. Plugins loaded, never started.
- `frozen_time` fixture freezes `shared.now`, `strftime`, `datetime.now`, and the Moon module's `datetime.now(tz)` (patched separately — it reads the module directly) to `2025-06-18 14:30`.
- `pump(app, seconds)` helper processes Qt events without `exec_()`.
- `unwired` marker = xfail (behaviour not yet implemented).
- Plugin tests exercise `normalizeData`/schema as unbound logic against captured, sanitized real API responses as golden fixtures — no network, no full `Plugin` bootstrap needed (see `tests/plugins/test_openweathermap.py` for the pattern).

## Style & config

- **Indentation**: tabs (2-width) for `.py`, spaces for `.yaml`/`.spec` (`.editorconfig`).
- **Max line length**: 240.
- **Python**: 3.11–3.14.
- **Config**: `ConfigParser` with `ExtendedInterpolation`; `LEVITYDASH_CONFIG_DEBUG=1` redirects paths to temp dirs.
- **Logging**: Custom verbosity levels (0–5), Rich console + rotating file handler. Traceback locals off by default (live Qt objects crash on concurrent repr).

## Notable quirks

- **`cached_property` lock**: Python <3.12 gets an unlocked backport (`__init__.py:20`) to prevent Qt signal deadlocks.
- **`LEVITY_BUILDING=TRUE`**: bypasses compile-time checks during PyInstaller build.
- **PyInstaller**: per-platform specs at `build-to-app/specs/{macOS,windows,linux}.spec`.
