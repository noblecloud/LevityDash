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

- **[computed-values-in-dashboard-config.md](computed-values-in-dashboard-config.md)**
  — define a value by expression in a `.levity` file
  (`average(environment.temperature.temperature, 24hr)`, arithmetic between
  keys). Closer to a small expression language than a display option; the
  design questions are where it evaluates, when it recomputes, and what unit
  the result carries.
