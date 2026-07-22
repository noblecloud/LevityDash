# Phase 4.2 — backend/frontend split: STATUS

**Branch:** `feat/phase-4.2-backend-split` (9 commits, not yet merged to `dev`).

## Done — the split works end-to-end (verified with two real processes)

- Shared wire-message contract (`lib/wire/messages.py`), transport
  (`server.py`/`client.py`), receive adapter (`frontend.py`), send adapter
  (`wire/backend.py`) — all individually tested.
- **Standalone backend**: `lib/backend.py` rebuilt; `LevityDash-backend` entry
  point (re-run `poetry install` to register it, or `python -m
  LevityDash.lib.backend`). Headless Qt main loop + aiohttp server thread;
  clean SIGINT/SIGTERM shutdown. `[Backend] host/port` or
  `LEVITYDASH_BACKEND_HOST/PORT` (default 127.0.0.1:8667).
- **`mode=remote` frontend**: local plugins loaded but never attached/started;
  `RemoteConnection` (client thread + reconnect/backoff) marshals every
  message onto the GUI thread once. `[Backend] url` /
  `LEVITYDASH_BACKEND_URL`.
- Live verification: backend (debug config, OpenMeteo) + headless remote
  frontend → **all 43 keys** in the dispatcher, `Fahrenheit(74º)` decoding
  properly. A raw aiohttp client also works (language-agnostic proof).

## Follow-ups

1. ~~**Derived-unit wire support**~~ — **done** (3e9dc4f). Wind/rate values
   now decode to their specialized class (MilesPerHour) instead of
   degrading to unitless floats.
2. **Full identical-render check** — substantially done via the real-GUI
   debugging below (dashboard renders remote data, incl. stale labels).
   Remaining: graphs empty until #3; float-under pair sync is a known
   separate wart (pre-existing, recursion-prone autofit per maintainer).
   NOTE: the Govee/BLE TCC gotcha now applies to whatever terminal
   launches the *backend*.
3. **Timeseries + plugin control plane** — the next roadmap milestone
   (graphs in remote mode have no timeseries source yet; realtime-only).
4. On merge to `dev`: strike the completed milestones in `docs/roadmap.md`
   (standalone backend ✅, WS client reconnect/attach ✅).

## Merge review notes (Kimi, 2026-07-22)

Everything below is on `fix/remote-boot-integration`, stacked on
`fix/remote-observation-value-source` (already includes
`fix/backend-pin-live-mode` and `chore/py314-drop-profiling`). Verified
end-to-end against the maintainer's real config: backend + remote
frontend render the full dashboard on first paint.

**Why so many UI fixes:** first real-GUI runs in mode=remote surfaced a
chain of latent bugs in paths live mode never takes — data arriving
*before/at* panel load (the replay) instead of after. Each is covered by
a test; `tests/wire/test_remote_boot.py` (subprocess, real WireServer,
real OpenMeteo dashboard, zero-traceback assertion) is the guard rail.

Key changes to scrutinize:

- **`RemoteSource`/`RemoteContainer` surface gaps** — `hasRealtimeFor`,
  `hasTimeseriesFor`, `hourly/daily`, `.source` stand-ins
  (`_RemoteValueSource`, ABC-registered for streaming), and
  `notifyOnRequirementsMet` now mirrors `observation.Container`'s exact
  match-based signature (dispatcher calls it positionally).
- **`Graph.connectTimeseries` None guard** — documented 4.4 behavior
  (stay empty); was crashing `waitForLoadComplete`'s action chain, which
  is why *nothing* rendered on first real run.
- **`TimeOffsetLabel`** — was wired to a never-existent
  `qApp.instance().clock`; now a local QTimer (time is frontend-local by
  design; never crosses the wire).
- **`Text.updateText(*_ignored)`** — statekit's direct-call after-func
  branch passes the owner; the deferred branch passes nothing. Latent.
- **`MeasurementUnitSplitter` value visibility** — the big one. Lazily
  created at `connectRealtime` (mid-load in remote), base `__init__`'s
  `setGeometries` hides the ValueLabel on a degenerate ratio;
  `updateUnitDisplay`'s unit-hidden branches never un-hid it. Now they
  `value.show()` — matches stated intent, no-op in live.
- **Dispatcher wait short-circuit** — `getPreferredSourceContainer` now
  fires immediately when a qualifying container already exists (mirrors
  `checkAwaiting`'s conditions). Fixes the "placeholder for one full
  poll cycle" race; also closes the same race in live mode. This one is
  shared-code, worth the closest look.
- **Backend entry moved** — `LevityDash-backend` now points at
  `LevityDash.backend` (package-level) so `LEVITYDASH_BACKEND_MODE=live`
  is pinned before `LevityDash.lib` imports (entry-point import order
  made the old in-main() pin useless; the backend was self-connecting
  when config said remote). Requires `poetry install` after merge.
- **Codec derived units** — `_resolve_measurement_class` prefers
  canonical non-generic name, then non-generic symbol-carrier; '%' still
  resolves by class name. Registry by-symbol can return parametrized
  generic classes that can't build from a bare number.
- **Test config seed** — `LEVITYDASH_CONFIG_SEED` +
  `tests/resources/config-seed/` (established config: onboarding
  answered, real OpenMeteo dashboard) so integration tests don't run the
  fresh-install path. Unset it to test onboarding.

Not done / open: timeseries over wire (#3 above), `_latest` replay is
still last-batch-per-source (fine for current plugins, which publish
full batches; the cumulative-snapshot TODO in server.py stands),
float-under pair sync wart (pre-existing), the graph-annotation
`'NoneType' has no attribute 'view'` tracebacks seen once when poking
menubar views (couldn't reproduce; likely pre-existing detached-item
layout issue).
