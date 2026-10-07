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
                               (supervisor.py — runs backend+frontend together and
                                keeps them up, for a deployed display;
                                backend_watch.py — auto-restart-on-change watcher;
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
- **Plain logging (rich off)**: `LEVITY_LOG_PLAIN=1` in the environment, or `[Logging] plain = 1` in the config (the env var wins), swaps the rich console and file handlers for the standard library's — no markup parsing, no rich tracebacks, one line per record. Use it when rich's formatting is in the way: piping output to a tool, a log you want to grep line by line, or a traceback you want unwrapped. `LEVITY_LOG_SHOW_LOCALS=1` (or `[Logging] tracebackLocals = 1`) is the opposite switch and only applies with rich on. Both are read in `lib/log.py` `_LevityLogger.install`.
- `tests/qolkit` and `tests/statekit` are pure Python; `tests/ui` boots a headless dashboard via `tests/conftest.py`; `tests/wire` mostly uses hand-built stand-ins over real sockets rather than a full app bootstrap.
- Two-process manual check: `LevityDash-backend`, then `LevityDash` with `[Backend] mode = remote` in config (or `LEVITYDASH_BACKEND_MODE=remote` env). To screenshot a remote-mode run instead of eyeballing a window: boot via `LevityDashboard.init()`/`app.init_app()` (mirrors `tests/conftest.py`'s `dashboard` fixture, minus `exec_()`), pump events, then `view.grab().save(path)` — works under `QT_QPA_PLATFORM=offscreen` once `[QtOptions] openGL` is forced off (offscreen has no real GL context, so the default `QOpenGLWidget` viewport grabs as blank white).
- **Rendering a dashboard headlessly** (dev only): `render_dashboard.py` (whole board) and `render_widget.py` (one named item, `--list` to see names) each pay ~6s of Qt boot per render. **`render_service.py` holds a booted dashboard warm and serves renders over HTTP in ~85ms** — `GET /render` (`?w=&h=&scale=&dpi=`), `GET /render/<name>` (`?scale=&pad=`), `GET /render/at/<path>` (by structural position; `0/1/main` and `[0][1][main]` both parse, and `curl` needs `-g` for the bracket form), `GET /tree` (`?depth=`, the structure with indices — `/items` only sees things carrying a `name:`), `GET /items`, `POST /reload`, `POST /load` (`{"path": …}`, switch dashboards without restarting Qt), `POST /preview` (a `.levity` document in, a PNG out — **experimental**, renders real content but does not reliably finish settling), plus `/health` and `/status`, on `127.0.0.1:8670` (`--host`/`--port`, or `LEVITYDASH_RENDER_HOST`/`_PORT`). `?w=`/`?h=` take the same vocabulary as a `.levity`: pixels, relative (`50%`), or physical (`12in`, needing `?dpi=` since a headless process has no screen). Prefer the service whenever you'll look more than once. All three use `QGraphicsScene.render()` rather than `view.grab()`, so there's no window and no GL context — but ⚠️ a *cold* render composites `QGraphicsEffect`s poorly (the moon's glow comes out flat), while the warm service renders them correctly, having had time to initialise. Layout, type, spacing and colour are faithful either way.
- **`--seed <dir>` on the render devtools** copies *from* `<dir>` **into** a disposable temp config (`LEVITYDASH_CONFIG_DEBUG=1` for the temp dirs, `LEVITYDASH_CONFIG_SEED` for the source) — `<dir>` is a source to read, never written to, so a render can't touch whatever it points at. That means `<dir>` **can safely be your real config dir** (`~/Library/Application Support/LevityDash`) directly — no manual copy needed, and you keep onboarding, plugins, and existing dashboards for free instead of hitting the fresh-install flow. Point it at a copy instead only when you specifically want to edit-and-render a *candidate* file without that edit ever reaching a real dashboard. ⚠️ Both variables are read **in a class body at import time** (`LevityDash/__init__.py`), and `from LevityDash.devtools…` imports the parent package — so they must be set *before* the first LevityDash import, which is what `devtools/_seed.py` exists for. Setting them inside `boot()` is too late and fails **silently**: until 2026-08-03 `--seed` was a complete no-op and every "rendered against a copy" run was really reading and writing the live config. Same ordering rule as `QT_QPA_PLATFORM`. `tests/conftest.py` was never affected — it sets both at module import.
- **`design_mode.py`** (dev only, `devtools/design_mode.py`) and **`watch_render.py`**: rapid-prototype *one panel/fragment* rather than a whole dashboard — see `docs/design-references/` for example fragments. `design_mode.py` opens a real interactive window over one `.levity` fragment and reloads it whenever the file changes on disk, via the same `CentralPanel.reload()` that `Ctrl+R` uses (`--full-reload` wipes and rebuilds instead, for when you're restructuring rather than tweaking values). `watch_render.py` is the PNG-based equivalent for a running `render_service.py` — polls a fragment's mtime and re-renders to a fixed path; open that PNG in **Preview.app**, not Quick Look, since Preview reloads automatically on external change.
- **`gauge_studio.py`** (dev only, `devtools/gauge_studio.py`): design *one gauge* live, with controls — modelled on gauge-ui's Studio. `poetry run python src/LevityDash/devtools/gauge_studio.py [fragment.levity]`. Preview on the left, controls on the right, on **made-up data**: it draws the real `Gauge` on its own `QGraphicsScene` and feeds it a value source the studio owns (`_studio_stage.py`), so it starts no dashboard, plugin, backend or Fixture and reads no user config. The controls come from `StateProperty` introspection (`_studio_schema.py`), so a property added to `Gauge.py` appears with no edit here; a value the gauge rejects shows its reason under the control. Value slider or an animated sweep; data presets (temperature °F, humidity, pressure inHg, wind mph, rain in/hr, generic 0-100); a Templates menu over `docs/design-references/presets/*.levity` and the `gauge-showcase.levity` cells; *Copy code* / *Save as…* write the `.levity` YAML with only the properties that differ from the defaults. With a fragment path it reloads whenever the file changes. ⚠️ Not a `pyproject` entry point on purpose: an entry point imports the `LevityDash` package first, which builds the config at import time; the script instead points every LevityDash directory at a temp dir (`_studio_env.py`) before that import. Drive it offscreen with `QT_QPA_PLATFORM=offscreen`, change a control in code, pump events and `grab()` the window. **Direct manipulation** (`_studio_handles.py`): handles overlay the preview for arc start/end angle, radius, arc weight, needle tip (sets the preview value), numeric marker, zone-edge and fill-end values, value/unit/caption/sub-label text boxes, and four corner squares that set `anchor`; shift or the Snap box sets the step (shift = fine); edits are live in place while dragging and rebuild on release. Text boxes write a new opt-in `offset: {x, y}` (shares of the dial diameter) on `GaugeLabel`/`GaugeCaption`. Undo/redo (`Cmd+Z`/`Shift+Cmd+Z`) covers every edit. **Gradient stops** can be pinned to a unit (`arc.gradient: {32°F: '#4aa3ff', 99°F: '#ff4a4a'}`, or a list of `{at: 37°C, color: …}`); `colors/stopunits.py` parses and converts them, `Gradient.resolve(valueClass)` converts each stop to the data unit (a stop that does not fit logs once and is skipped). In the Studio the gradient row has a collapsible colour band and, with *Edit gradient* on, draggable nodes on the band and on the meter (`_studio_stops.py`, `_studio_handles.py`). Structured editors (`_studio_editors.py`) replace free text for fill, caption, zones, markers, gradient, tick text maps, sizes, colours, formats, int sets and enums. ⚠️ Qt rule learned here: never delete or rebuild a scene item inside its own mouse event, and keep Python references to scene items alive; the handle layer pools its items and defers rebuilds with a 0 ms timer.
- **`LevityDash-run`** (`devtools/supervisor.py`): the *deployed* counterpart to `backend-watch` — runs the backend **and** the frontend in one supervised process and keeps both up. Restarts a child that dies (crash, OOM, someone closing the window) with backoff for crash loops, and restarts both when `src/LevityDash` changes. **No test gate**, deliberately: whatever is deployed was tested before it was pushed, and a room display that refuses a fix because of an unrelated failing test is worse than one that picks it up. Reads `[Backend] mode` from the real config without importing Qt — in `mode=remote` the backend starts first and the frontend waits for its port to accept (otherwise the frontend sits in reconnect and the display looks broken); in `mode=live` no separate backend starts at all, since the frontend runs the plugins itself and two would double every plugin. `GET /health` (200 only when *every* child is up — a dead frontend is a blank display) and `GET /status` on `127.0.0.1:8668` (`--host`/`--port`, or `LEVITYDASH_SUPERVISOR_HOST`/`_PORT`); `--no-backend`/`--no-frontend` to supervise one; `Ctrl+R` restarts both now. ⚠️ The frontend is a GUI process and inherits this process's GUI session, so **launch it from a terminal on the machine with the display** (or a LaunchAgent) — started over plain SSH it supervises a frontend that can never open a window.
- **`LevityDash-backend-watch`** (dev only, `devtools/backend_watch.py`): watches `src/LevityDash`/`tests` for `.py` changes, debounces (default 2s, `--debounce-ms`), runs the full suite, and restarts the supervised backend only if it's green — a failing suite leaves the previous backend running and reports `tests_failing` instead. Serves a small standard status API on `http://127.0.0.1:8669` (`--host`/`--port`, or `LEVITYDASH_WATCH_STATUS_HOST`/`_PORT`): `GET /health` (plain 200/503, for any generic uptime tool or menu-bar widget) and `GET /status` (full JSON state). The frontend's own in-app connection indicator (top-right dot, mode=remote only) is independent of this tool — it reflects `RemoteConnection.connectionStateChanged` (`lib/wire/remote.py`) directly, so it's correct whether or not the backend happens to be running under the watcher.

## Bars

`type: realtime.bar` is a `Meter` on a straight `LineTrack` (`Displays/meter/bar.py`): progress, battery (`style: battery`), segmented (`fill: {segments: N}`) and thermometer (`style: thermometer`). A bar paints track, zones, fill, ticks, markers, pointer and text in one canvas item; it shares `Meter` (value, range, `Scale`) with `Gauge` but not the arc items. It reports `DisplayType.Gauge`, so a panel's value feed drives it unchanged; `Realtime` creates it from `DisplayType.Bar`, because `realtime.bar` alone would fuzzy-match the bar *plot*. Options: `docs/config/dashboard/bar.md`. Fragments, a showcase board and the `bar-cards` scenario: `docs/design-references/bars/`. Studio does not edit bars yet.

## The second machine (`lambda`)

`lambda` (in `~/.ssh/config`; Intel Mac) runs the same dashboard on a room
display, with the same layout — `~/Code/{LevityDash,WeatherUnits}` and
`~/Library/Application Support/LevityDash`.

Both **were** kept in sync by PyCharm rsync, which left them with no `.git` and no
way to tell what revision they were on — a partial sync is invisible. Both are now
real git checkouts on `dev`, updated by pushing to them over SSH (no GitHub round
trip). Each repo has its own `lambda` remote:

```bash
git push lambda dev      # from LevityDash  -> lambda:Code/LevityDash
git push lambda dev      # from WeatherUnits -> lambda:Code/WeatherUnits
```

`receive.denyCurrentBranch=updateInstead` is set in both, so a push updates the
working tree directly — but **only if that tree is clean**; a push onto a dirty
tree is refused. Turn PyCharm's auto-upload off for both projects, or it will
fight the checkouts.

Note LevityDash's `dev` group path-depends on `../WeatherUnits` in develop mode
there as well, so pushing WeatherUnits changes what LevityDash resolves on that
box — push both when they move together.

`poetry` isn't on `PATH` for non-interactive SSH there; use `.venv/bin/python -m
pytest` (or `.venv/bin/LevityDash`). Two size-group tests currently fail on that
box and pass on ARM — see [docs/tasks/lambda-sizegroup-test-failures.md](docs/tasks/lambda-sizegroup-test-failures.md).

## Presets

A preset is a whole item written once: `resources/presets/<name>.yaml` (user ones in `<config>/presets/`, found first) holds `props:` (names with defaults, optional `type`/`min`/`max`/`doc`) and a `template:` that uses them as `$prop`. A board item says `preset: name`, `props: {...}` and any fields it changes, which merge over the template (mappings merge, lists replace). `lib/presets.py` is Qt-free, like `lib/variables.py`: `expand` runs in `CentralPanel._load` before `resolveVariables`, so `$name` resolves item props, preset defaults, `vars:`, theme. A bad use becomes an error tile (`type: preset-error`, raised in `utils._loadItemGroup`). On save, `collapse` writes `preset`, the file's `props` and only the fields that differ from `CentralPanel._loaded`, the app's own dump taken right after loading (the raw expansion is not a usable baseline, because a dump adds keys). `preset:` on a stack whose value is not a preset file is still `Stack.preset`. A property that is `null` and used as a whole value, a key or a list item leaves that entry out (`_apply`), so an optional setting costs nothing; a property can name a series (`$key: {...}`). Shipped library: `stat-row`, `reading-list`, `list-panel`, `callout`, `headline-panel`, `meter-card`, `room-card`, `compass`, `ring`, `sparkline`, `day-column`, `zone-dial`, `readout-bar`, `hero-readings`; the `station`, `storm`, `sky` and `week` design boards use them, and `tests/test_preset_library.py` expands every shipped preset and board. Docs: `docs/config/dashboard/presets.md`. Known: until PR #66, a gauge saved as `type: realtime` (an error tile on reload) and wrote a derived `center_offset`, with or without presets.

## Themes

A dashboard picks one colour theme and writes `$tokens` instead of raw values. `lib/ui/colors/theme.py` (Qt-free) holds the engine; themes are YAML in `resources/themes/` (user ones in `<config>/themes/`, found first). `default.yaml` is the original white-on-black look, so a dashboard without `theme:` renders pixel-identical to before.

- **Select**: a root mapping, `theme: dusk` or inline `theme: {extends: dusk, colors: {solar: '#ffd400'}}`, with the board under `items:` (a root list has no room for it). `render_dashboard.py --theme NAME` forces one over the file. Applied in `CentralPanel._load` before any item decodes; switching needs a reload (`Ctrl+R`).
- **Write**: `color: $accent`, `font: $mono`, `gradient: $temperature`. One token namespace across three groups in the theme file: `colors`, `fonts`, `scales` (named gradients; unit-pinned stops work inside them). A raw value on an item always wins; a missing token comes from `extends` (default: `default`); an unknown token is a `ThemeError` that names the known ones.
- **Standard tokens** every theme defines: colours `background surface text muted faint rule accent good warn bad info series-1..6 needle-glow moon moon-shade moon-glow`; fonts `display mono body`; scales `load temperature`. A theme may add more (per-source colours like `$solar`).
- **Existing presets**: the named gradients dashboards already use (`TemperatureGradient`, `UVIndexGradient`, `WindSpeedGradient`, …) and the web colour names are untouched. `$temperature` is `TemperatureGradient` in the default theme, and a theme recolours any preset by listing its name under `scales`.
- **Modifiers**: `{color: $accent, alpha: 0.4 | lighten: 0.1 | darken | chroma: 0.8 | hue-shift: 30 | mix: {with: $background, by: 0.3}}`; lightness, chroma and hue work in Oklch, mixing in Oklab. A token can be built from another one inside a theme file.
- **A `Color` from a token keeps the name** (`str()` gives `$accent`), so saving writes the token back. `Color.role('text')` is a shared live colour retargeted in place when the theme changes; `Color.text`/`Color.default`, Text, dividers, the Graph line and the view background use it. Use it for class-level defaults; never hard-code `#ffffff` for "the text colour".
- **Qt palette**: the theme also fills the dashboard's `QPalette` (`applyThemeToPalette`: background, text, surface, faint, rule, accent), set on the dashboard viewport only. The QApplication and window chrome keep the system palette.
- **Background**: the board's ground is the theme's `background` colour unless the root says `background:`: a colour, `$background`, a scale token such as `$sky` (a gradient), a gradient written in place, or `{gradient: $sky, angle: 160}` (CSS degrees, default 180 = top to bottom). A theme can also define a `backdrop` scale to give every board without its own `background:` a gradient. `lib/ui/colors/backdrop.py` resolves it; `LevityScene.drawBackground` paints it, so view and render tools agree. `sky` is a standard scale (flat in `default`).
- **Picker**: the `Dashboard > Theme` menu (`Modules/ThemeMenu.py`) forces a theme for this run with `theme.set_override` and reloads the board (items read `$tokens` once); "Dashboard's own" lifts it. It never writes the dashboard file. Gauge Studio has a theme combo (`devtools/_studio_themes.py`) that does the same and rebuilds the gauge from its saved form; the Studio's Light/Dark button only styles the controls.
- Beam `theme: auto` (the default) follows the theme's `mode`. The needle's shadow is `needle-glow`; the moon takes `moon` (lit face), `moon-shade` (dark side) and `moon-glow` (default theme keeps the original black, white, `#1c1d1f` and white). Both follow a runtime theme change. Not themed yet: any colour still literal in code.

## Gotchas

- **A misbehaving display with a clean log — read the captured child output.** Under `LevityDash-run` each child's stdout/stderr goes to `~/Library/Logs/LevityDash/<name>.out`. The app's own `LevityDash.log` can record a perfectly clean startup while a traceback that aborted the dashboard load went only to the supervisor's terminal. That is how [dashboard-wont-load.md](docs/tasks/dashboard-wont-load.md) stayed open for two months.
- **An offscreen render is not proof that a dashboard loads.** `render_dashboard.py` built gauges fine for a config that crashed the real windowed app, which is what cleared the correct suspect in July. To trust a verdict on a dashboard, run the real app too, with a live backend and `STATEFUL_DEBUG=1` — statekit swallows factory exceptions otherwise.
- **A failing item becomes a red error tile.** `itemLoader` builds one item per call; if it raises, the error is logged at ERROR with the traceback (`Item failed to load and was replaced by an error tile: …`), whatever the item half-built is removed, and an `ErrorTile` (type or key plus the first error line) takes its geometry. The rest of the board loads. While a tile exists, a save is refused so the broken item is not deleted from the file. Failed statekit factories now log at ERROR instead of staying silent (`STATEFUL_DEBUG=1` also raises). Before 2026-10, one raising item aborted the whole load and left "just a big moon".
- **A headless render's `--size` is the scene size.** Until 2026-10-06 it was the window size, and the menu bar and status bar (48px + 22px in the design seed) came out of it, so a `1600x900` render was `1600x830`. That looked like a scene-sizing bug and was not: the scene always filled the view exactly. `_boot.resizeScene` now sizes the window around the chrome. In the real app, macOS has a native menu bar (no in-window cost) and the status bar is off unless `[QtOptions] status-bar` is set; turn it on and the scene is its height shorter, which is correct.
- **A font the dashboards ask for but the app does not ship.** `.levity` files reference `Roboto Mono`; only Nunito and Roboto were bundled until 2026-09-08, so it worked on any machine that happened to have it installed and died on the ones that didn't. On macOS `database.hasFamily()` can answer `True` through alias population while the family has no usable styles, so the existing not-found guard in `__getFontFromConfig` never fires — the tell is Qt's own `Populating font family aliases took … Replace uses of missing font family` line, which reads like a performance nag. Bundle a font under `resources/fonts/` rather than relying on the host having it.

- **macOS Bluetooth/TCC**: with the Govee plugin enabled, the process dies with `SIGABRT` (exit 134) and **no output at all** at startup. Not a code bug, and *not* a missing permission grant — granting Bluetooth in System Settings does not fix it. macOS kills any process touching Bluetooth when the **responsible process's bundle** lacks `NSBluetoothAlwaysUsageDescription` in its `Info.plist`, and that check runs *before* the TCC grant is consulted. The crash report says `Termination Reason: Namespace TCC` and names the missing key. iTerm and PyCharm ship it; some hosts (including Claude Code's `claude-code` helper bundle) do not — so run BLE work from a terminal that has it. `devtools/ble_scan.py` is a dependency-free way to check whether a given host can do BLE at all. Never patch a signed app's `Info.plist` to work around this; it breaks the code signature.
- **Cross-thread timers**: never call `QTimer.start()` from a non-owner thread — it silently does nothing. Use `startTimerSafe`/`stopTimerSafe` from `lib/utils/shared.py` in any data-callback path.
- **Off-thread painting**: workers may paint `QImage` only; all scene-graph reads must be resolved to plain values on the GUI thread before handing work to a `Worker` (see `Graph.py` `render()` for the pattern).
- **StateProperty encoders**: anything reaching the YAML dumper must be a plain type; leaked objects (e.g. `DeepChainMap`, measurement objects) get silently `repr()`'d into the save file and corrupt it. Flatten in `.encode`.
- **Keys**: `CategoryItem` is a tuple subclass carrying two orthogonal extras — `source` (*who* provided it; reconciled across providers by `MultiSourceContainer`) and `identity` (*which* value it is — `…temperature#bedroom`; **never** merged). Identity participates in equality, hashing *and* the `__existing__` interning cache. Both forms round-trip through `str()`/constructor: `str()` renders `source:path#identity` (`Govee-bedroom:indoor.temperature.temperature#bedroom`) and the constructor splits both affixes off before tokenizing the path. ⚠️ It did **not** until 2026-09-04 — the tokenizer is word-chars only, so `:` was neither delimiter nor atom content and a source was silently folded into the path atoms (`Govee:a.b` → `('Govee','a','b')`). Schema lookups are keyed by the *base* key, so identity must be stripped before any schema lookup (`getExact`, `getUnitMetaData`).

## Conventions

- Tabs for indentation in Python (existing style).
- Commit messages: `type(Scope): summary`, e.g. `fix(UI.Graph): …`, `feat(Stateful): …`.
- `.levity` dashboard files are YAML; example config/templates under `src/LevityDash/resources/example-config/`.
- **Task handoffs live in `docs/tasks/`** — self-contained briefs (context, expected change, verification, suggested branch/worktree) for work meant to be picked up in a fresh session or by another agent. If working from one of these, sync your branch with `dev` first (`git merge dev`) since new briefs and unrelated fixes land there continuously.

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
