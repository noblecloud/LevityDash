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

## 2. Graph.py's smoothing isn't robust to too-few-points

Confirmed live: with a small dataset in the ±3h window above (OpenMeteo
hourly data ≈ 6-7 points across 6h), `GraphItemData.data`'s smoothing branch
(`Graph.py`, `savgol_filter(y, sf, 2)`) can raise
`ValueError: If mode is 'interp', window_length must be less than or equal
to the size of x` when the computed smoothing window (`sf`, derived from
DPI/resolution/strength) exceeds the point count. The existing guard
(`if self.smooth and len(x) > 5`) only checks for "more than 5 points," not
"enough points for this specific `sf`."

Not remote-specific — a live Container fed a similarly sparse window would
hit the same crash — but item 1 above makes it more likely to actually
occur in remote mode until viewport-aware fetching lands. Currently
non-fatal (the thread-pool worker's exception path catches and logs it,
confirmed via a real run — the app keeps running, just skips that redraw),
so this is a robustness/noise issue, not a crash-the-app one. Fix: clamp
`sf` to `min(sf, len(x) - (len(x) % 2 == 0))` (savgol needs an odd window
length ≤ sample count) before calling `savgol_filter`, or skip smoothing
entirely when `sf` doesn't fit.

## 3. Plugin control plane

Not started: watchdog heartbeats and remote start/stop/health lifecycle for
backend-hosted plugins. Independent of the two items above.
