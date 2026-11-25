# Worker brief — launch protocol v2 and `--new-instance`

Audience: a coding worker in its own worktree. Read this file first, then the design record it points at.

## Base and setup

- Repo: `/Users/noblecloud/Code/LevityDash`. Base branch: `feat/dashboard-launch` (NOT `dev`, NOT `main`).
- Make your own worktree so the owner's checkout is untouched:
  `git -C /Users/noblecloud/Code/LevityDash worktree add /tmp/launch-protocol -b feat/dashboard-protocol feat/dashboard-launch`
  then work only in `/tmp/launch-protocol`.
- Poetry uses an in-project `.venv` per directory: run `poetry install` once in the worktree (the local dev
  dependency `../unitcorn` must resolve; a warning that `../WeatherUnits` does not exist is expected noise).
- Test command: `poetry run python -m pytest …`. **Not** `poetry run pytest` — the console script does not put
  the repo root on `sys.path`, and ten test modules import `tests.conftest` and fail to collect.
- Tabs for `.py`, 2-wide; max line length 240; Python 3.13–3.14.

## Read first

- `docs/BRIEF-OPUS-MULTI-WINDOW-2026-11-23.md` — the questions this implements.
- `src/LevityDash/lib/ui/frontends/PySide/control.py` — Qt-free client, `dispatch` table, `COMMANDS`.
- `src/LevityDash/lib/ui/frontends/PySide/control_server.py` — the `QLocalServer` listener.
- `src/LevityDash/__main__.py` — `_handOffOrResolveDashboard`, called from `main()`.
- `src/LevityDash/__init__.py` — `_LevityArgParser` (`--dashboard`, `allow_abbrev=False`) and
  `_LevityDashboard.__slots__` (which includes `dashboardOverride`).
- `tests/ui/test_dashboard_launch.py` — the existing handoff tests; extend them, do not weaken them.

## Job 1 — protocol v2 fields

Keep the one-request-per-connection, newline-JSON shape. Changes:

1. `status` answers `windows: [{id, title, dashboard, screen, pid}]` even when there is one window. The window
   id today is `"main"`; `screen` is `view.screen().name()`; `dashboard` is the loaded file path or `null`.
   Keep the existing top-level `dashboard` and `window` fields for compatibility.
2. `open`'s `window` field accepts `"current"`, `"main"` and `"new"`. `"new"` still answers
   `not_implemented`. Any other value is `bad_request`.
3. Reserve `list`, `focus`, `close`, `move`, `workspace` in `COMMANDS`, each answering
   `{"ok": false, "error": {"code": "not_implemented", "message": …}}`.
4. Errors become `{"ok": false, "error": {"code": …, "message": …}}` with codes
   `not_found | not_implemented | busy | bad_request`. Update every existing error site (missing file,
   relative path, unknown command, parse failures, YAML failure, load exception). The string-only `error`
   field goes away — update the tests.
5. CLI exit codes map from the code: `not_found` 3, `bad_request` 4, `not_implemented` 5, `busy` 6,
   anything else 1. Document the mapping in `docs/config/dashboard/opening.md`.
6. `--no-wait` on the CLI: send the request and exit 0 as soon as it is written, without reading the reply.
   Default behaviour stays "wait for the reply and print it" (this is what makes a slow board honest).

## Job 2 — `--new-instance`

1. Add the flag to `_LevityArgParser`. With it, `main()` skips `_handOffOrResolveDashboard`'s socket
   handoff and starts a window normally (`dashboardOverride` still applies when `--dashboard` is given).
2. The new process must NOT take the primary's socket. It listens on
   `/tmp/levitydash-<uid>-<id>.sock`, where `<id>` is a short stable string: the value of
   `--window-id` if given, else a slug of the dashboard file's stem, else `"w<pid>"`. Export the same
   `LEVITYDASH_CONTROL_SOCKET` override behaviour (`socketPath(id=…)`).
3. The screenshot server (`userConfig [Debug] screenshot-port`, default 0 = off) must not collide: when the
   port is non-zero and `--new-instance` is set, log a warning and start it on `port + <n>` or skip it —
   pick one and say which in the commit message.
4. `mode = live` with `--new-instance`: print one warning that a second instance loads the plugins twice and
   polls the APIs twice. Do not refuse.
5. Two processes may Save the same file; last write wins. Log one line when a save lands on a file another
   live instance reports as loaded (cheap check: ask the primary's socket for `status` if it answers).

Best-effort, report if you skip it: a `register` command on the primary's socket so the primary's `status`
lists the child windows too. If registration is more than ~60 lines, leave it out and say so.

## Done criteria

- `poetry run python -m pytest tests/ui/test_dashboard_launch.py tests/ui/test_dashboard_file.py -q` passes.
- New tests: error codes for a missing file / relative path / unknown command / `window: "new"`; exit-code
  mapping (unit-level is fine); `--no-wait` writes and returns; `--new-instance` socket path differs from the
  primary's and the primary's socket still answers `status`; `mode=live` warning text (capture via caplog or
  a subprocess run with `-q`).
- Manual smoke, no screenshot needed:
  `poetry run LevityDash --dashboard <file>` in a first process, then
  `poetry run LevityDash --new-instance --dashboard <file2>`; both windows open, `control status` against
  each socket answers with its own file, and the first process keeps its socket.
- `git show --stat` lists exactly the files you intended; commit with an explicit path list.

## Do not

- Do not touch `docs/design-references/`, the showcase generators, `tests/test_showcase.py` (its failures are
  pre-existing: scenario epochs are baked at generation time).
- Do not change the theme engine, the singleton slots, or the save rule (`isConfigFile`) — that design is
  settled.
- Do not merge into `dev`, do not push anywhere. Leave your branch `feat/dashboard-protocol` and report the
  sha.
- Do not weaken `tests/ui/test_dashboard_file.py` or `test_theme_menu.py`; the Save rule is deliberate.

## Report back

The branch name and sha, the test command output tail, what you changed in each file, anything you skipped
and why, and the one-line smoke result for each of the two windows.
