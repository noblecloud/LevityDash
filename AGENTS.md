# AGENTS.md — LevityDash Schema

Schema subsystem of LevityDash — plugin data ingestion, transformation, mapping, unit conversion, and validation. The `Schema` class (`lib/plugins/schema/__init__.py`) is the core: it parses raw API/ingested data into structured `LevityDatagram` objects using source-key maps, property setters, and typed unit metadata.

> Repo-wide developer notes (package layout, dependency rules, environment gotchas) live in [CLAUDE.md](CLAUDE.md); this file focuses on the schema engine.

## Before you start a task

- **Task briefs live in `docs/tasks/`.** Each file there is a self-contained brief for one piece of work (bug fix, cleanup, investigation) with context, the concrete change expected, verification steps, and a suggested branch name. If you were pointed at this repo for a specific task, check there first — the human maintainer uses this directory to hand off work.
- **Two integration branches exist, with different rules — know which one applies to you:**
  - **`dev`** — the human maintainer's primary branch. Never target this directly unless explicitly told to. It only receives *reviewed, deliberate* merges from `deepseek-dev` (see below) or from the maintainer's own local worktrees.
  - **`deepseek-dev`** — a staging/integration branch that exists specifically so DeepSeek/OpenCode work can land and accumulate without needing a human review on every single small PR. If you're working from a persistent clone with `origin` push access (check `git remote -v` and `gh auth status`), **this is your target, not `dev`.**
- **Sync before you branch:**
  - **Persistent clone with `origin` access (the normal case for DeepSeek/OpenCode):** `git fetch origin && git checkout deepseek-dev && git merge origin/deepseek-dev` (or `git pull origin deepseek-dev`).
  - **Local worktree sharing another checkout's `.git`, no separate remote** (the maintainer's own quick local tasks): `git merge dev` from inside the worktree — this case still targets `dev` directly, see below.
  - Either way: "Already up to date," a fast-forward, or a clean merge means you're good. A conflict means stop and flag it rather than resolving blindly — someone else's in-flight work likely overlaps with yours.
- **Work on your own branch, off the branch you synced above.** Never commit directly to `dev`, `deepseek-dev`, or `main`. Each task brief includes a suggested branch name.
- **When you're done:**
  - **From a persistent clone (targeting `deepseek-dev`):** push your branch and open a PR against `deepseek-dev` — `git push origin <branch-name>`, then `gh pr create --base deepseek-dev --head <branch-name> --title "..." --body "..."`. You **may merge your own PR into `deepseek-dev`** once its own verification steps pass (tests green, no scope creep) — `deepseek-dev` is a staging area, not the maintainer's real line, so this is fine. **Never merge anything into `dev` or `main` yourself, under any circumstances** — that promotion is a deliberate, human-reviewed step the maintainer (or Claude, when asked) performs periodically by reviewing the accumulated `deepseek-dev` diff.
  - **From a local worktree with nothing to push to:** leave the branch committed for the maintainer to review and merge into `dev` locally, as before.
- **Stay inside the task's stated scope.** Several task briefs explicitly call out what NOT to touch (usually because that code is tracked separately, or because it's mid-refactor elsewhere). Respect those boundaries even if you notice something else that looks wrong nearby — flag it instead of fixing it.

## Commands

```sh
poetry install                          # install deps (has local dev dep: ../WeatherUnits)
poetry run LevityDash                   # run desktop app
poetry run pytest                       # run all tests
poetry run pytest -xvs tests/ui/test_smoke.py
poetry run pytest -m unwired            # xfail-marked (unimplemented) tests
```

## Project structure

- `src/LevityDash/` — package root (imported as `LevityDash`)
  - `lib/plugins/schema/` — **schema engine** (`Schema`, `LevityDatagram`, `Subdatagram`, `Properties`, `MetaData`)
  - `lib/plugins/schema/units.py` — unit definition dictionary (`unitDict`) mapping short codes (e.g. `"f"`, `"hPa"`, `"AQI"`) to WeatherUnits types
  - `lib/plugins/plugin.py` — base `Plugin` class (each plugin declares a `Schema` for its data)
  - `lib/plugins/builtin/` — built-in plugins: Open-Meteo, WeatherFlow, Govee BLE, PirateWeather, OpenWeatherMap
  - `lib/config.py` — `ConfigParser` with `ExtendedInterpolation` (schema config per plugin)
  - `lib/backend.py` — UNWIRED scaffold for the headless backend (nothing imports it; being rebuilt as part of the backend/frontend process split — see docs/roadmap.md)
  - `lib/ui/Groups.py` — SizeGroup layout system
  - `__init__.py` — `LevityDashboard` singleton (immutable after init via `__slots__` / `__setattr__`)
  - `__main__.py` — entrypoint (`main()`)
- `docs/` — docsify docs site (the Sphinx skeleton under `docs/source/` is vestigial)
- `build-to-app/` — PyInstaller build script + per-platform specs

## Schema engine overview

- **`Schema`** (`lib/plugins/schema/__init__.py:606`): per-plugin registry mapping source keys to `UnitMetaData` (unit type, validation rules, source-key aliases, data-maps). Registered in `Schema.__schemas__` for cross-plugin lookup.
- **`LevityDatagram`** (`lib/plugins/schema/__init__.py:47`): dict subclass that parses raw data through the schema — key mapping, variable substitution, array expansion into `Subdatagram` lists, auto-validation.
- **`unitDict`** (`lib/plugins/schema/units.py`): maps ~50 unit codes to `WeatherUnits` types (`wu.temperature.Fahrenheit`, `wu.pressure.Hectopascal`, etc.). Drives automatic conversion and display formatting.
- **Schema config**: each plugin declares its schema as a Python dict in its own module (e.g. `builtin/OpenMeteo.py` `schema = {...}`) with `sourceKey`, `dataMaps`, `keyMaps`, `properties`, `metaData`, and `ignored` keys — not YAML.

## Test quirks

- **`conftest.py`** sets `QT_QPA_PLATFORM=offscreen` and `LEVITYDASH_CONFIG_DEBUG=1` **before any PySide6 import** (top-level, not in a fixture).
- Session-scoped `dashboard` fixture boots a real Qt app headlessly without entering `exec_()`. Plugins loaded, never started.
- `frozen_time` fixture freezes `shared.now`, `strftime`, `datetime.now` to `2025-06-18 14:30`.
- `pump(app, seconds)` helper processes Qt events without `exec_()`.
- `unwired` marker = xfail (behaviour not yet implemented).

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
