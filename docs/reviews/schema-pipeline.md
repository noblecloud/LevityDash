# Schema pipeline review — datagrams, UnitMetaData, and the plugin maps

*2026-07-12. Verified against the code by tracing the full path: raw JSON → `LevityDatagram` → keyMaps/dataMaps → `UnitMetaData.getConvertFunc` → `ObservationValue.value`. File references are to `lib/plugins/schema/__init__.py` unless noted.*

## The pipeline, as it actually works

For a REST plugin (OpenMeteo is the cleanest example):

1. **Fetch** — `REST.getData` (`web/rest.py:39`) pulls JSON, passes it through the plugin's optional `normalizeData` hook, and constructs `LevityDatagram(data, schema=…, dataMap=schema.dataMaps[endpoint.name])`.
2. **`__init_data__`** (`:68`) runs five passes over the raw tree:
   - `mapArrays` — applies the plugin's `keyMaps` to turn *positional* arrays into keyed dicts (WeatherFlow's `obs_st` block is a 18- or 22-element array; the keyMap assigns a `CategoryItem` to each position).
   - `parseData` — walks the tree; promotes `{{sourceData}}`/`{{metaData}}`-tagged scalars into datagram-level metadata (`@station`, `@timezone`, `@timestamp`…); wraps any dict whose keys match schema `sourceKeys` into a `Subdatagram`; explodes columnar timeseries (`{time: […], temp: […]}` under a valid dataMap path) into a *list* of per-timestamp `Subdatagram`s.
   - `replaceKeys` — renames every recognized `sourceKey` to its canonical `CategoryItem` (via the inverted `sourceKeyMap`), dropping unknown keys' `None` values unless `allowNull`.
   - `replaceKeyVars` — substitutes `@var` atoms inside keys (e.g. `device.@deviceSerial.battery`) from the promoted metadata, with per-property `alt` fallback chains, defaulting to `'NA'`.
   - `addDataKeyValues` — copies values across keys that declare a `dataKey` (e.g. `condition.icon` and `condition.condition` both derive from `condition.weatherCode`).
3. **`mapData`** (`:90`) — selects which parsed `Subdatagram`s become the named sections the plugin consumes (`'hourly'`, `'daily'`, `'realtime'`…), by structural-pattern-matching each candidate's `path` against the endpoint's `dataMap`. Everything unmapped is deleted.
4. **`validate`** (`:376`) — per-key `UnitMetaData.validate` runs the `requires` rules (operator dicts, negation, cross-key requirements) and pops failures.
5. **Consumption** — the plugin hands sections to its observations; each stored `ObservationValue` lazily converts on first `.value` access via `UnitMetaData.getConvertFunc(source)` (`categories.py:181`), which resolves `type` + `sourceUnit` against `unitDict` into a real WeatherUnits class — including derived units built from tuples (`('mi', 'hr')` → `Wind`) and datetime parsing (`epoch`/`ISO8601`). Aliased values (`aliases: '@condition'`) go through `mapAlias`/`mapIcon` instead.

