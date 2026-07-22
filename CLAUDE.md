# LevityDash — developer notes

A desktop-native, multi-source weather dashboard. Qt (PySide6) QGraphicsScene frontend; plugin-driven data layer. Beta, used daily. Direction lives in [docs/roadmap.md](docs/roadmap.md). [AGENTS.md](AGENTS.md) covers the same repo for other AI agents (OpenCode/DeepSeek) — the two should stay roughly in sync.

## Layout

```
src/
  qolkit/      generic Python QOL utilities (sentinels, DotDict, DeepChainMap,
               OrderedSet, descriptors) — zero domain/Qt coupling
  statekit/    declarative state + YAML persistence (StateProperty, Stateful,
               loaders/dumpers, ActionPool) — Qt-free, depends only on qolkit
  LevityDash/  the app
    lib/stateful.py            Qt facade over statekit — consumers import from
                               HERE, never from statekit directly
    lib/plugins/               data layer: plugins, observations, schemas,
                               dispatcher ({key → MultiSourceContainer})
    lib/plugins/builtin/       OpenMeteo, PirateWeather, WeatherFlow, Govee (BLE),
                               OpenWeatherMap (experimental)
    lib/wire/                  backend/frontend split wire protocol (in progress)
    lib/ui/frontends/PySide/   the Qt frontend (app.py, Modules/Displays/…)
    lib/ui/Groups.py           size-group text-fitting engine (stateless refit)
```

Dependency direction is strict: `qolkit ← statekit ← LevityDash`. Never import Qt or LevityDash from statekit/qolkit.

## Environment

- Poetry; Python `>=3.11,<3.15` (developed and run on 3.14).
- The `dev` dependency group path-depends on a sibling checkout `../WeatherUnits` (develop mode). Without it, `poetry install --without dev`.
- After dependency churn, the editable install can come unlinked — fix with `poetry run pip install -e . --no-deps`.
- Keep `pyside6` at its pinned floor; loose upgrades have pulled broken Qt builds before.

## Run / test

```bash
poetry run LevityDash                 # or: poetry run python -m LevityDash
poetry run pytest                     # offscreen Qt is configured in pyproject
LEVITYDASH_CONFIG_DEBUG=1 poetry run python -m LevityDash   # pristine temp config
```

- `LEVITYDASH_CONFIG_DEBUG=1` creates a throwaway config and triggers onboarding — use it for fresh-install behavior, NOT for testing against real dashboards/plugins (run without it; real config is in the platform config dir, e.g. `~/Library/Application Support/LevityDash` on macOS).
- `tests/qolkit` and `tests/statekit` are pure Python; `tests/ui` boots a headless dashboard via `tests/conftest.py`.

## Gotchas

- **macOS Bluetooth/TCC**: with the Govee plugin enabled, launching from a terminal that lacks Bluetooth permission aborts the process (SIGABRT) at startup. Not a code bug.
- **Cross-thread timers**: never call `QTimer.start()` from a non-owner thread — it silently does nothing. Use `startTimerSafe`/`stopTimerSafe` from `lib/utils/shared.py` in any data-callback path.
- **Off-thread painting**: workers may paint `QImage` only; all scene-graph reads must be resolved to plain values on the GUI thread before handing work to a `Worker` (see `Graph.py` `render()` for the pattern).
- **StateProperty encoders**: anything reaching the YAML dumper must be a plain type; leaked objects (e.g. `DeepChainMap`, measurement objects) get silently `repr()`'d into the save file and corrupt it. Flatten in `.encode`.
- **Keys**: `CategoryItem` is a tuple subclass with an optional `source`; string form round-trips via `str()`/constructor. The dispatcher reconciles multiple sources per anonymous key via `MultiSourceContainer`.

## Conventions

- Tabs for indentation in Python (existing style).
- Commit messages: `type(Scope): summary`, e.g. `fix(UI.Graph): …`, `feat(Stateful): …`.
- `.levity` dashboard files are YAML; example config/templates under `src/LevityDash/resources/example-config/`.
- **Task handoffs live in `docs/tasks/`** — self-contained briefs (context, expected change, verification, suggested branch/worktree) for work meant to be picked up in a fresh session or by another agent. If working from one of these, sync your branch with `dev` first (`git merge dev`) since new briefs and unrelated fixes land there continuously.
