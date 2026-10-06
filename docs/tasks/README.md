# Task briefs — index

Self-contained briefs for work meant to be picked up in a fresh session or
by another agent. Each carries its own context, verification steps, and
suggested branch. See the root `CLAUDE.md` / `AGENTS.md` for conventions.

**Sync with `dev` before branching** — briefs and unrelated fixes land here
continuously.

---

**Start here:** [session-handoff-2026-10-05](session-handoff-2026-10-05.md) is the state of play for a fresh session: branch, rules, work in flight, open decisions and known bugs.

## Open — needs a decision from the maintainer

| brief | what's blocked on you |
|---|---|
| [dual-license-migration](dual-license-migration.md) | the licensing model itself; repo is still plain MIT |
| [value-annotations-and-digit-budget](value-annotations-and-digit-budget.md) § 3 | whether annotations v1 is derived-only, and the shape of the "micro leading zero" rendering |
| *(WeatherUnits)* [`parameter-audit.md`](../../../WeatherUnits/docs/parameter-audit.md) | param renames (`max` → ?, `unit_type` → `unitType`), which dead options to delete, and the library name |

## Open — actionable without input

| brief | scope |
|---|---|
| [statekit-bindings](statekit-bindings.md) | statekit: validate with a reason, notify on real change with old value, one-way `bind` to a value source (ideas from traitlets) |
| [timeseries-viewport-and-control-plane](timeseries-viewport-and-control-plane.md) | plugin control plane (start/stop/health); also no re-fetch when panning past the fetched window |
| [text-baseline-alignment](text-baseline-alignment.md) | graph hour labels — descenders (`12p`) shift them relative to `6a`; align by font metric, not ink extents |
| [eventfilter-pending-exception](eventfilter-pending-exception.md) | parked: a `SystemError` seen once, non-fatal, not reproducible. Wants an always-on diagnostic to catch it live |
| [phase-4.2-follow-ups](phase-4.2-follow-ups.md) | remaining odds from the backend/frontend split |
| [gauge-tick-label-format](gauge-tick-label-format.md) | tick labels read `28.00` on a 1-inHg scale — units carry a compact (dial-face) format in WeatherUnits, tick spacing as the floor; then dashboard-level format `defaults:` (matcher design open) |
| [gauge-round-to-float](gauge-round-to-float.md) | fixed on `fix/gauge-round-to-float`: a gauge narrower than 1 unit died in `__init__` (`round_to` returned `1e-323`); then drew no graduations (`rounded_max`, float floor/ceil) |
| [gauge-text-treatments](gauge-text-treatments.md) | optical centering — `98°` looks off-centre because `°` is light |
| [gauge-presets](gauge-presets.md) | named `preset:` for gauges, one per gauge-ui template (29 rows); which of seven missing gauge primitives unlocks which; blocked first on [gauge-display](gauge-display.md) |
| [meter-and-bar](meter-and-bar.md) | `Scale` + `Track` split out of `Gauge.py` (~6,299 lines) into a `meter/` package, `Meter(Display)` base, then `Bar(realtime.bar)` with progress/battery/segmented/thermometer/range presets. Phase 1 (survey) is done: [meter-survey](meter-survey.md). Phase 2 runs on `refactor/meter`: the split is done and verified step by step against the pixel harness, and the sync merge with `feat/value-sources` has landed (`5dea824`). M3 (`GaugeArc` into `meter/gauge.py`, `Gauge.py` a ~30-line shim) waits on that merge's review and carries the dial-geometry and `dependencies={'range','arc'}` questions — see [meter-m3-recon](meter-m3-recon.md). Phase 4 waits on `feat/studio-snapping`. |
| [meter-survey](meter-survey.md) | phase 1 output of [meter-and-bar](meter-and-bar.md): every angle/radius site in `Gauge.py` grouped by class, what each becomes under `Scale`/`Track`, the arc-only remainder, the risks, and the proposed `meter/` file split. Read-only; awaiting review before phase 2. |
| [meter-harness-status](meter-harness-status.md) | phase 2 working note: the harness renders 24 targets (23 presets plus the showcase) and the merged tree is 24/24 clean across captures; `emissive` keeps a live clock (the freeze trips `Graph.py:862`) behind two named masks, and the baseline is `.render-diff/merged-a`. Also the clock-pin fix, the two queued gauge-track asks, and the findings to report. |
| [render-scenario-crash](render-scenario-crash.md) | `render_dashboard.py --scenario` SIGSEGVs on a full dashboard (a preset renders fine): the repro, what was ruled out, the faulting stack, and where to look. Needs a fix or a finer bisect — suggested branch `fix/scenario-render-segv`. |
| [graph-zero-time-range](graph-zero-time-range.md) | `Graph.py:862` divides by a zero-second time range (the y axis guards its own range, the x axis does not): NaN x-coordinates, a plot that drifts between captures, and in about half the harness runs a shutdown SIGSEGV. A live-board risk, not just harness noise; fixing it also lets the harness drop `emissive`'s workarounds. |

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

## Recently completed

Kept briefly so the same ground isn't re-covered.

- **[studio-value-sources](studio-value-sources.md)** — the Studio's value-source
  stand-in now registers in `lib/valuesource` and `openValueSource` consults it,
  so keyed markers/fills/captions resolve wherever their consumer lives; and a
  numeric field decodes against the class the build assigns, so the settle/rebuild
  path no longer calls a `None` class. 13/30 -> 30/30 showcase cells load. Pinned
  by `tests/devtools/test_studio_value_sources.py`.
- **Digit budget** — `max` now applies to values ≤ 1; `leadingZero`
  implemented as three-state with an `auto` default. The `auto` rule is
  documented in `WeatherUnits/docs/formatting.md` along with two rejected
  simplifications of it.
- **Degree sign** — the whole codebase rendered `º` U+00BA (ordinal
  indicator), not `°` U+00B0. Normalized, with a test pinning the codepoint.
- **Formatting reference** — `WeatherUnits/docs/formatting.md`, every
  example executed rather than predicted.
- **`defaultFor` ignored for graphs** — `getPreferredSourceContainer` took
  the first ready container instead of ranking, unlike the other three
  accessors.
- **Source menus empty in `mode=remote`** — they enumerated local plugins,
  which are loaded but never started in that mode.
- **Derived units degraded to bare floats over the wire** — precipitation
  rate rendered as raw float64 digits.
- [dead-code-sweep](dead-code-sweep.md), [dependabot-triage](dependabot-triage.md),
  [schema-golden-fixture-tests](schema-golden-fixture-tests.md) — done.

- **[value-sources.md](value-sources.md)**
  — every value slot in a `.levity` file (panel key, gauge markers, range
  bounds, colour) takes a key, a number or an expression
  (`max(environment.temperature.temperature, today)`, maths between keys,
  `x if cond else y`). Evaluated on the backend as computed keys. First
  slice: a gauge with today's high/low markers. Merges the former
  computed-values and value-driven-display-properties briefs.

- **[experimental-maybe-never.md](experimental-maybe-never.md)** - ideas recorded but not scheduled; currently distance-tolerant size matching.
- **[curved-gauge-labels.md](curved-gauge-labels.md)** - bend gauge graduation labels along the arc - warping the glyph OUTLINES, not placing characters along a curve (that has been tried and looks faceted). A non-affine warp, so the path must be flattened and every point remapped into polar space.
