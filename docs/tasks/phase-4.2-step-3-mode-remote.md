# Phase 4.2 — Step 3: separate backend process + `mode=remote`

**Branch:** `feat/phase-4.2-backend-split` (Steps 1–2 committed there, not merged to `dev`).
**Status:** open — this is the big one.

## Where Steps 1–2 left it

- `lib/wire/messages.py` — `encode_container` / `apply_container_update`: the shared wire-message pair. `LoopbackBridge` uses both; the server/client each use one.
- `lib/wire/server.py` — `WireServer` (aiohttp WS): `start/stop/broadcast`, replays latest per-source snapshot to late clients. **Transport only** — nothing feeds `broadcast()` yet.
- `lib/wire/client.py` — `WireClient`: connects, read loop, hands each decoded message dict to an `on_message` callback. **Transport only** — nothing applies messages yet.
- Both proven over a real socket in `tests/wire/test_wire_transport.py`.

## What Step 3 connects (mostly wiring existing pieces)

1. ~~**Frontend adapter**~~ ✅ **DONE** (`c66cfa8`) — `wire/frontend.py` `RemoteFrontend`: `handle_message(update)` → `getOrCreate` `RemoteSource` → `apply_container_update` per key → hands `{key: RemoteContainer}` to a callback. Tested standalone.
2. ~~**`encode_update_message`**~~ ✅ **DONE** (`c66cfa8`) — envelope builder + `parse_update_message` in `messages.py`.
3. **Wire `RemoteFrontend` into `dispatcher.py`** under `mode == 'remote'` (where `mode == 'loopback'` picks `LoopbackBridge`, ~line 508): run a `WireClient` pointed at the backend with `on_message = RemoteFrontend(self.update).handle_message`. **Not done** — needs the app's asyncio loop running the client.
4. **Backend process** — build messages from live plugin publishes (`encode_update_message` + `encode_container` per changed key) → `WireServer.broadcast()`; rebuild `lib/backend.py`'s `main()` to run the `PluginManager` + plugins **headless** and serve. **Not done — the hard part.**
5. **Reconnect/backoff** in `WireClient` (or the adapter). **Not done.**

## The real risk (flagged in the roadmap)

The backend still needs **Qt** — `Publisher` is a `QObject`, `ScheduledEvent` uses `QTimer` — so the backend runs a headless `QCoreApplication` (no GUI) alongside aiohttp's asyncio loop. The app already marries asyncio+Qt for REST plugins; follow that pattern. **The GUI-less asyncio/Qt event-loop integration is the hard part of this step.**

Also honor the roadmap requirement: the frontend adapter must marshal every incoming update **onto the GUI thread once** at the wire→frontend seam (this is where the QBasicTimer startup-burst fix lands; supersedes the piecemeal `startTimerSafe` wrapping).

## Verify

`mode=remote` frontend + separately-launched backend renders **identically** to `mode=loopback` / `live` — same bar as 4.1's identical-render check.
