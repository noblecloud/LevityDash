# The glyph system: more robust, and more than one kind of pack

**Status: open — stage 1 and stage 2 (static) are on `feat/glyph-sets`; motion and two-tone painting remain.**

Stage 2 has landed: `lib/ui/svgpath.py` (the whole `d` grammar, arcs to cubics, `transform`), vector styles in a map (`svg` + `viewBox` + `stroke`, single part or a part list with `stroke`/`role`/`transform`), `VectorIcon` with `painterPath(size)` / `advance(size)` and `cutout` subtraction, `Text` drawing it into the same `QPainterPath` it fills for text, the `import_svg_pack.py` converter, and four packs: `vec:` (16 shipped glyphs), `wiv:` (219, weather-icons' own SVG export), `qw:` (507, QWeather), `meteo:` (519, Meteocons monochrome, 1.3 MB at two decimals). Pack colour comes from `[pack.colors]` resolved through `Color.role`, so it follows the theme.

Still open: per-part painting so `accent`/`edge` roles are more than data, the `glyph-color` modes (`themed`/`mono`/`native`), a theme file recolouring a pack by name, animated SVG frames, and pose morphing.

A glyph is a named picture an item draws (`icon:` on a `text` item, `icon:` on a `realtime` value label, the pins of a graph). Today every glyph is a Private-Use-Area character in an icon font. That is one kind of pack, and the loader around it assumed there would never be another.

Node on the vocabulary: **pack** is the icon set (`fa:`, `mdi:`, `wi:`), **style** is a table inside a pack (`solid`, `regular`, `brands`), **glyph** is one named picture, **map** is the TOML file a pack is written in.

## What stage 1 landed (branch `feat/glyph-system`)

`lib/ui/icons.py` is now a data-driven registry, and the failure modes below are gone. `docs/config/dashboard/icons.md` documents the format for users.

- **A pack is data, not a class.** `resources/icons/maps/*.toml` (user maps in `<config>/icons/maps/`, read first) are discovered at import. The three `IconPack` subclasses are gone; one generic `IconPack` reads a map. A new pack is a TOML file.
- **Discovery cannot take the window down.** A map that will not parse is logged and skipped. A pack whose map is missing becomes a `_MissingPack` that raises on use, not on import. Before, the three packs were constructed at module scope, so a broken map raised inside `Text.py`'s import.
- **Typed errors.** `IconError` / `IconPackNotFound` / `IconNotFound` (`IconNotFound` and `IconPackNotFound` subclass `KeyError`, so existing `except KeyError` callers keep working) and `FontNotFoundError`. A miss names close matches: `wi: has no glyph named 'day-sunnyy'; did you mean day-sunny?`.
- **`lstrip('icon:')` bug fixed.** `lstrip` takes a *set* of characters, so a bare name beginning with `i`, `c`, `o`, `n` or `:` lost its head — `getIcon('cloud')` resolved `loud`. Now `removeprefix('icon:')`, and bare names resolve across every pack.
- **Per-pack font metrics.** `IconPack.metrics` was a `ClassVar` dict keyed by *style*, so `mdi`'s `regular` and `wi`'s `regular` overwrote each other's metrics. Now per instance.
- **Font Awesome `regular` was commented out.** `[font-awesome.regular]` and its `font =` line were `#`-prefixed in the map while the style's `chars`/`svg` tables were live, so `fa:star` with `style: regular` silently drew the *solid* font. Restored; `fa:regular` has its own font again.
- **`getIconSvg` no longer KeyErrors** for a pack with no `svg` table (it returned `None` for `wi:`/`mdi:` and `KeyError` before). `Icon.svg` reads it.
- **Aliases and retired prefixes.** A pack's `aliases` table maps another vocabulary onto its names (`wi:clear-day` → `day-sunny`, and the forecast-io `partly-cloudy-*` pair). A root `also = [...]` key keeps a retired prefix alive (`mdi6:` → `mdi`; the map said `prefix = "mdi6"` while the code registered `mdi`).
- **Lookup cache.** `getIcon` returns the same object for the same `(name, style)`.
- **`IconPack.validate()`** reports what a pack cannot serve: a font that will not load, a missing font file, a style with no glyphs, an alias pointing nowhere, empty `svg` data.
- **Tests.** `tests/ui/test_icons.py` (14 tests) covers discovery, prefix handling, aliases, typed errors, the `fa:regular` regression, caching, a broken map being skipped, and a user map joining the registry.

### Do not validate glyph coverage with `QFontMetrics.inFont`

Measured on macOS with PySide6 6.11: `inFont(ord(char))` answers **False for 1083 of the 1852 Font Awesome names and 1102 of the 6395 Material Design names** — names that draw correctly in the app. The old `getFont(style, hasChar)` used it as a hard gate, which is why `fa:ellipsis` logged "no font found" on every boot while rendering fine. Which style *holds* a name is the map's job (`_styleFor`); `inFont` is a tiebreak only. Do not reintroduce it as a validator.

## Stage 2 — a vector pack tier

Candidates, counts and the measured Qt animation surface are in [PLAN-GLYPH-SYSTEMS.md](../PLAN-GLYPH-SYSTEMS.md). Meteocons' monochrome style and QWeather's `currentColor` 16×16 set are the two worth wiring first.

The reason to want it: three shipped packs are font-only, so a glyph is one colour, cannot animate, and pops between weather conditions. `docs/roadmap.md` has two items waiting on this ("Duotone / two-color icons", "Morphing glyphs"), and both are shared prerequisites.

**Good news: the renderer half already exists.** `Text._runPath` builds glyphs as `QPainterPath` outlines (`_addRun` → `path.addText`), and `_update_path` assembles the item's path with `path.addPath(self._runPath(text, font).translated(text_pos))`. A vector glyph is therefore an *extra path appended at the text position*, not a new item type and not a new renderer tier.

The work, in order:

1. **`Icon` learns two shapes.** `Icon.isVector`, `Icon.advance(em)`, `Icon.painterPath(em)`; font packs answer `None` and keep today's path. Path data comes from the pack's `svg` table.
2. **An SVG-path reader, Qt-free.** `lib/ui/svgpath.py`: SVG `d` → list of subpaths (M/L/H/V/C/S/Q/T/A/Z, absolute and relative) in a unit box. Arc segments are the only hard part; the fallback is a polyline at a fixed tolerance. Qt-free so the parser is testable without a scene, and so a converter script can reuse it.
3. **`Text` appends a vector run.** At `Text.py:1645`, when the icon is a vector, `path.addPath(icon.painterPath(...).translated(text_pos))` instead of `_runPath`; the advance comes from `Icon.advance(em)`. `_inkRect`, `_advance` and `_leftBearing` need the same branch or the fit group will size the item to a blank string.
4. **One real pack**, so the tier is proven: a small in-repo `vec:` pack (wind arrows, compass marks, sun/moon) written as TOML `svg` entries, and then a converter for an external set (`tools/import_svg_pack.py` — a folder of `.svg` files in, one map out). Kubai's static icons and Trazo's stickers are both that shape; neither is copied into the repo wholesale.
5. **Duotone, only after 1–4.** A second accent is a second path layer per glyph (`parts`), which is the same data model stage 3 needs. Do not add a two-colour code path before a pack can carry two layers.

## Stage 3 — motion and morphing

Animated SVG is **not** the expensive half: measured on this machine with PySide6 6.11.1, `QSvgRenderer` reports `animated()=True` and renders distinct frames for SMIL `<animateTransform>` and CSS `@keyframes`, so a pack entry whose `.svg` carries a pose can advance frames on a display timer with no new data model. Two caveats: `pyproject.toml` pins `pyside6 = "^6.6.1"` while CSS keyframes need Qt 6.10, and SMIL does not animate arbitrary attributes (`<animate attributeName="r">` reports `animated()=False`). Guard on `animated()` and fall back to a still frame.

Path-to-path morphing is the expensive half and comes last: it needs path correspondence, and `QPainterPath.elementCount()` differs per icon, so every part must be resampled to a common polyline before interpolating. Prefer pose interpolation over a fixed part set (sun, cloud, precip, bolt) — the roadmap's Morphicons note is the fallback design, not the first move. A pack needs, per name, an optional `rest` and `hover` pose so a glyph has two states; that is a data-model decision to take with the owner.

## Verification

- `env -u PYTHONPATH .venv/bin/python -m pytest tests/ui/test_icons.py -q` → 14 passed.
- `env -u PYTHONPATH .venv/bin/python -m pytest tests/ui/test_line_pins.py tests/ui/test_smoke.py tests/wire/test_containers.py -q` → 29 passed (the graph pins resolve glyphs through `getIcon`).
- For a render check of stage 2: `poetry run python src/LevityDash/devtools/render_dashboard.py OUT.png --seed <config-copy>` on a board with `icon: vec:wind-arrow`, and compare against a `wi:` icon at the same size.

## Scope boundaries — do not chase

- The font packs' own data (596 + 6395 + 1852 names) is not to be re-derived or trimmed here.
- `polar/glyphs.py` (aircraft silhouettes: `classify()`, `SHAPES`, `path()`) is a **different** glyph system — shapes drawn in code for the radar. It shares the word and nothing else. Leave it alone.
- `Modules/glyphs.py` (`Plus`, `BackArrow`, `Indicator`) is the Chrome/Studio chrome, also unrelated.
- Character-cell rendering, `IndoorIcon` in `Handles/Various.py`, and the `wi:` → condition mapping in the plugins' schemas are out of scope.

## Cross-links

- [docs/config/dashboard/icons.md](../config/dashboard/icons.md) — the user-facing format.
- [roadmap: duotone icons, morphing glyphs](../roadmap.md) — the two display items this unblocks.
