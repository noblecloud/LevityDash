# Phase 4.2 — Step 3: separate backend process + `mode=remote`

**Branch:** `feat/phase-4.2-backend-split` (Steps 1–2 committed there, not merged to `dev`).
**Status:** open — this is the big one.

## Where Steps 1–2 left it

- `lib/wire/messages.py` — `encode_container` / `apply_container_update`: the shared wire-message pair. `LoopbackBridge` uses both; the server/client each use one.
- `lib/wire/server.py` — `WireServer` (aiohttp WS): `start/stop/broadcast`, replays latest per-source snapshot to late clients. **Transport only** — nothing feeds `broadcast()` yet.
- `lib/wire/client.py` — `WireClient`: connects, read loop, hands each decoded message dict to an `on_message` callback. **Transport only** — nothing applies messages yet.
- Both proven over a real socket in `tests/wire/test_wire_transport.py`.

## What Step 3 connects (mostly wiring existing pieces)

1. **Frontend adapter** (`mode=remote`) — a `WireBridge`-style class mirroring `LoopbackBridge._on_published`, but fed by `WireClient.on_message` instead of a local `Publisher`: parse the envelope → `getOrCreate` the `RemoteSource` (name/defaultFor/enabled/running from `message['source']`) → `apply_container_update` per key → `dispatcher.update(remoteValues)`. Wire it in `dispatcher.py` where `mode == 'loopback'` picks `LoopbackBridge` (~line 508): add `mode == 'remote'` → run a `WireClient` pointed at the backend.
2. **`encode_update_message`** — add to `messages.py` (the envelope builder Step 2 deferred): `{v, type:'update', source:{...}, updates:{str(key): encode_container(c)}}`. The backend calls it on each plugin publish, then `WireServer.broadcast()`.
3. **Backend process** — rebuild `lib/backend.py`'s `main()`: run the `PluginManager` + plugins **headless** and feed publishes into `WireServer.broadcast()`.
4. **Reconnect/backoff** in `WireClient` (or the adapter).

## The real risk (flagged in the roadmap)

The backend still needs **Qt** — `Publisher` is a `QObject`, `ScheduledEvent` uses `QTimer` — so the backend runs a headless `QCoreApplication` (no GUI) alongside aiohttp's asyncio loop. The app already marries asyncio+Qt for REST plugins; follow that pattern. **The GUI-less asyncio/Qt event-loop integration is the hard part of this step.**

Also honor the roadmap requirement: the frontend adapter must marshal every incoming update **onto the GUI thread once** at the wire→frontend seam (this is where the QBasicTimer startup-burst fix lands; supersedes the piecemeal `startTimerSafe` wrapping).

## Verify

`mode=remote` frontend + separately-launched backend renders **identically** to `mode=loopback` / `live` — same bar as 4.1's identical-render check.
