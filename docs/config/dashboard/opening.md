# Opening a dashboard

LevityDash shows one dashboard at a time, named by `[Display] dashboard` in `config.toml` (a file in
`<config>/saves/dashboards/`). The other ways to open a file — one run, a handoff to the running window, a
second window — open it without touching that setting.

## A dashboard for one run

```sh
poetry run LevityDash --dashboard docs/design-references/grid-packing.levity
```

`--dashboard PATH` shows that file instead of the configured one. The config is not written, so the next
launch with no flag shows the configured dashboard again. A relative path is resolved against the directory
the command was run from.

## Handing it to the running window

If LevityDash is already open, `--dashboard` does not start a second app: it hands the file to the window
that is running and exits. The command prints the window title once the file has loaded — a slow board is
not reported as a success before it is on screen.

```sh
$ poetry run LevityDash --dashboard docs/design-references/grid-bento.levity
levitydash: grid-bento.levity is showing in the running window (Levity Dashboard - grid-bento.levity)
```

Add `--no-wait` to send the request and exit as soon as it is written, without reading the reply. The window
still opens the file; nothing reports what happened. Use it in a launcher that must not block on the load.

The window owns a local socket at `/tmp/levitydash-<uid>.sock`, so the handoff works from another terminal
or over `ssh` to the same machine. The path is fixed rather than taken from `$TMPDIR` because an app started
from Finder has a per-session temp directory and a shell over `ssh` usually has none.

A probe is available for scripts:

```sh
poetry run python -m LevityDash.lib.ui.frontends.PySide.control status
```

It answers with the loaded file, the window title and the list of windows; `open PATH` and `ping` are the
other commands, all with a one line of JSON reply. Set `LEVITYDASH_CONTROL_SOCKET` to use a different path.

### Replies and exit codes

A failure is `{"ok": false, "error": {"code": ..., "message": ...}}`. The code is one of four, and the CLI
turns it into an exit status so a script does not have to read the message:

| code              | exit | meaning                                                     |
|-------------------|------|-------------------------------------------------------------|
| — (`ok: true`)    | 0    | the request was carried out                                 |
| `not_found`       | 3    | no such dashboard file, or no window to act on              |
| `bad_request`     | 4    | the request itself is wrong (relative path, unknown command)|
| `not_implemented` | 5    | a command this version reserves but does not carry out      |
| `busy`            | 6    | no reply in time, or the connection failed                  |
| anything else     | 1    | unrecognised failure                                        |

`status` answers `windows`, one entry per window, at least one even when there is only one window:

```json
{"v": 2, "ok": true,
 "dashboard": "/Users/me/desk.levity",
 "window": "Levity Dashboard - desk.levity",
 "windows": [{"id": "main", "title": "Levity Dashboard - desk.levity",
              "dashboard": "/Users/me/desk.levity", "screen": "Built-in Retina Display", "pid": 4112}]}
```

`close` closes one window by id (`current`, `main`, or the id of a window registered with this one), and
`workspace` answers the layout this window belongs to — see below. `list`, `focus` and `move` answer
`not_implemented`: the names are reserved and carry no work yet. `open`'s `window` accepts `current` or `main`
for the window this process has; `new` answers `not_implemented` — a second window is a second process, below.

## A second window

```sh
poetry run LevityDash --new-instance --dashboard other.levity
```

`--new-instance` skips the handoff and starts a second window, whatever is already running. Its own socket is
`/tmp/levitydash-<uid>-<id>.sock`, where `<id>` is `--window-id` when given, else a slug of the dashboard's
file name, else `w<pid>`. The first window keeps its socket, and the second registers itself with the first,
so `control status` against the first lists both. `control open` still means the *first* window: pass
`LEVITYDASH_CONTROL_SOCKET` to drive the second one.

Two windows are two processes:

- **mode=live** loads the plugins in each and polls every API twice. `--new-instance` allows it and prints one
  warning; `mode=remote` attaches both windows to one backend instead.
- **Save** writes the open file in each window, so two windows on the same file means last write wins. A save
  into a file another window reports as loaded logs one line, and the other window keeps its copy until it
  reloads.
- The **screenshot server** (`[Debug] screenshot-port`) is off in a second instance: the port belongs to the
  first window, and nobody can guess the second one it would have picked.

## A workspace: one file, several windows

A **workspace** is the unit of a multi-window layout: one YAML file listing the windows, the dashboard each
shows, the monitor it goes on and where. It lives in `<config>/workspaces/<name>.yaml`.

