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
    lib/wire/                  backend/frontend split wire protocol — codec, messages,
                               server/client transport, RemoteBackend/RemoteFrontend,
                               RemoteConnection, RemoteContainer stand-ins, LoopbackBridge
    lib/backend.py             headless backend process; entry point is the sibling
                               backend.py (pins mode=live before any lib import)
    lib/ui/frontends/PySide/   the Qt frontend (app.py, Modules/Displays/…)
    lib/ui/Groups.py           size-group text-fitting engine (stateless refit)
    devtools/                  dev-only tooling, never imported by the shipped app
                               (backend_watch.py — auto-restart-on-change watcher;
                                ble_scan.py — BLE scan / "can this host do Bluetooth?";
                                _boot.py — offscreen dashboard boot + scene rendering;
                                render_dashboard.py / render_widget.py — one-shot renders;
                                render_service.py — warm render service over HTTP)
```

Dependency direction is strict: `qolkit ← statekit ← LevityDash`. Never import Qt or LevityDash from statekit/qolkit.

## Environment

- Poetry; Python `>=3.13,<3.15` (developed and run on 3.14).
- The `dev` dependency group path-depends on a sibling checkout `../WeatherUnits` (develop mode). Without it, `poetry install --without dev`.
- After dependency churn, the editable install can come unlinked — fix with `poetry run pip install -e . --no-deps`.
- Keep `pyside6` at its pinned floor; loose upgrades have pulled broken Qt builds before.

## Run / test

```bash
poetry run LevityDash                 # or: poetry run python -m LevityDash (mode=live by default)
poetry run LevityDash-backend         # standalone headless backend (WebSocket server)
poetry run LevityDash-backend-watch   # dev only: debounced restart-on-change, gated on pytest passing
poetry run pytest                     # offscreen Qt is configured in pyproject
LEVITYDASH_CONFIG_DEBUG=1 poetry run python -m LevityDash   # pristine temp config
```

- **`Ctrl+R` restarts** — in the frontend it replaces the *second* `Ctrl+C` (one `Ctrl+C` arms, then `Ctrl+R` restarts instead of quitting); under `LevityDash-backend-watch` a plain `Ctrl+R` bounces the backend immediately, deliberately skipping the test gate that the file-change path uses. Implemented in `src/qolkit/hotkeys.py` — cbreak, not raw, so `ISIG` stays on and `Ctrl+C` is unaffected; a no-op when stdin isn't a TTY.
- `LEVITYDASH_CONFIG_DEBUG=1` creates a throwaway config and triggers onboarding — use it for fresh-install behavior, NOT for testing against real dashboards/plugins (run without it; real config is in the platform config dir, e.g. `~/Library/Application Support/LevityDash` on macOS).
- `tests/qolkit` and `tests/statekit` are pure Python; `tests/ui` boots a headless dashboard via `tests/conftest.py`; `tests/wire` mostly uses hand-built stand-ins over real sockets rather than a full app bootstrap.
- Two-process manual check: `LevityDash-backend`, then `LevityDash` with `[Backend] mode = remote` in config (or `LEVITYDASH_BACKEND_MODE=remote` env). To screenshot a remote-mode run instead of eyeballing a window: boot via `LevityDashboard.init()`/`app.init_app()` (mirrors `tests/conftest.py`'s `dashboard` fixture, minus `exec_()`), pump events, then `view.grab().save(path)` — works under `QT_QPA_PLATFORM=offscreen` once `[QtOptions] openGL` is forced off (offscreen has no real GL context, so the default `QOpenGLWidget` viewport grabs as blank white).
- **Rendering a dashboard headlessly** (dev only): `render_dashboard.py` (whole board) and `render_widget.py` (one named item, `--list` to see names) each pay ~6s of Qt boot per render. **`render_service.py` holds a booted dashboard warm and serves renders over HTTP in ~85ms** — `GET /render` (`?w=&h=&scale=`), `GET /render/<name>` (`?scale=&pad=`), `GET /items`, `POST /reload` (re-reads the `.levity` without restarting Qt), plus `/health` and `/status`, on `127.0.0.1:8670` (`--host`/`--port`, or `LEVITYDASH_RENDER_HOST`/`_PORT`). Prefer it whenever you'll look more than once. All three use `QGraphicsScene.render()` rather than `view.grab()`, so there's no window and no GL context — but ⚠️ a *cold* render composites `QGraphicsEffect`s poorly (the moon's glow comes out flat), while the warm service renders them correctly, having had time to initialise. Layout, type, spacing and colour are faithful either way.
- **`LevityDash-backend-watch`** (dev only, `devtools/backend_watch.py`): watches `src/LevityDash`/`tests` for `.py` changes, debounces (default 2s, `--debounce-ms`), runs the full suite, and restarts the supervised backend only if it's green — a failing suite leaves the previous backend running and reports `tests_failing` instead. Serves a small standard status API on `http://127.0.0.1:8669` (`--host`/`--port`, or `LEVITYDASH_WATCH_STATUS_HOST`/`_PORT`): `GET /health` (plain 200/503, for any generic uptime tool or menu-bar widget) and `GET /status` (full JSON state). The frontend's own in-app connection indicator (top-right dot, mode=remote only) is independent of this tool — it reflects `RemoteConnection.connectionStateChanged` (`lib/wire/remote.py`) directly, so it's correct whether or not the backend happens to be running under the watcher.

