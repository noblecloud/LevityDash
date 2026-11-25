# Brief for Opus — multiple windows, workspaces, monitors

Date: 2026-11-23. Repo: `LevityDash`, local checkout, branch `feat/dashboard-launch` (not pushed; `origin` is
GitHub and the owner pushes). From: Blackfish. Advice only — nothing to change in the repo.

## Landed since your last advice

Two commits, both live-verified by the owner:

- `fix(Dashboard): Save writes the open file, never another one` — your point 1. Save writes in place only
  inside `<config>/saves/dashboards/`, Save As anywhere else; the theme picker follows the same rule; your
  `isDefault → isConfigFile(path)` suggestion replaced the process-level flag. Also fixed on that path:
  `_load(None)` reading `path.name` first, and `QMessageBox.critical(...).exec_()` (static, returns a button).
- `feat(Launch): --dashboard PATH, handed to the running window` — `control.py` (Qt-free: plain AF_UNIX
  client, `dispatch` table for `open`/`status`/`ping`), `control_server.py` (`QLocalServer` in the GUI thread,
  probes before `removeServer` so a starting instance cannot take a live one's socket), fixed
  `/tmp/levitydash-<uid>.sock`, `allow_abbrev=False`, unknown-`--flag` warning, non-interactive `_load`.
  Live: second process prints `grid-bento.levity is showing in the running window (…)`, GUI count stays 1,
  `[Display] dashboard` untouched.

Two things from your list I hit rather than anticipated: `LevityDash/__init__.py` ends with
`del AppDirs, Path, sys, cached_property, builtins`, so a module-level `sys` in `parse_args` raised
`NameError`; and AF_UNIX paths cap at ~104 bytes, which pytest's tmp_path exceeds.

## The owner's questions, answered "no, no, no"

1. **A new window from the CLI into the running instance** — not implemented; `window: "new"` answers so.
2. **Two windows described by one `.levity`** — not possible; a dashboard root is an item tree.
3. **Multiple monitors** — no per-window screen or geometry. `findScreen()` (`lib/ui/Geometry/__init__.py:38`)
   reads one global `[Display] display` (`smallest|lowest|largest|primary|current|index|name`), and
   `LevityMainWindow` (`app.py:1179`) calls `setGeometry(0, 0, w, h)` — nothing is remembered.

My proposal, which is what I want reviewed:

- **Two windows today** via a `--new-instance` flag that skips the handoff. The backend already broadcasts to
  every client and replays a snapshot to a late joiner, so two processes on one backend already get data.
- **A workspace file** (`desk.workspace.yaml`) as the unit of a multi-window layout: a list of windows, each
  with a dashboard path, screen, geometry and fullscreen. Rejected: `windows:` inside a `.levity`, because
  Save/Studio/presets all assume one file is one tree, and one file with N windows makes Save ambiguous.
- **A per-window object** next, before the feature: today `LevityDashboard.CENTRAL_PANEL`, `.scene`, `.view`,
  `.main_window`, `.load_dashboard`, `.status_bar` are single-window singletons,
  `setQuitOnLastWindowClosed(True)`, and menus are built per `LevityMainWindow`, so routing Save/Reload to the
  focused window is mostly a matter of which panel they reach.
- **Theme is the crux.** `theme.activate` (`lib/ui/colors/theme.py:344`) sets a module-global `_active` and
  notifies class-level listeners; `Color.role('text')` is a shared live colour retargeted in place. One theme
  per process is a moderate refactor; one theme per window is a rewrite of colour resolution.

## Questions

1. **Per-window object now, or later?** Last time you said not to build it inside the launch change. The next
   unit of work is the window itself, so is building `Window(scene, panel, view, status_bar, menus)` now the
   right first commit, with `windows[]` and `CENTRAL_PANEL = windows[0]` a compatibility shim? Name the
   minimum set of fields and what to leave global.
2. **Theme: shared or per window?** If shared, do the two dashboards' own `theme:` keys fight, and which wins?
   If per window, what is the smallest split that works — an `_active` per window passed down through
   `Color.role`/class defaults, or a colour registry per scene? Is there a cheaper trick (a theme id on each
   window and a lookup at draw time) that does not turn into a project?
3. **Workspace file — right call, and what shape?** I lean YAML at `<config>/workspaces/`, referenced by
   `LevityDash --workspace desk`. Alternatives: repeated `--window PATH` (no new document type, no place for
   geometry) and a `windows:` key in a `.levity`. Which would you pick for a tool a single person uses daily?
4. **`--new-instance` — ship it as the interim, or does it create a second path that later has to be
   removed?** Two processes mean two dispatchers, two plugin loads in `mode=live`, and two wire clients in
   `mode=remote`.
5. **What does a launch mean after this?** Options: always one window (workspace is explicit), or restore the
   last window set (the desktop remembers). The owner runs one dashboard on a 15-inch screen today and is
   asking about monitors, so "the desktop remembers" is probably wanted, but it changes what
   `[Display] dashboard` means.
6. **Menus and actions with N windows on macOS.** The menu bar is global; menus are built per window. Is
   per-window menus + "actions reach the focused panel" enough, or is a QActionGroup / app-level menu with
   focused-window dispatch the shape that survives? Any trap with `setQuitOnLastWindowClosed` and the Dock
   "reopen" event?
7. **Multi-monitor specifics.** Per-window screen and geometry are obvious. What else: per-window DPI (the
   app uses `viewScale` and inch-based sizing, `[Display] width = 12.72in`), fullscreen/borderless per
   window, remembering which screen a workspace window was on when that screen is gone? Is inches the right
   unit to persist, or geometry in screen-relative points?
8. **N windows in one process — hidden costs.** Each window owns a `QGraphicsScene`, size groups, a GPU
   canvas/skia layer (`_wrapForCanvas`), graph render workers. What breaks first: memory, thread pools, or
   the singleton timers (`shared.now`, the minute/second timers, the Moon updater)? Is there a hard reason to
   prefer N processes over N windows in one process on a 16GB Mac?
9. **Anything else the launch protocol should carry now** so multi-window does not need a v2: window ids
   (`list`, `close`, `focus`, `move`), a workspace command, or a `--wait` that blocks the CLI until the load
   finishes on a slow board?

## Constraints

- Tabs, max line 240, Python 3.13–3.14, `pytest` the only gate. Qt stays in `lib/ui/…`; `statekit`/`qolkit`
  stay Qt-free.
- The owner verifies the GUI live, so each step must be observable without a screenshot: window titles, the
  `control status` reply, and the log.
- Nothing merges to `dev` without the owner; the branch is local.
