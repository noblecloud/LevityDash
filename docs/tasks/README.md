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
| [meter-and-bar](meter-and-bar.md) | `Scale` + `Track` split out of `Gauge.py` (~6,299 lines) into a `meter/` package, `Meter(Display)` base, then `Bar(realtime.bar)` with progress/battery/segmented/thermometer/range presets. Phase 1 (survey) is done: [meter-survey](meter-survey.md). Phase 2 runs on `refactor/meter`: the split is done and verified step by step against the pixel harness, and the sync merge with `feat/value-sources` has landed (`5dea824`). M3 (`GaugeArc` into `meter/gauge.py`, `Gauge.py` a 16-line shim) has landed (`38579f4`, `f519eed`); the dial-geometry and `dependencies={'range','arc'}` questions it carried are settled in [meter-m3-recon](meter-m3-recon.md). Phase 4 waits on `feat/studio-snapping`. |
| [meter-survey](meter-survey.md) | phase 1 output of [meter-and-bar](meter-and-bar.md): every angle/radius site in `Gauge.py` grouped by class, what each becomes under `Scale`/`Track`, the arc-only remainder, the risks, and the proposed `meter/` file split. Read-only; awaiting review before phase 2. |
| [meter-harness-status](meter-harness-status.md) | phase 2 working note: the harness renders 37 targets on `dev` (36 presets plus `gauge-showcase`; 38 once `feat/meter-showcase` lands its second board), and `emissive` keeps a live clock behind one named mask (`graph-figure`): the `Graph.py` zero-range divide is guarded now, but a frozen clock still SIGSEGVs a graph preset. Also the clock-pin fix, the two queued gauge-track asks, and the findings to report. |
| [render-scenario-crash](render-scenario-crash.md) | `render_dashboard.py --scenario` SIGSEGVs on a full dashboard (a preset renders fine): the repro, what was ruled out, the faulting stack, and where to look. Needs a fix or a finer bisect — suggested branch `fix/scenario-render-segv`. |

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

- **Station, Storm, Sky and Week boards** ([#54](https://github.com/noblecloud/LevityDash/pull/54), [#60](https://github.com/noblecloud/LevityDash/pull/60)) — the Station board is from [dashboard-design-handoff](dashboard-design-handoff.md). All four are in `docs/design-references/boards/`.
- **Whole-module presets and saved gauges and bars** ([#64](https://github.com/noblecloud/LevityDash/pull/64), [#66](https://github.com/noblecloud/LevityDash/pull/66)), and a saved text keeps its theme font ([#69](https://github.com/noblecloud/LevityDash/pull/69)).
- **Deterministic unit localisation** ([#68](https://github.com/noblecloud/LevityDash/pull/68), WeatherUnits [#7](https://github.com/noblecloud/WeatherUnits/pull/7)): the `[Units]` config is read explicitly, not by import order.
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
- [beam-glow](beam-glow.md) — the border-beam pieces take a `glow:` (stroked on the beam's
  outline, filled on its card), with a Studio control and an opt-in preset.
- **[graph-zero-time-range](graph-zero-time-range.md)** — `Graph.normalize()` guards the
  x divide (`Graph.py:884`) and pins a zero-span series to the left edge;
  `pos_px_to_value` takes its single sample. On `dev` (`d917135`), pinned by
  `tests/ui/test_graph_zero_time_range.py`. Guarding the divide did **not** let the
  harness drop `emissive`'s `NO_FREEZE` — a frozen clock still SIGSEGVs a graph preset.
- **[needle-glow-filled](needle-glow-filled.md)** — a filled shape's halo starts flush
  with its outline: the needle's paint passes `filled=True` and the shape's own
  thickness, not the pen width. On `dev` (`0d69fa5`, `14457d4`), pinned by
  `tests/ui/test_glow_filled.py`.
- **[emissive-upstream-check](emissive-upstream-check.md)** — the emissive render
  instability is pre-existing, not the meter refactor's: a frozen clock plus a graph
  preset is the trigger. Closed; `emissive` keeps its `NO_FREEZE` exemption.

- **[value-sources.md](value-sources.md)**
  — every value slot in a `.levity` file (panel key, gauge markers, range
  bounds, colour) takes a key, a number or an expression
  (`max(environment.temperature.temperature, today)`, maths between keys,
  `x if cond else y`). Evaluated on the backend as computed keys. First
  slice: a gauge with today's high/low markers. Merges the former
  computed-values and value-driven-display-properties briefs.

- **[experimental-maybe-never.md](experimental-maybe-never.md)** - ideas recorded but not scheduled; currently distance-tolerant size matching.
- **[curved-gauge-labels.md](curved-gauge-labels.md)** - bend gauge graduation labels along the arc - warping the glyph OUTLINES, not placing characters along a curve (that has been tried and looks faceted). A non-affine warp, so the path must be flattened and every point remapped into polar space.
