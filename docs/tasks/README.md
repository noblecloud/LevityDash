# Task briefs — index

Self-contained briefs for work meant to be picked up in a fresh session or
by another agent. Each carries its own context, verification steps, and
suggested branch. See the root `CLAUDE.md` / `AGENTS.md` for conventions.

**Sync with `dev` before branching** — briefs and unrelated fixes land here
continuously.

---

## Open — needs a decision from the maintainer

| brief | what's blocked on you |
|---|---|
| [dual-license-migration](dual-license-migration.md) | the licensing model itself; repo is still plain MIT |
| [value-annotations-and-digit-budget](value-annotations-and-digit-budget.md) § 3 | whether annotations v1 is derived-only, and the shape of the "micro leading zero" rendering |
| *(WeatherUnits)* [`parameter-audit.md`](../../../WeatherUnits/docs/parameter-audit.md) | param renames (`max` → ?, `unit_type` → `unitType`), which dead options to delete, and the library name |

## Open — actionable without input

| brief | scope |
|---|---|
| [timeseries-viewport-and-control-plane](timeseries-viewport-and-control-plane.md) | plugin control plane (start/stop/health); also no re-fetch when panning past the fetched window |
| [text-baseline-alignment](text-baseline-alignment.md) | graph hour labels — descenders (`12p`) shift them relative to `6a`; align by font metric, not ink extents |
| [eventfilter-pending-exception](eventfilter-pending-exception.md) | parked: a `SystemError` seen once, non-fatal, not reproducible. Wants an always-on diagnostic to catch it live |
| [phase-4.2-follow-ups](phase-4.2-follow-ups.md) | remaining odds from the backend/frontend split |
| [gauge-tick-label-format](gauge-tick-label-format.md) | tick labels read `28.00` on a 1-inHg scale — units carry a compact (dial-face) format in WeatherUnits, tick spacing as the floor; then dashboard-level format `defaults:` (matcher design open) |
| [gauge-round-to-float](gauge-round-to-float.md) | fixed on `fix/gauge-round-to-float`: a gauge narrower than 1 unit died in `__init__` (`round_to` returned `1e-323`); then drew no graduations (`rounded_max`, float floor/ceil) |
| [gauge-text-treatments](gauge-text-treatments.md) | optical centering — `98°` looks off-centre because `°` is light |
| [gauge-presets](gauge-presets.md) | named `preset:` for gauges, one per gauge-ui template (29 rows); which of seven missing gauge primitives unlocks which; blocked first on [gauge-display](gauge-display.md) |

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