**Verdict on the core question: yes, it works, and the *architecture* is genuinely good.** The declarative intent — a plugin is mostly a schema dict plus endpoint definitions — is achieved for the REST path: PirateWeather is ~120 lines of schema and ~100 lines of code. Hierarchical inheritance is a standout feature: a parent entry (`'environment.temperature': {type, sourceUnit}`) supplies unit metadata to all children, so leaf entries are often just `{title, sourceKey}` (`UnitMetaData.__init__`'s parent-walk, `categories.py:129-134`).

## The exotic parts (verified, working, but undiscoverable)

The keyMap/dataMap DSL uses *Python objects* as vocabulary:

| token | meaning | example |
|---|---|---|
| `int` key | "match an array of exactly this length" | WeatherFlow `obs_st: {18: […], 22: […]}` — firmware variants |
| `iter` (the builtin) | "map each element of the list" | `obs_sky: {obs: {iter: […]}}` |
| `filter` (the builtin) | "whitelist these keys, drop the rest" | |
| `...` (Ellipsis) | positional skip / variadic marker | |
| `DotStorage` + `match` | value-patterns in `match` need dotted names, so `mapData` wraps the map in a throwaway object to write `case Subdatagram(path=s.map)` (`:96-108`) | |
| `unitDict['special'][type][n : type(d)]` | slice syntax as a composite-unit constructor (`categories.py:224`) | wind = distance over time |

This is clever and compact — but none of it is documented anywhere (until now), none of it is expressible in a config file, and a typo produces silence rather than an error.

## Bugs found (concrete, verified)

1. **`Schema.getUnitMetaData` fuzzy-match is a latent `RecursionError`** (`:751`): `keys = [str(key) for k in self._source.keys()]` uses `key` (the lookup) instead of `k` — it builds N copies of the key being looked up, so `get_close_matches` always "finds" the key itself and the method recurses with identical arguments until the stack dies. One-character fix (`str(k)`). It only fires when `key in self` but `getExact` returns None — rare, which is why it's survived.
2. **OpenWeatherMap's schema is never used** (`builtin/OpenWeatherMap.py`): the module defines a real 22-entry `schema` dict at line 13, but the class body sets `schema = {}` and the `__plugin__ = OpenWeatherMap` export is commented out. The plugin is a disabled skeleton, not just "unpolished."
3. **`Schema.__parseDateTime`** (`:889`) is dead code and doubly broken: the `epoch` branch references `kwargs` that's never bound (`NameError`); the `ISO8601` branch calls `datetime.strptime(value, format=…)` — strptime takes format positionally. No callers; the real datetime handling is in `UnitMetaData.getConvertFunc`. Should be deleted.
4. **Static datagrams silently drop writes** (`LevityDatagram.__setitem__`, `:177`): when `static=True` the method body is skipped entirely — no store, no error. Construction only works because CPython's `dict.update` bypasses the override. Any future code that assigns into a static datagram loses data invisibly. The same method also computes `replaceKeyVars({key: value})` into a local that's discarded — the var-substitution feature simply doesn't run for post-construction assignment.
5. **Silent conversion fallback** (`observation.py:230-232`): `ObservationValue.value` wraps `convertFunc` in `except Exception: value = self.rawValue`. A schema mistake (wrong `sourceUnit`, bad alias) doesn't error — it displays an unconverted number. Combined with (6), schema errors are nearly undebuggable by design.
6. **Fuzzy fallbacks mask typos**: `getUnitMetaData` remaps unknown keys to the closest match at `cutoff=0.5` with only a log warning; `findTimeKey` fuzzy-matches "timestamp". A misspelled `sourceKey` can silently bind the wrong unit metadata.
7. **Smaller items**: `getConvertFunc` mutates `self['kwargs']` in place (bakes `tz` on first call) and has a `kwargs = kwargs =` typo (`categories.py:184`); `Properties.get`/`MetaData.get` use `if value is not None`, so a legitimately-`None`/falsy property can never be returned directly; both classes inject `'plugin': plugin` into their own dict, so every iteration over `.items()` visits a `Plugin` object and quietly relies on `'sourceKey' in plugin` behaving; the datagram's `__hash__` is built from `sourceData` *while parsing is still mutating it*, and it's used as an `lru_cache` key mid-parse (`findTimeKey`).

## Is there a better way?

The goal — **new plugins without much coding** — is the right lens, and the current design is already 80% of the way there in *spirit*. The gaps are formality, feedback, and serializability. Recommendations, in order of leverage:

1. **Give the schema a schema.** Define the entry vocabulary (`type`, `sourceUnit`, `sourceKey`, `dataKey`, `aliases`, `requires`, `allowNull`, `timeseriesOnly`, …) as TypedDicts/dataclasses and validate every plugin schema at load. Today a typo'd field name is ignored forever; a 30-line validator turns it into a startup error with the field name and the plugin. This is the single cheapest, highest-value change, and it costs plugin authors nothing.
2. **Replace Python-object DSL tokens with string tokens** (`iter` → `'*'` or `'each'`; `filter` → `'only'`; `...` → `'…'`/`'rest'`; int length-keys → an explicit `variants: {18: […], 22: […]}` block). Then a plugin schema is *pure data* — loadable from a TOML/YAML manifest. That's the real unlock for the low-code goal: a new REST source becomes a single file (`endpoints` + `schema` + `keyMaps`), with Python needed only for genuinely custom behavior (a `normalizeData` hook, BLE parsing). It also lets the future headless backend advertise/load plugin manifests without importing arbitrary code, which matters for the HUD-node vision.
3. **Build the feedback loop: a schema dev harness.** The hardest part of writing a plugin today is that the mapping either works or silently produces an empty datagram (`InvalidData` at best). A small CLI — `levitydash schema-dev plugin.toml sample-response.json` — that prints the parsed datagram tree with *unmatched source keys highlighted* would make schema authoring a minutes-scale iterative task instead of log archaeology. The pieces already exist (`LevityDatagram.__str__` is already a pretty-printed tree).
4. **Make failures loud in development.** A strict mode (env var or config flag) where: unmapped keys are reported once per session as a summary table; `convertFunc` exceptions log the key + raw value + exception at WARNING (instead of silently degrading); and the fuzzy-match fallback *suggests* instead of *substitutes*. Production keeps the lenient behavior.
5. **Record golden fixtures.** `tests/plugins/` with one captured raw JSON response per builtin endpoint and the expected parsed datagram (as YAML). The whole 900-line engine currently has zero test coverage, which is why bugs like #1 and #4 persist; goldens are cheap to record (the app already receives the data) and make the eventual refactor of the exotic bits safe.
6. **Delete/merge the second mapping path.** `Schema.mapKeys`/`Schema.mapData`/`__setProperties` (`:761-853`) largely duplicate what `LevityDatagram` does internally, and `Schema.mapData` appears to have no external callers. One engine, one code path.
7. **Shared vocabulary across plugins** (smaller win): all four builtin schemas independently define the same canonical keys with the same titles. A `baseSchema` of canonical entries (title/description/type per key) that plugin schemas *reference* (adding only `sourceKey` + unit) would shrink plugin schemas by ~half and keep titles consistent — OpenWeatherMap's entire leaf layer is already implicitly this.

Notably **not** recommended: replacing the engine wholesale (with pydantic, marshmallow, etc.). The domain logic — positional array variants, key vars, columnar explosion, unit inheritance — is real and would have to be rebuilt on top of any library; the current engine's problems are formality and feedback, not the core algorithms, and the WeatherUnits integration (`unitDict` + derived units) is a genuine asset no off-the-shelf library replicates.
