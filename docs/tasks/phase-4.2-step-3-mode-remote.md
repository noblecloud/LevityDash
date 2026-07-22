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

## Follow-ups (not started)

1. **Derived-unit wire support** — Wind/rate measurements degrade to plain
   floats over the wire (generic class can't build from a bare number; see
   `codec.py decode_measurement`'s second degrade branch). Loopback silently
   skipped these keys all along. Needs either specialized-class naming in the
   registry or a richer measurement envelope. Unitless wind = the one known
   render delta vs live.
2. **Full identical-render check** — headless dispatcher parity is proven;
   the pixel-level bar (like 4.1's) and a real-GUI run against the user's
   actual config/backend still to do. NOTE: the Govee/BLE TCC gotcha now
   applies to whatever terminal launches the *backend*.
3. **Timeseries + plugin control plane** — the next roadmap milestone
   (graphs in remote mode have no timeseries source yet; realtime-only).
4. On merge to `dev`: strike the completed milestones in `docs/roadmap.md`
   (standalone backend ✅, WS client reconnect/attach ✅).
