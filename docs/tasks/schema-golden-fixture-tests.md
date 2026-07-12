# Golden-fixture tests for the remaining plugin schemas

**Status:** open, not started
**Scope:** new tests only, no source changes expected
**Suggested workflow:** own branch/worktree (see below), not `dev` directly

## Context

`tests/plugins/test_openweathermap.py` (added today, see commit `970dd0c`) established a pattern for testing a plugin's data-shaping logic without network access or a full `Plugin` bootstrap: capture a real (sanitized) API response, test the plugin's `normalizeData`/schema against it directly.

Before today, the entire plugin layer had **zero test coverage** (see `docs/reviews/schema-pipeline.md` and `docs/reviews/project-review.md`) — this is the most exotic, least-tested part of the codebase, and it's where several real bugs were found this session specifically because nothing exercised these paths (a `RecursionError` in `Schema.getUnitMetaData`, a dead `decode_measurement` timestamp restoration, an unmapped-key crash, a missing schema guard on auto-derived dewpoint — see `docs/reviews/schema-pipeline.md` for the first two, this session's task history for the rest).

## The task

Extend the same golden-fixture pattern to the other three builtin plugins with real schemas:

- `src/LevityDash/lib/plugins/builtin/OpenMeteo.py`
- `src/LevityDash/lib/plugins/builtin/PirateWeather.py`
- `src/LevityDash/lib/plugins/builtin/WeatherFlow/__init__.py`

(Govee is a different shape — BLE payload parsing, not a REST/JSON schema — lower priority, could use a similar-in-spirit test but the payload-slicing logic is different enough to treat separately if time allows.)

For each plugin, look at `tests/plugins/test_openweathermap.py` as the template and cover, at minimum:

1. **A captured, sanitized real response** (or a realistic hand-built one, matching the plugin's actual API shape — check `docs/plugin_config.md` for API references) run through the plugin's own data-shaping method (`normalizeData` if it has one; otherwise construct a `LevityDatagram` directly against the plugin's `schema` dict — see how `LevityDatagram(data, schema=schema, ...)` gets called in `src/LevityDash/lib/plugins/web/rest.py`'s `getData` for the pattern, and `lib/plugins/schema/__init__.py` for what it does).
2. **"Every emitted/mapped key has a schema entry" check** — this is the general-purpose regression guard `test_normalize_every_key_has_a_schema_source_key` in the OpenWeatherMap test file; adapt it to whatever each plugin's actual data-shaping step produces. This is the single highest-value test per plugin, since it directly catches the "unmapped key crashes the whole batch" bug class documented in `docs/reviews/schema-pipeline.md` and hit live during OpenWeatherMap's development.
3. **Missing/optional field handling** — most weather APIs omit fields under some conditions (calm wind, clear sky, no precipitation, etc.). Confirm the plugin's data-shaping doesn't crash on a sparse/partial response.

## What NOT to do

Don't touch the schema engine itself (`src/LevityDash/lib/plugins/schema/__init__.py`, `src/LevityDash/lib/plugins/observation.py`, `src/LevityDash/lib/plugins/categories.py`) as part of this task — if a test reveals a real bug in the engine (not just the plugin's own schema/normalizeData), report it rather than fixing it inline; that's a separate, more invasive change that should be scoped on its own (see whether `docs/tasks/` already has a relevant open item, or ask before starting one).

## Verification

`poetry run pytest tests/plugins/ -v` — new tests pass. `poetry run pytest` — full suite still green, no regressions.

## Suggested git workflow

```bash
cd ~/Code/LevityDash
git worktree add ../LevityDash-plugin-tests -b test/plugin-schema-fixtures
```

Work in `~/Code/LevityDash-plugin-tests`. When done:

```bash
cd ~/Code/LevityDash
git merge test/plugin-schema-fixtures    # after reviewing the diff
git worktree remove ../LevityDash-plugin-tests
```
