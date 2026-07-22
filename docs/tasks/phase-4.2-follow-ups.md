# Phase 4.2 follow-ups (split is merged & live; these are the loose ends)

The backend/frontend split shipped on `dev` (merge `fce2568`): `LevityDash-backend`
serves, `[Backend] mode = remote` renders the full dashboard on first paint.
History/context: the phase branch's commit messages and Kimi's merge review
notes (this file's history at `1592e15`).

## Open items

1. **Timeseries + plugin control plane** — the next roadmap milestone. Graphs
   in remote mode stay empty by design until it lands (realtime-only today;
   `Graph.connectTimeseries` has the documented None-guard for this gap).
2. **`WireServer._latest` cumulative snapshot** — replay is last-batch-per-
   source; fine while plugins publish full batches, but the merge-into-a-
   cumulative-snapshot TODO in `lib/wire/server.py` stands before any plugin
   publishes partial updates.
3. **Float-under pair sync wart** — pre-existing (not remote-specific);
   recursion-prone autofit per the maintainer. Untracked elsewhere.
4. **Unreproduced traceback** — `'NoneType' has no attribute 'view'` from
   graph annotations, seen once while poking menubar views during remote
   testing; likely a pre-existing detached-item layout issue.

## Operational notes

- The Govee/BLE macOS TCC gotcha now applies to whatever terminal launches
  the **backend** (it owns the plugins).
- `LEVITYDASH_CONFIG_SEED` (see AGENTS.md Test quirks) seeds test config dirs
  with an established config; unset it to exercise onboarding/fresh-install.