## Gotchas

- **macOS Bluetooth/TCC**: with the Govee plugin enabled, the process dies with `SIGABRT` (exit 134) and **no output at all** at startup. Not a code bug, and *not* a missing permission grant — granting Bluetooth in System Settings does not fix it. macOS kills any process touching Bluetooth when the **responsible process's bundle** lacks `NSBluetoothAlwaysUsageDescription` in its `Info.plist`, and that check runs *before* the TCC grant is consulted. The crash report says `Termination Reason: Namespace TCC` and names the missing key. iTerm and PyCharm ship it; some hosts (including Claude Code's `claude-code` helper bundle) do not — so run BLE work from a terminal that has it. `devtools/ble_scan.py` is a dependency-free way to check whether a given host can do BLE at all. Never patch a signed app's `Info.plist` to work around this; it breaks the code signature.
- **Cross-thread timers**: never call `QTimer.start()` from a non-owner thread — it silently does nothing. Use `startTimerSafe`/`stopTimerSafe` from `lib/utils/shared.py` in any data-callback path.
- **Off-thread painting**: workers may paint `QImage` only; all scene-graph reads must be resolved to plain values on the GUI thread before handing work to a `Worker` (see `Graph.py` `render()` for the pattern).
- **StateProperty encoders**: anything reaching the YAML dumper must be a plain type; leaked objects (e.g. `DeepChainMap`, measurement objects) get silently `repr()`'d into the save file and corrupt it. Flatten in `.encode`.
- **Keys**: `CategoryItem` is a tuple subclass carrying two orthogonal extras — `source` (*who* provided it; reconciled across providers by `MultiSourceContainer`) and `identity` (*which* value it is — `…temperature#bedroom`; **never** merged). Identity participates in equality, hashing *and* the `__existing__` interning cache. ⚠️ Only the identity form round-trips through `str()`/constructor: `str()` renders a source as a `:`-prefix (`Govee:indoor.…`) that the constructor does **not** parse back, so sourced keys are not round-trip safe. Schema lookups are keyed by the *base* key, so identity must be stripped before any schema lookup (`getExact`, `getUnitMetaData`).

## Conventions

- Tabs for indentation in Python (existing style).
- Commit messages: `type(Scope): summary`, e.g. `fix(UI.Graph): …`, `feat(Stateful): …`.
- `.levity` dashboard files are YAML; example config/templates under `src/LevityDash/resources/example-config/`.
- **Task handoffs live in `docs/tasks/`** — self-contained briefs (context, expected change, verification, suggested branch/worktree) for work meant to be picked up in a fresh session or by another agent. If working from one of these, sync your branch with `dev` first (`git merge dev`) since new briefs and unrelated fixes land there continuously.
