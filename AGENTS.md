# AGENTS.md — LevityDash Schema

Schema subsystem of LevityDash — plugin data ingestion, transformation, mapping, unit conversion, and validation. The `Schema` class (`lib/plugins/schema/__init__.py`) is the core: it parses raw API/ingested data into structured `LevityDatagram` objects using source-key maps, property setters, and typed unit metadata.

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
  - `lib/backend.py` — async event loop + thread pool for headless operation
  - `lib/ui/Groups.py` — SizeGroup layout system
  - `__init__.py` — `LevityDashboard` singleton (immutable after init via `__slots__` / `__setattr__`)
  - `__main__.py` — entrypoint (`main()`)
- `docs/` — Sphinx docs site
- `build-to-app/` — PyInstaller build script + per-platform specs

## Schema engine overview

- **`Schema`** (`lib/plugins/schema/__init__.py:606`): per-plugin registry mapping source keys to `UnitMetaData` (unit type, validation rules, source-key aliases, data-maps). Registered in `Schema.__schemas__` for cross-plugin lookup.
- **`LevityDatagram`** (`lib/plugins/schema/__init__.py:47`): dict subclass that parses raw data through the schema — key mapping, variable substitution, array expansion into `Subdatagram` lists, auto-validation.
- **`unitDict`** (`lib/plugins/schema/units.py`): maps ~50 unit codes to `WeatherUnits` types (`wu.temperature.Fahrenheit`, `wu.pressure.Hectopascal`, etc.). Drives automatic conversion and display formatting.
- **Schema config**: each plugin's YAML schema declares `sourceKey`, `dataMaps`, `keyMaps`, `properties`, `metaData`, and `ignored` keys.

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
