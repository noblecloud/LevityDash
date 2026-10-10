# Task briefs — index

Self-contained briefs for work meant to be picked up in a fresh session or
by another agent. Each carries its own context, verification steps, and
suggested branch. See the root `CLAUDE.md` / `AGENTS.md` for conventions.

**Sync with `dev` before branching** — briefs and unrelated fixes land here
continuously.

Audited against `dev` on 2026-10-10. Where a brief's own header disagreed
with the merge history, the header now carries an **Audit** line. Status
words below come from the briefs plus the merges, not from a re-run of each
brief's verification steps.

---

**Start here:** [docs/roadmap.md](../roadmap.md) is the only roadmap. The
[session handoff of 2026-10-05](session-handoff-2026-10-05.md) is stale.

## Open — needs a decision from the maintainer

| brief | what's blocked on you |
|---|---|
| [dual-license-migration](dual-license-migration.md) | the licensing model itself; repo is still plain MIT |
| [value-annotations-and-digit-budget](value-annotations-and-digit-budget.md) § 3 | whether annotations v1 is derived-only, and the shape of the "micro leading zero" rendering. The digit budget itself has merged. |
| *(WeatherUnits)* [`parameter-audit.md`](../../../WeatherUnits/docs/parameter-audit.md) | param renames (`max` → ?, `unit_type` → `unitType`), which dead options to delete, and the library name |
| [roadmap open questions](../roadmap.md#plan-first-stable-cut-then-lanes) | who the first stable cut is for, and the lane order after it |

## Open — actionable

| brief | scope |
|---|---|
| [gauge-text-treatments](gauge-text-treatments.md) | optical centering — `98°` looks off-centre because `°` is light |
| [studio-snapping-guides](studio-snapping-guides.md) | Studio distance guides, ratio snapping and drag gearing. Branch `feat/studio-snapping` is not on `dev`. Next lane: Editor. |
| [warp-along-path](warp-along-path.md) | `warp:` takes a free path, plus a `bend` blend. Not started; `feat/warped-text` (circle warp) has merged. |
| [render-scenario-crash](render-scenario-crash.md) | `render_dashboard.py --scenario` SIGSEGVs on a full dashboard (a preset renders fine). Needs a fix or a finer bisect — suggested branch `fix/scenario-render-segv`. |
| [categoryitem-duplicate-keys](categoryitem-duplicate-keys.md) | duplicate `CategoryItem` keys in `dispatcher._values`; root cause not closed |
| [lambda-sizegroup-test-failures](lambda-sizegroup-test-failures.md) | two size-group tests fail on `lambda`, pass on the Mac. Low priority. |
| [gauge-display](gauge-display.md) | unclear (audit 2026-10-10): the `_majorDivisions` error may be fixed; value-label centring needs a render |
| [dashboard-redesign](dashboard-redesign.md) | unclear (audit 2026-10-10): the layout is installed; the sun-time cells and mini-gauge centring need a render |
| [dashboard-design-handoff](dashboard-design-handoff.md) | the weather boards: PR #54 and #60 merged; Station and Core + rotation still to finish. Paused 2026-10-06. |
| [timeseries-viewport-and-control-plane](timeseries-viewport-and-control-plane.md) | the plugin control plane's start/stop/restart commands (not started); a socket that stays bound but goes silent is not detected; no re-fetch when panning past the fetched window |
| [phase-4.2-follow-ups](phase-4.2-follow-ups.md) | loose ends from the backend/frontend split, which has merged |
| [render-service-and-surface-frontend](render-service-and-surface-frontend.md) | step 1 shipped (`devtools/render_service.py`); step 2 is still a design note (HUD lane, parked) |
| [dead-code-sweep](dead-code-sweep.md) | partly done. The commented-out-code portion needs a human pass. |
| [meter-and-bar](meter-and-bar.md) | `Scale` + `Track` split and `Gauge(Meter)` have landed (M3, PR #27). Phase 4 (progress, battery, segmented, thermometer, range bars) is open. |
| [meter-m2b-remaining](meter-m2b-remaining.md) | the rest of M2 and two side jobs. Follows [meter-and-bar](meter-and-bar.md). |
| [meter-harness-status](meter-harness-status.md) | phase 2 working note, in progress 2026-10-05. The `emissive` `NO_FREEZE` exemption stays. |
| [emissive-color-and-glow](emissive-color-and-glow.md) | phases 1 and 2 merged 2026-10-05. Phase 3 (border-beam painting engine moves into LevityDash) is open. |
| [gauge-tick-label-format](gauge-tick-label-format.md) | 1a–1c and 3 merged (`feat/tick-label-format-2`). Phase 2 is open and has design calls. |
| [gauge-presets](gauge-presets.md) | the `preset:` mechanism exists (`lib/presets.py`), and PR #64 merged. Preset library (PR #70) is open. The gauge-ui template list is still to do. |
| [value-sources](value-sources.md) | merged into `feat/value-sources`, which is on `dev`. The roadmap's "close out value-sources" step is still open. |
| [statekit-bindings](statekit-bindings.md) | partly merged; re-check items 1 to 3 before you start |
| [gradient-unit-stops](gradient-unit-stops.md) | merged; the running-dashboard edit mode is still open |
| [eventfilter-pending-exception](eventfilter-pending-exception.md) | root cause fixed 2026-07-28. A second `SystemError` was seen twice since, non-fatal, not reproducible. Parked until an always-on diagnostic catches it. |

## Design only — not started

| brief | what it is |
|---|---|
| [data-model-multi-domain](data-model-multi-domain.md) | research for a multi-domain data model (openHAB, Home Assistant, Grafana, Prometheus, OTel, InfluxDB, weather APIs). Not started. |
| [data-model-spec](data-model-spec.md) | config spec that goes with the research above. Not started. |
| [device-model-redesign](device-model-redesign.md) | the proposal for devices as first-class objects. Superseded in part by the data-model work. Not started. |
| [ble-launcher-app](ble-launcher-app.md) | a wrapper `.app` so BLE work doesn't need iTerm. Idea, low priority. |
| [experimental-maybe-never](experimental-maybe-never.md) | ideas recorded but not scheduled |

## Done — kept briefly so the same ground isn't re-covered

| brief | where it landed |
|---|---|
| [gauge-round-to-float](gauge-round-to-float.md) | `1789e18` on `dev`: sub-1 spans get a usable step |
| [beam-glow](beam-glow.md) | `feat/beam-glow`, merged 2026-10-06 |
| [text-baseline-alignment](text-baseline-alignment.md) | fixed 2026-07-26 |
| [dashboard-wont-load](dashboard-wont-load.md) | `808363c`, fixed 2026-09-08 |
| [graph-zero-time-range](graph-zero-time-range.md) | `d917135`, merged 2026-10-06 |
| [needle-glow-filled](needle-glow-filled.md) | `0d69fa5`, `14457d4`, merged 2026-10-06 |
| [emissive-upstream-check](emissive-upstream-check.md) | closed 2026-10-06 |
| [studio-value-sources](studio-value-sources.md) | `794dcd8`, merged 2026-10-06 |
| [meter-survey](meter-survey.md) | phase 1 of meter-and-bar, read-only, done |
| [meter-m3-recon](meter-m3-recon.md) | M3 landed (`38579f4`, `f519eed`) |
| [meter-merge-sync](meter-merge-sync.md) | the sync merge into the meter layout is merged |
| [meter-split-audit](meter-split-audit.md) | read-only audit of the meter split, complete; `refactor/meter` has merged |
| [dependabot-triage](dependabot-triage.md) | done; 43 alerts flagged for a follow-up decision in the triage doc |
| [schema-golden-fixture-tests](schema-golden-fixture-tests.md) | done for OpenMeteo, PirateWeather, WeatherFlow. Govee not attempted. |
| [govee-multi-device](govee-multi-device.md) | working since 2026-07-27 |
| [govee-multi-device-rewrite](govee-multi-device-rewrite.md) | merged into `dev` 2026-09-03 |
| [colour-decode-pr18-handoff](colour-decode-pr18-handoff.md) | PR #18 merged |
| [condition-pins-bisect](condition-pins-bisect.md) | PR #50 merged |
| [expr-keys-thickness-pins](expr-keys-thickness-pins.md) | `feat/expr-props`, merged |
| [shared-expression-panels-handoff](shared-expression-panels-handoff.md) | `shared-expr`, merged 2026-10-04 |
| [gauge-end-labels-handoff](gauge-end-labels-handoff.md) | `gauge-end-labels`, merged 2026-10-04 |
| [n1-fill-arc-handoff](n1-fill-arc-handoff.md) | `fill-value-sources`, merged 2026-10-04 |
| [curved-gauge-labels](curved-gauge-labels.md) | `feat/curved-gauge-labels`, merged 2026-10-04 |
| [studio-slider-smoke](studio-slider-smoke.md) | superseded by `studio-value-sources` (30/30 showcase cells load) |

## Loose ends not yet written up

- **`max` in `[UnitProperties]` only partly binds.** `precipitationRate =
  precision=2, max=2` — `precision` reaches `Hourly[in/hr]`, `max` does not
  (class ends up with `3`). Fuzzy class-name matching is the suspect. Means
  any `[UnitProperties]` line for a *derived* unit may be half-applied.
- **`environment.precipitation.probability` has no source.** OpenMeteo
  doesn't provide the key; only PirateWeather does, and nothing is
  connected — that figure renders empty.
- **WeatherUnits `SyntaxWarning`s** — `\s` in non-raw regex strings
  (`_SmartFloat.py:67,81`). Pre-existing; Python says these "will not work
  in the future."
- **`Angle` / `Direction` render a trailing space** (`'45° '`, `'S '`) from
  an empty unit plus a spacer. Cosmetic.
- **Public docs for WeatherUnits** — the original ask, deliberately blocked
  on the naming cleanup so they aren't written against a surface that needs
  apologising for.
- **Govee's schema golden tests** — the BLE payload parser has no golden
  fixture yet (see schema-golden-fixture-tests).

## Reference, not briefs

- [dashboard-traps](dashboard-traps.md) — `.levity` layout mistakes and the rule behind each one. Read it before hand-authoring a dashboard.
