# Follow-ups from timeseries-over-wire

The timeseries-over-wire milestone shipped: `RemoteContainer.timeseries` is
now populated via a real request/response round trip (`lib/wire/codec.py`'s
columnar encode/decode, `messages.py`'s `ts_request`/`ts_response`, unicast
dispatch in `server.py`, correlation in `client.py`, the Qt/asyncio two-hop
handler in `backend.py`, and the `RemoteTimeSeries` stand-in in
`containers.py`). Graphs in `mode=remote` now populate with real data
instead of the permanent None-guard. Full path verified against a real
two-process run (`LevityDash-backend` + `LevityDash` with `mode=remote`), not
just unit tests.

That real run also surfaced things intentionally left out of that
milestone's scope — tracked here rather than assumed solved.

## 1. ~~Wire-fetched window isn't viewport-aware~~ — fixed

`RemoteContainer.prepare_for_ts_connection` used to always request a fixed
±3h window (`_DEFAULT_MIN_PERIOD`/`_DEFAULT_MAX_PERIOD`), mirroring
`Container.timeseries`'s own construction default. But a real `Container`'s
`MeasurementTimeSeries`, once populated, holds all available history —
`Graph.py`'s own slicing (`self.timeseries[self.graph.timeframe.historicalStart:end]`)
is what narrows that down to whatever the Graph panel is actually configured
to show. A `RemoteContainer` had no equivalent: whatever ±3h the backend
sent was *all* it would ever have, so a Graph configured for a wider view
rendered a visibly truncated series in remote mode (confirmed: a real
temperature curve reduced to a tiny sliver against a multi-day axis).

Fixed via a duck-typed capability query rather than threading a new param
through `dispatcher.py`'s shared `getPreferredSourceContainer` plumbing
(lower blast radius, zero risk to the live-mode path): `GraphItemData` now
exposes `.wireTimeseriesPeriod -> (timedelta, timedelta)` (Graph.py, derived
from `self.graph.timeframe.lookback`/`.range` — the exact same fields
`.list` already uses to slice), and `RemoteContainer.prepare_for_ts_connection`
reads it off `request.requester` via `getattr(..., 'wireTimeseriesPeriod', None)`,
falling back to the old default when absent or malformed. `request.requester`
was previously only ever used for identity (hashing/logging) — this is a
deliberate, narrow, backward-compatible extension of that contract, not a
pre-existing one, and it required zero changes to `dispatcher.py` or the
backend (which already honored whatever `minPeriod`/`maxPeriod` a request
carried). Verified both by unit test (`tests/wire/test_containers.py`) and
visually — a real remote-mode screenshot (via an on-screen-then-`.grab()`
harness, no browser/computer-use tooling needed) now shows the temperature/
cloud-cover curves spanning the full multi-day configured timeframe instead
of a sliver near "now".

## 2. ~~Graph.py's smoothing isn't robust to too-few-points~~ — fixed

Confirmed live against a real two-process remote-mode session: with a small
dataset in the ±3h window above (OpenMeteo hourly data ≈ 6-7 points across
6h), `GraphItemData.data`'s smoothing branch raised
`ValueError: If mode is 'interp', window_length must be less than or equal
to the size of x` repeatedly (once per redraw, printed to stderr - not
silently swallowed as first assumed). Fixed by clamping `sf` to the
available odd point count and skipping smoothing below the polyorder floor,
rather than assuming a live-mode-sized series. Not remote-specific in
principle (a live Container fed a similarly sparse window would hit the
same crash), but item 1 above made it far more likely to actually occur in
remote mode.

## 3. Plugin control plane — health done, start/stop still open

**Landed 2026-07-27: the read-only half.** Two backend→frontend message types
in `messages.py`, deliberately separate:

- **`heartbeat`** — small, unconditional, every `_HEARTBEAT_INTERVAL` (5s,
  `lib/backend.py`). Carries `seq` + `uptime`. This is the liveness signal;
  silence on the update channel is *normal* for a weather backend on a slow
  poll, so update traffic says nothing about health.
- **`plugin_status`** — per-plugin `{enabled, running, keyCount, lastPublish}`,
  sent **on change only**, plus replayed by `WireServer` to each late joiner
  (`_latestStatus`). A heartbeat is deliberately *not* retained for replay —
  it would assert liveness the backend hasn't demonstrated.

Frontend: `RemoteConnection.plugins` (`{name: PluginState}`) + `pluginsChanged`
Signal, paired the same way `state`/`connectionStateChanged` already are.
`backendAlive` is the watchdog — distinct from `state == 'connected'`, because
a wedged Qt loop keeps its socket open. That's also why `tick()` is a QTimer on
the **Qt main thread**: a wedged loop stops the heartbeat, which an
aiohttp-level ping would keep reporting as healthy.

A backwards `seq` means a different backend process is answering (restart under
a surviving socket); the frontend clears its plugin snapshot rather than
showing the old process's state.

### Two bugs the two-process run caught that unit tests did not

- **`len(plugin)` raises `TypeError`.** `Plugin` defines no `__len__` — the
  one nearby in `plugin.py` belongs to its observation-class dict. An
  over-broad `except` reported **0 keys for every plugin**, including busy
  ones. Real source is `plugin.keys()`; verified live at 451/270/15 keys.
- **A failed `plugin_status` send must not update the "unchanged" cache**, or
  one transient failure suppresses that snapshot permanently. Now only
  recorded after the send succeeds.

Live verification (`LevityDash-backend` + a real `WireClient`): heartbeats
ticking with incrementing seq, late joiner receiving the replayed status
immediately, one status in 12s (change-suppression holding), and
`OpenWeatherMap` showing `keys=15, lastPublish=None` — registered but not yet
publishing, a distinction that only exists because these are separate fields.

⚠️ Reproducing this needs a Govee-free config (`LEVITYDASH_CONFIG_SEED`) —
otherwise the backend `SIGABRT`s at startup on Bluetooth/TCC, per CLAUDE.md.

**Still open:** frontend→backend `start`/`stop`/`restart` commands, and any UI.
The health half was built first deliberately — commands land on top of it
without reshaping anything above.

## Still open, not yet tackled

- **No re-fetch on pan/zoom.** The fix above matches the *initial* fetch to
  the Graph's configured timeframe, but if a user pans/zooms a scrollable
  Graph beyond that window in remote mode, there's still no re-fetch —
  `RemoteTimeSeries` is a one-shot snapshot (see its docstring). Real fix
  would need `Graph.py` to notice a requested slice exceeds what's cached
  and re-issue a request, closer to how a paginated API client behaves. Not
  attempted here — lower priority than the control plane, and no evidence
  yet that any real dashboard actually scrolls a remote-backed Graph.
