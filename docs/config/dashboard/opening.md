# Opening a dashboard

LevityDash shows one dashboard at a time, named by `[Display] dashboard` in `config.ini` (a file in
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

`list`, `focus`, `close`, `move` and `workspace` answer `not_implemented`: the names are reserved for the
multi-window protocol and carry no work yet. `open`'s `window` accepts `current` or `main` for the one window
this process has; `new` answers `not_implemented` — a second window is a second process, below.

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

## What Save writes

Save (`Ctrl+S`) writes the open file when it lives in `<config>/saves/dashboards/`. A dashboard opened from
anywhere else — a reference file in the repo, a template, a file on another disk — is not written in place:
Save becomes Save As, with the same name under `saves/dashboards/`. The theme picker follows the same rule,
so choosing a theme for a reference file leaves that file alone; the theme is in force for the run.

`Dashboard > Set Default` is the one action that changes `[Display] dashboard` to the open file.