```yaml
name: desk                 # optional, defaults to the file's stem
theme: dusk                # optional: the one theme the whole layout uses
windows:
  - id: main               # stable, unique in the file; it is the window's control socket id
    dashboard: home.levity # <config>/saves/dashboards, then the current directory, or absolute
    screen: {name: "DELL U2720Q", fallback: primary}
    geometry: {x: 0, y: 0, width: 50%, height: 100%}   # fractions of that screen's available area
    mode: windowed         # windowed | fullscreen | kiosk
  - id: right
    dashboard: /Users/me/tower.levity
    screen: {name: "Side Monitor", fallback: primary}
    geometry: {x: 0.5, y: 0, width: 0.5, height: 1}
```

```sh
poetry run LevityDash --workspace desk              # a name in <config>/workspaces/
poetry run LevityDash --workspace ./desk.yaml       # or a path
poetry run LevityDash --window home.levity --window tower.levity   # the same thing, unsaved
```

Window 1 opens in the process you started; each remaining window is a child process
(`python -m LevityDash --new-instance --window-id <id> --dashboard <path>`, plus `--screen-name`, `--geometry`
and `--mode` when the file gives them), so every window keeps its own control socket, as `--new-instance`
already does. A child that exits is logged once and not restarted.

`--window PATH` may be repeated to build an unsaved workspace in memory: one process per path, in the order
given, with no ids and no geometry to remember. It cannot be combined with `--workspace`, and it is refused
(`bad_request`, exit 4) rather than guessed at.

`[Display] workspace` in `config.toml` names a workspace to open when no flag says otherwise. It is only a
default: `--dashboard`, `--window` or `--workspace` all win over it, and `[Display] dashboard` still means the
single window you get with no flags at all.

The file is validated strictly. An unknown key is an error that names the key — `unknown key 'position';
known: id, dashboard, screen, geometry, mode` — as is a duplicate `id`, a `geometry` value that is not a
fraction or a percentage, and a `mode` that is not one of the three.

### Screens, geometry and kiosk

- `screen.name` is the name `QGuiApplication.screens()` reports, exactly as the operating system spells it. A
  name that is not attached falls back to `screen.fallback` (`primary` by default); the **file keeps the saved
  name**, so plugging the monitor back in restores the layout instead of leaving it on whatever was attached.
  The name is only rewritten when the window is actually moved to another monitor.
- `geometry` is fractions of that screen's available area (`0.5`) or percentages (`50%`), clamped so a layout
  written on a bigger monitor still lands on screen. A window with no `geometry` is sized as usual.
- `mode: kiosk` is frameless at the screen's full geometry — no title bar, no menu, nothing of the desktop.
  `mode: fullscreen` keeps the frame and takes the available area. Neither is decided by the "this looks
  nearly fullscreen" heuristic, which still applies to a window no file places.

### What is remembered, and when

On quit each window writes its own `screen` and `geometry` back into the file, in the window's own process,
re-reading the file first so two windows do not clobber each other. Nothing else is ever written: windows are
not added or removed, `dashboard` is not rewritten, and `mode` stays as authored. A workspace file deleted
while the app is open is reported in one line and nothing is written.

Quitting the primary asks the windows it started to close (the same as `control close ID`) and waits at most
three seconds for them; a window that does not answer is left running and named in the log.

### Theme

A layout has one theme, never one per window and never one per focus. `theme:` in the file wins; without one,
the first window's dashboard theme wins. A window whose dashboard names a different theme logs one line —
`paper theme ignored: the workspace uses dusk` — and uses the layout's.

### Asking who is there

```sh
poetry run python -m LevityDash.lib.ui.frontends.PySide.control workspace
```

```json
{"v": 2, "ok": true,
 "workspace": "/Users/me/Library/Application Support/LevityDash/workspaces/desk.yaml",
 "name": "desk",
 "windows": [{"id": "main", "pid": 4112, "screen": "DELL U2720Q",
              "geometry": {"x": 0.0, "y": 0.0, "width": 0.5, "height": 1.0}, "mode": "windowed"},
             {"id": "right", "pid": 4127, "screen": "Side Monitor",
              "geometry": {"x": 0.5, "y": 0.0, "width": 0.5, "height": 1.0}, "mode": "windowed"}]}
```

`workspace` is `null` and `name` is the window's id when no workspace file is open, so the shape does not
depend on how the app was started. `control status` on the primary lists the same windows with their titles
and dashboards; `control close right` closes one of them.

## What Save writes

Save (`Ctrl+S`) writes the open file when it lives in `<config>/saves/dashboards/`. A dashboard opened from
anywhere else — a reference file in the repo, a template, a file on another disk — is not written in place:
Save becomes Save As, with the same name under `saves/dashboards/`. The theme picker follows the same rule,
so choosing a theme for a reference file leaves that file alone; the theme is in force for the run.

`Dashboard > Set Default` is the one action that changes `[Display] dashboard` to the open file.
