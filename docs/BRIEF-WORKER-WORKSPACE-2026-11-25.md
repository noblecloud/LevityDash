# Worker brief — workspace file, `--workspace`, and one process per window

Audience: a coding worker in its own worktree. Read this first.

## Base and setup

- Repo: `/Users/noblecloud/Code/LevityDash`. Base branch: `feat/dashboard-launch` at `9e15a001` (it already has
  `--dashboard`, the control socket, protocol v2, error codes and `--new-instance`).
- Your own worktree, so the owner's checkout is untouched:
  `git -C /Users/noblecloud/Code/LevityDash worktree add /tmp/launch-workspace -b feat/dashboard-workspace feat/dashboard-launch`
- `poetry install` once in the worktree. If it fails on the local dev dependency, the sibling checkout is
  `../unitcorn`: `ln -s /Users/noblecloud/Code/unitcorn /tmp/unitcorn` makes `../unitcorn` resolve inside
  `/tmp`. Do not commit anything outside the repo.
- Tests: `poetry run python -m pytest …` (**not** `poetry run pytest`; ten modules import `tests.conftest`
  and fail to collect otherwise). UI tests boot a headless app: ~1–2 min per session, so use generous timeouts.
- Expected noise: `Path …/WeatherUnits for unitcorn does not exist`, and many `Failed to disconnect …`.
- Tabs, 2-wide; max line 240; Python 3.13–3.14.

## Read first

- `docs/BRIEF-OPUS-MULTI-WINDOW-2026-11-23.md` — the design record (workspace shape, screen fallback,
  kiosk, why one process per window).
- `src/LevityDash/lib/ui/frontends/PySide/control.py` — `socketPath(id=…)`, `EXIT_CODES`, `dispatch`.
- `src/LevityDash/__main__.py` — `main()`, `_resolveDashboard`, `_windowId`, `--new-instance` handling.
- `src/LevityDash/lib/config.py` — `[Display] dashboard`, `dashboardPath` (do not change its meaning).

## Job — a workspace is the unit of a multi-window layout

**File.** YAML in `<config>/workspaces/<name>.yaml`. Shape (validate strictly; an unknown key is an error
naming the key, not a silent default):

```yaml
name: desk                 # optional, defaults to the file's stem
theme: night               # optional; the one theme the whole app uses, see "Theme" below
windows:
  - id: main               # stable, unique within the file; used as the control socket id
    dashboard: home.levity # relative to <config>/saves/dashboards then cwd, or absolute
    screen: {name: "DELL U2720Q", fallback: primary}
    geometry: {x: 0, y: 0, width: 100%, height: 100%}   # fractions of that screen's availableGeometry
    mode: windowed         # windowed | fullscreen | kiosk
```

**Never change what `[Display] dashboard` means.** It is still the single window you get with no flag. Add an
optional `[Display] workspace` (a name or a path) read only when no `--workspace` is given.

**CLI.**

- `--workspace NAME_OR_PATH`: read the file; open window 1 in **this** process and spawn one child process per
  remaining window.
- `--window PATH` repeated: an unsaved workspace built in memory, in the order given (no geometry, no ids).
  A flag used with `--workspace` is an error (`bad_request`).
- A child is `[sys.executable, '-m', 'LevityDash', '--new-instance', '--window-id', <id>, '--dashboard', <path>]`
  plus `--screen-name`, `--geometry` and `--mode` when the file gives them. New flags are fine; keep them
  documented in `docs/config/dashboard/opening.md`.

**Screen and geometry.**

- Resolve by `QGuiApplication.screens()` name, exact match first, then the `fallback`
  (`primary` or a screen name); if neither exists, `primary`.
- `geometry` is fractions of `screen.availableGeometry()`; `kiosk` means frameless at `screen.geometry()`.
- When the saved screen name is missing, open on the fallback **and keep the saved name in the file**; only
  rewrite it when the user actually moves the window.

**Persistence (on quit).** Write geometry and screen back into the workspace file for windows that are still
open — never add or remove windows, never rewrite `dashboard`. A window whose file was deleted is reported in
one log line and left alone.

**Theme.** One theme per process, as Opus ruled. The workspace's `theme:` wins; without one the first
window's dashboard theme wins and every other window logs `<name> theme ignored: the workspace uses <theme>`.
Never switch theme on focus. Do not touch `lib/ui/colors/theme.py`.

**Control protocol.** Add one command: `workspace` answers
`{ok: true, workspace: <path or null>, name: <name>, windows: [{id, pid, screen, geometry, mode}]}`, with the
same `{code, message}` error shape. `status` stays as it is.

**Spawn/quit rules.** A child that exits is logged once and not restarted. Quitting the primary asks the
registered children to close (`close` becomes implemented for this: it closes one window by id) and waits at
most 3 s, then leaves them. `setQuitOnLastWindowClosed(True)` stays; the primary quits when its own window
closes after asking the children.

## Done criteria

- `poetry run python -m pytest tests/ui/test_dashboard_launch.py tests/ui/test_dashboard_file.py -q` still passes.
- New tests in `tests/ui/test_workspace.py`: the file parses (good/bad), an unknown key is refused with the
  key named, `--window` order is kept, geometry round-trips through the writer, a missing screen falls back
  and keeps its saved name, the child argv is exactly as specced (monkeypatch `subprocess`/`QProcess`), and
  `workspace` answers the documented shape.
- Manual, offscreen is fine (`QT_QPA_PLATFORM=offscreen LEVITYDASH_CONFIG_DEBUG=1 LEVITYDASH_CONFIG_SEED=<repo>/tests/resources/config-seed`):
  a two-window workspace opens two processes with two sockets, `control status` on the primary lists both,
  quitting the primary closes the child. Paste the two `status` replies in your report.

## Do not

- Do not touch `docs/design-references/`, `tests/test_showcase.py` (pre-existing date-dependent failures),
  `lib/ui/colors/theme.py`, the Save rule (`isConfigFile`), or the `LevityDashboard` singleton slots.
- Do not merge into `dev`, do not push. Leave the branch and report the sha.
- Do not make the primary's socket the child's: each window keeps its own, as `--new-instance` already does.

## Report back

Branch + sha, test tail, the two `status` replies, files changed per file, what you skipped and why, and one
line on the child-closing behaviour you observed.
