# Brief for Opus — launching a specified dashboard, and the road to multiple windows

Date: 2026-11-23. Repo: `LevityDash` (this checkout is on `feat/dashboard-launch`, based on `origin/dev` at
`9132f1cb`). Owner: Neal. From: Blackfish.

## What is wanted

1. **Now.** Launch the app showing a named `.levity` file, without editing `[Display] dashboard` in
   `config.ini`. Today the only way to change dashboards is to overwrite that config key, so trying a file
   means losing the default (we did exactly that today and had to restore from a backup).
2. **Now, ideally.** If an instance is already running, hand the file to *that* instance and show it there,
   instead of starting a second process.
3. **Later.** Several windows open, each showing its own dashboard.

The owner wants to keep playing with `docs/design-references/grid-packing.levity` while their real
dashboard stays the configured default.

## How selection works today

- `[Display] dashboard` names a file in `<config>/saves/dashboards/`. `Config.dashboardPath`
  (`src/LevityDash/lib/config.py:617`) reads it; the setter (`:627`) **writes `config.ini` immediately**.
- `CentralPanel.__init__` (`src/LevityDash/lib/ui/frontends/PySide/Modules/CentralPanel.py:59-71`) resolves
  that path, copies a template there when it is missing, and sets `self.filePath`.
- `CentralPanel._load` (`:328`) parses the file, expands presets, resolves variables, activates the theme,
  and sets `self.state`. It sets the window title from the file name (`:330`).
- `CentralPanel.setDefault` (`:406`) is the only place that calls `userConfig.dashboardPath = ...`, so a
  *load* does not write config today. Good news: an override can stay non-destructive without a new rule.
- The CLI parser lives in `src/LevityDash/__init__.py:149` (`_LevityArgParser`), currently `--reset-config`
  and `--version`, parsed with `parse_known_args`, so unknown flags are ignored rather than fatal.
  `--fullscreen` is still read by hand in `app.py:1292`.
- Frontend/backend split (`AGENTS.md`, `lib/wire/`): `mode = live` runs plugins in-process; `mode = remote`
  (the owner's config) attaches the GUI to a standalone `LevityDash-backend` over a WebSocket on
  `127.0.0.1:8667`. The GUI parses the `.levity` itself either way — the backend holds data, not layout.
- The dashboard is one scene owned by `CentralPanel`, and `LevityDashboard` is an immutable singleton whose
  slots include `CENTRAL_PANEL`, `scene`, `view`, `main_window`, `load_dashboard` (`__init__.py:172-192`).
  `LevitySceneView.__init__` assigns `LevityDashboard.view` and `LevityDashboard.load_dashboard` (`app.py:388-393`).

## Proposed design (critique this, do not just endorse it)

**A. CLI flag.** `--dashboard PATH` on `_LevityArgParser`, stored on `_LevityDashboard` (a parsed-args
attribute, not a slot). A relative path resolves next to the working directory; the flag wins over
`[Display] dashboard`; config is never written. The flag is threaded to `CentralPanel.__init__`, which uses it
as `self.filePath` instead of `userConfig.dashboardPath`, and to `setDefault`, which should refuse (or
save-as) while an override is active.

**B. Handoff to a running instance.** The GUI process listens on a `QLocalServer` (per-user socket name, e.g.
`levitydash-<uid>`). A new process with `--dashboard` tries to connect first:

- connect succeeds → send one JSON line `{"dashboard": "<abs path>", "window": "current"}`, wait for a reply,
  print it, exit 0;
- connect fails and the socket file is stale → remove it and continue as a fresh instance;
- no `--dashboard` → behave exactly as today.

The server marshals to the GUI thread (a queued signal, as `lib/wire/frontend.py` already does for its
messages) and calls the same path the menu's "Open" does (`CentralPanel._load(Path)`), then replies
`{"ok": true, "dashboard": ..., "window": <title>}`.

**C. Multi-window, later.** The protocol carries `"window": "current" | "new"`, so adding `new` does not
change the wire. Today `new` answers `{"ok": false, "error": "not implemented"}`.

## Questions

1. **Who owns the control channel?** A `QLocalServer` in the GUI process, or a command routed through the
   existing wire (a second `WireClient` connecting to 8667 and having the backend relay it)? My reading: the
   backend cannot answer it, because the path is local to the GUI and a backend may be on another machine;
   and the frontend already owns every scene-graph touch. Is there a reason to prefer the wire anyway —
   e.g. one obvious place for "commands" once there are more of them?
2. **Second-instance detection.** Qt's usual trick is to attempt `QLocalServer.listen()` and treat failure as
   "someone else owns this app". But this app is two processes (GUI + backend) and only the GUI should own
   the socket, and a crashed instance leaves a stale socket. Is a lock file plus a connect-probe better than
   relying on `QLocalServer.errorString()`? Any macOS-specific trap with `QLocalServer` over a socket path in
   the config dir rather than `/tmp`?
3. **What is the smallest change now that does not have to be undone for N windows?** The singleton is the
   problem: `LevityDashboard.CENTRAL_PANEL`, `.view`, `.load_dashboard`, the global theme
   (`theme.activate`), and size-group refit hooks all assume one scene. Should this feature introduce a
   per-window object (scene + central panel + theme handle) and leave the singleton as "the first window",
   or is that a rewrite better done as its own change later, with the socket protocol designed to survive it
   either way? If the former, name the minimum set of globals to move.
4. **Saving under an override.** Options: (a) `Ctrl+S` writes over the override file — fine for a scratch
   example, destructive for a file in the repo; (b) `Ctrl+S` becomes save-as; (c) the session is read-only.
   The owner's use is "open a reference example, poke at it, don't lose the real dashboard". Which is least
   surprising?
5. **Protocol.** Newline-delimited JSON over `QLocalSocket` seems sufficient. Anything you would add now —
   an explicit protocol version, a `{"ping": true}` health reply, an id per request — that costs nothing
   today and saves a migration later?
6. **Anything in the flag's semantics** that will bite: `parse_known_args` silently swallowing a typo;
   a path that does not exist (fail with a message, or start with the default dashboard and warn);
   a path inside the config dir vs. anywhere on disk; opening the same file twice.

## Constraints

- Tabs, 2-wide, max line length 240, Python 3.13–3.14. `pytest` is the only gate.
- Keep Qt out of `statekit`/`qolkit`; the control channel belongs to the PySide frontend.
- Work stays on `feat/dashboard-launch`; nothing merges to `dev` without the owner.
- The owner verifies the GUI live, so the change must be observable: window title plus the loaded file's path
  in the log.

## Verification planned

- `pytest`: parser accepts `--dashboard`; a bad path fails with one clear message; the override never calls
  `Config.dashboardPath`'s setter (assert `config.ini` is byte-identical after a load).
- Live: run the app with `--dashboard docs/design-references/grid-bento.levity` while an instance is showing
  `grid-packing.levity`; the running window's title changes and no second window appears; `config.ini` keeps
  its original `[Display] dashboard`.
