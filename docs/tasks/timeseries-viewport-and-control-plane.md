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

That real run also surfaced two things intentionally left out of that
milestone's scope — tracked here rather than assumed solved.

## 1. Wire-fetched window isn't viewport-aware

`RemoteContainer.prepare_for_ts_connection` always requests a fixed ±3h
window (`_DEFAULT_MIN_PERIOD`/`_DEFAULT_MAX_PERIOD` in both `containers.py`
and `messages.py`), mirroring `Container.timeseries`'s own construction
default. But a real `Container`'s `MeasurementTimeSeries`, once populated,
holds all available history — `Graph.py`'s own slicing
(`self.timeseries[self.graph.timeframe.historicalStart:end]`) is what
narrows that down to whatever the Graph panel is actually configured to
show (which can be much wider than 3h either side of now). A
`RemoteContainer` has no equivalent: whatever ±3h the backend sent is *all*
it will ever have, so a Graph configured for e.g. a 24h view will render a
visibly truncated series in remote mode.

Real fix needs either:
- Threading the Graph's actual configured timeframe into the wire request
  (Graph would need to expose it somewhere `prepare_for_ts_connection` can
  reach, without importing Graph.py into `lib/wire/` — probably a param on
  `MultiSourceContainer.getPreferredSourceContainer`/`prepare_for_ts_connection`
  itself), or
- Re-fetching on pan/zoom when the requested slice exceeds what's cached
  (closer to how a real paginated API client would behave).

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

## 3. Plugin control plane

Not started: watchdog heartbeats and remote start/stop/health lifecycle for
backend-hosted plugins. Independent of the two items above.
