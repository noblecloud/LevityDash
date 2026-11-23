# Opening a dashboard

LevityDash shows one dashboard at a time, named by `[Display] dashboard` in `config.ini` (a file in
`<config>/saves/dashboards/`). Two other ways open a file without touching that setting.

## A dashboard for one run

```sh
poetry run LevityDash --dashboard docs/design-references/grid-packing.levity
```

`--dashboard PATH` shows that file instead of the configured one. The config is not written, so the next
launch with no flag shows the configured dashboard again. A relative path is resolved against the directory
the command was run from.

## Handing it to the running window

If LevityDash is already open, `--dashboard` does not start a second app: it hands the file to the window
that is running and exits. The command prints the window title once the file has loaded.

```sh
$ poetry run LevityDash --dashboard docs/design-references/grid-bento.levity
levitydash: grid-bento.levity is showing in the running window (Levity Dashboard - grid-bento.levity)
```

The window owns a local socket at `/tmp/levitydash-<uid>.sock`, so the handoff works from another terminal
or over `ssh` to the same machine. The path is fixed rather than taken from `$TMPDIR` because an app started
from Finder has a per-session temp directory and a shell over `ssh` usually has none.

A probe is available for scripts:

```sh
poetry run python -m LevityDash.lib.ui.frontends.PySide.control status
```

It answers with the loaded file and the window title. `open PATH` and `ping` are the other commands; the
reply is one line of JSON. Set `LEVITYDASH_CONTROL_SOCKET` to use a different socket path.

Out of scope today: a second window. The protocol carries `window: "current" | "new"`, and `new` answers
"not implemented" until there is one.

## What Save writes

Save (`Ctrl+S`) writes the open file when it lives in `<config>/saves/dashboards/`. A dashboard opened from
anywhere else — a reference file in the repo, a template, a file on another disk — is not written in place:
Save becomes Save As, with the same name under `saves/dashboards/`. The theme picker follows the same rule,
so choosing a theme for a reference file leaves that file alone; the theme is in force for the run.

`Dashboard > Set Default` is the one action that changes `[Display] dashboard` to the open file.
