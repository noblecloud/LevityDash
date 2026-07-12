# LevityDash project review

*2026-07-12, v0.2.0-beta.3, on `dev`. Companion to [schema-pipeline.md](schema-pipeline.md) (deep-dive on the data-ingestion engine). Numbers below were gathered from the tree, not estimated.*

## Snapshot

~40k lines of Python across three packages (`LevityDash`, `statekit`, `qolkit`). Runs daily on Python 3.14 + PySide6 6.11 with four live data sources. The 2026 revival paid down the worst debt: the tree is committed and pushed, the graph pipeline is off the GUI thread, text fitting was rewritten stateless, the state layer was extracted into a Qt-free package with tests, and the modern-floor migration (3.11→3.14, Qt 6.6→6.11, numpy 1.x→2.x) is complete and verified live.

**Overall: a genuinely ambitious architecture in mid-transition, healthier than it's been in years, with debt now concentrated in a few known places rather than everywhere.**

## What's strong

- **The layering bet is paying off.** `qolkit ← statekit ← LevityDash` with a Qt facade (`lib/stateful.py`) meant extracting 3,300 lines of state machinery without touching a single consumer. The same facade trick is the template for the Phase 4 split.
- **The declarative surfaces are the project's identity and they're good**: schema dicts make a REST plugin ~90% data; `.levity` YAML + StateProperty round-trips make dashboards fully text-editable; the size-group system gives designed-feeling typography for free.
- **The data model anticipates the vision.** `{key → MultiSourceContainer}` with per-source reconciliation already models "a device is just another source" — the HUD-node future drops into it rather than fighting it.
- **Test culture took root this cycle**: 64 tests (24 qolkit, 15 statekit, 25 UI incl. headless dashboard boots). The headless harness (`tests/conftest.py`) is the quiet MVP — it made every regression this cycle catchable offscreen.
- **Zero bare `except:`, zero `type: ignore`** — the escape hatches in use are at least visible ones.

## Where the risk is concentrated

**1. Five files are half the complexity.** Graph.py (4,408), Gauge.py (3,745), Geometry/`__init__.py` (3,522), observation.py (3,008), statekit/core.py (2,548). Within observation.py, `MeasurementTimeSeries` alone is 494 lines and `Container` 322 — both slated to shrink dramatically when Phase 4 moves series ownership backend-side, which is the right call (don't refactor what the split deletes).

**2. The plugin/data layer has no tests at all.** Not one test touches `lib/plugins/` — the schema engine, dispatcher, observation containers, or any builtin plugin. This is the layer with the most exotic logic and the least type safety (see the schema review's bug list: several of those bugs are only alive because nothing exercises the paths). Golden fixtures (captured JSON → expected datagram) are the cheapest possible entry point.

**3. `except Exception` as load-bearing infrastructure: 80 occurrences.** Worst: statekit/core.py (9), backend.py (9), observation.py (7). Some are legitimately defensive (YAML loading arbitrary user files), but the observation.py ones silently degrade data conversion — a schema bug becomes a cosmetic oddity instead of an error. A logging pass (keep the catch, make it loud once) would cost an hour and pay forever.

**4. Commented-out code is heavy in the UI tier.** Grid.py (~163 commented statements — much of the file), AttributeEditor (~95), Drawer.py (~85), Graph.py/Gauge.py (~82 each). Grid.py and AttributeEditor read as abandoned experiments; the git history preserves them, and deleting would make the live code paths much easier to follow.

**5. Confirmed dead code** (verified zero import sites): `lib/exceptions/` (4-line package, never imported), `lib/utils/debug.py` (imports the Qt shim, defines one unused function), `lib/backend.py` (403 lines — known, being rebuilt in Phase 4), and OpenWeatherMap (schema shadowed by an empty class attr, `__plugin__` export commented out — a skeleton, not a plugin). The two `.ignore` plugins are deliberate.

**6. Qt still reaches into the data layer in exactly 4 files**: dispatcher.py, observation.py, plugins/utils.py, web/socket_.py (Signals/QTimer/QThread). This is the known Phase 4 seam, already mapped — listed here because it's the complete list, and it's short enough to be encouraging.

**7. 65 TODOs, all `TODO` (no FIXME/HACK).** A handful are load-bearing warnings worth promoting to issues: `observation.py:2368` "Add a lock to this operation", `WeatherFlow:501` "possible crashing bug on first scheduled run", `Stacks.py:880` "probably the worst way to do this". Four `color.py` TODOs say "AI Generated - varify accuracy" — worth an afternoon with a color picker.

**8. Import-order gymnastics.** Local imports as circular-dependency workarounds cluster in config.py, app.py, and PySide/utils.py. Mostly benign, but they're the symptom of the same coupling Phase 4 untangles; `backend.py` importing `LevityDashboard` five separate times inside functions is the caricature version.

## Dependency & platform health

- Floors are modern and pinned where it matters (PySide6 pinned after the 6.11-on-3.11 incident; aiohttp's C-extension transitives floored for 3.14 wheels). `appdirs` is abandoned upstream but works; revisit only on breakage.
- The GitHub push flagged 109 Dependabot alerts — many predate the floor bumps and are likely stale; an hour of triage would clear the noise and surface any real ones.
- Packaging (PyInstaller 6) is unblocked but unverified on the new stack; the PyPI package is two years stale (0.1.x, PySide2-era) — worth either publishing 0.2.0 or yanking to stop misleading `pip install`s.

## What I'd do next, in order

1. **Ship Phase 4.1** (wire codec → `RemoteContainer` → loopback). Everything else on this list gets easier after the seam exists, and several debt items (MeasurementTimeSeries, Qt-in-data-layer, backend.py) are deleted by it rather than fixed.
2. **Golden-fixture tests for the schema engine** + the two one-line bug fixes from the schema review (`getUnitMetaData`'s `k`/`key`, OpenWeatherMap's shadowed schema — or delete the skeleton). First tests in the most-exotic, least-tested layer.
3. **Loud-failure pass on the silent fallbacks** (conversion `except Exception`, fuzzy key matching) behind a dev-mode flag.
4. **Dead-code sweep**: `lib/exceptions/`, `utils/debug.py`, Grid.py's commented mass, AttributeEditor. Low risk, big readability dividend. (backend.py dies naturally in Phase 4.2.)
5. **Dependabot triage + decide the PyPI story** for 0.2.0.

Deliberately *not* on the list: splitting Graph.py/Gauge.py (works, tested by usage, no active bug pressure — split opportunistically when features force it), swapping appdirs, and any schema-engine rewrite beyond what the schema review recommends.
