# Glyph systems: what exists, what each teaches, what to adopt

**Status: research, 2026-11-22. Documents options; schedules nothing.** The implementation brief is [tasks/glyph-system.md](tasks/glyph-system.md).

The question behind this file: the app has three font-glyph packs and one shape for a glyph (a single-colour character). Two icon projects prompted the search — kubai-icons (layered, one accent colour derived into gradients and shadows, hover motion) and trazo (hand-drawn stickers, multi-layer colour). Neither is useful as-is; both are useful as *evidence of a better data model*.

## The renderer we already have — measured, not assumed

`Text._runPath` / `_addRun` already build every glyph as a `QPainterPath`, so a vector glyph is an extra path appended at the text position. That covers static vectors. Whether *animated* SVG works today was tested on this machine (PySide6 6.11.1, offscreen), by rendering frame 0 and a mid frame and comparing pixels:

| SVG feature | `animated()` | duration | frames differ |
|---|---|---|---|
| CSS `@keyframes` on `transform` | True | 2000 ms | yes |
| SMIL `<animateTransform type="rotate">` | True | 6000 ms | yes |
| SMIL `animateTransform` + `keySplines`/`calcMode="spline"` | True | 3000 ms | yes |
| SMIL `<animate attributeName="r">` (non-transform attribute) | False | — | — |

So Qt SVG animation on this build is **transform- and CSS-keyframe-based**, not arbitrary-attribute animation. That is enough for weather motion (rotation, translation, scale, opacity via CSS), and it is what Meteocons uses.

Floor warning: `pyproject.toml` pins `pyside6 = "^6.6.1"`; CSS `@keyframes` support landed in Qt 6.10. An animated-SVG tier must either bump the floor or guard on `QSvgRenderer.animated()` and fall back to a still frame. SMIL `animateTransform` is the safer primitive on older Qt.

## Weather glyph sets

**Two new weather sets. Chosen 2026-11-22.**

| Set | What it gives | Why it was kept |
|---|---|---|
| [Meteocons](https://github.com/basmilius/meteocons) | 475+ icons in 4 styles (fill/flat/line/**monochrome**), SVG and Lottie; animated and static SVG as separate packages (`@meteocons/svg`, `@meteocons/svg-static`) | the only set whose vocabulary is *generated* (condition × sky cover × day/night) instead of enumerated; a monochrome style keeps theme tinting; a still and an animated file for the same name |
| [QWeather Icons](https://github.com/qwd/Icons) | 507 monochrome 16×16 `currentColor` SVGs in `icons/`, plus `-fill` variants and an icon font in `font/` | numeric icon codes that map 1:1 onto a provider's `icon` field, day/night pairs, 8 moon phases, **air quality, pollution and warning glyphs** in the same set |

[Weather Icons](https://github.com/erikflowers/weather-icons) stays as the existing `wi:` pack; its `svg/` folder holds the same 219 shapes, so existing names can move to a vector backend without renaming a single dashboard value.

**Dropped 2026-11-22, by decision — do not re-propose without a reason:** MET Norway weathericons, Weather Iconic, Makin-Things, Visual Crossing, Amedia Meteo Icons, amCharts animated weather icons, Climacons, Weather Underground icons. They added vocabularies (severity tiers, twilight, chance-of-X) that neither Meteocons' generated naming nor QWeather's code scheme needs.

## General vector libraries

Rated by how cleanly they become a pack, not by size.

- [Phosphor](https://github.com/phosphor-icons/core) — 1,512 icons × 6 weights, 256 box, one **filled** single path per file, `currentColor`. Least per-icon work of any candidate; duotone is the only weight with two layers.
- [Tabler](https://github.com/tabler/tabler-icons) — 5,491 outline + 1,054 filled at 24/2 stroke, `currentColor`, with tags in a file header. Best breadth-to-consistency ratio.
- [Remix Icon](https://github.com/Remix-Design/RemixIcon) — 1,690 names × line/fill, **filled paths even in "line"**, categorised directories.
- [Lucide](https://github.com/lucide-icons/lucide) — 2,102 flat files, stroke-only, one convention; simplest name→file mapping.
- [Iconoir](https://github.com/iconoir-icons/iconoir) — 1,383 regular (1.5 px stroke) + 288 solid.
- [Heroicons](https://github.com/tailwindlabs/heroicons) — good drawing, but colours are hard-coded (`#0F172A`), so each file needs a rewrite on import.
- [Bootstrap Icons](https://github.com/twbs/icons) — flawless ingest mechanics, wrong grid (16) for large dashboard draws.
- [Fluent UI System Icons](https://github.com/microsoft/fluentui-system-icons) — 1,431 names across 7 sizes; size in the filename forces one size per pack, colours hard-coded.
- [Solar](https://github.com/480-Design/Solar-Icon-Set) — 7,330 files in 6 styles; Title Case names with spaces make key derivation painful.
- [Octicons](https://github.com/primer/octicons) — 416 names × 2 sizes; small, GitHub-flavoured, supplementary.
- [Ionicons](https://github.com/ionic-team/ionicons) — 1,357 files at a 512 box with `-outline`/`-sharp` suffixes; least uniform of the file sets.
- [Simple Icons](https://github.com/simple-icons/simple-icons) — brand logos only; useful as a source/plugin badge pack, never a UI set.
- [Iconify collections](https://github.com/iconify/icon-sets) — **an aggregator, not a set**: 285 cleaned, validated upstream collections in one JSON format, plus the `chars` map used to generate fonts. Checked against its `collections.md` (2026-11-22): it carries Tabler, Iconoir and Lucide, but **not** Meteocons, QWeather or Phosphor. Value here is the format and the normalisation (monotone colours already rewritten to `currentColor`), not a pack to adopt.
- [Material Symbols](https://developers.google.com/fonts/docs/material_symbols) — font-first; the repo now ships Android assets, not a canonical SVG tree, so it is an upgrade path for the existing `mdi:` font pack, not an SVG pack.
- [Font Awesome](https://github.com/FortAwesome/Font-Awesome) — already a font pack here; its `svgs/` tree (2,886 files) would buy render quality at large sizes and nothing else.

## Systems: the three ideas worth taking

1. **A glyph is an ordered list of layers, not one path.** Phosphor's duotone is two stacked paths with `opacity="0.2"` on the secondary; SF Symbols formalises it as monochrome / hierarchical (one colour, per-layer opacity) / palette (N colours with a fallback rule) / multicolor (fixed semantic colours plus a tintable filler); trazo's `color="mix"` versus a single-colour stamp is the same switch; kubai derives one accent into gradients, outlines and a shadow across a back and front part.
   → **Decision it implies:** glyph data is `parts: [{path, role}]` with roles like `body`, `edge`, `accent`, `shadow`, each resolved against the theme's colours at paint time. Duotone becomes a colour-list length, not a second code path.

2. **Motion is a pose over a fixed part set.** Meteocons animates named groups (`__Sun`, `__Rays`, `__Cloud_2`) with `animateTransform`; kubai interpolates plain numbers over 460 ms with one cubic-bezier; Material Symbols uses the `FILL` axis for state transitions.
   → **Decision it implies:** a condition is a pose (per-part transform/opacity tracks) over shared parts, so a sun becomes cloud by moving parts, not by morphing one outline into another. This is cheaper and more legible than path morphing, and Qt already plays the SMIL/CSS form today (table above).

3. **A pack is a registry entry with a build step, not a class.** Iconify JSON normalises `{prefix, icons{name:{body, left/top/width/height, rotate, hFlip, vFlip}}, aliases{parent + transform}, chars{hex → name}}`; fantasticon turns an SVG folder into a font plus a codepoints JSON with pinned PUA values.
   → **Decision it implies:** one loader reads a map; a build script generates the PUA/char table. The hand-kept char maps and the per-pack Python classes both disappear. Stage 1 of the brief already made discovery data-driven; this is the same move one level deeper.

Morphing ([Morphicons](https://www.morphicons.com/docs)) stays last: it needs path correspondence, and `QPainterPath.elementCount()` differs per icon, so every part must be resampled to a common polyline before interpolating. Pose animation buys most of the delight for a fraction of that cost. The platform capability behind every animated option is [Qt 6.10's animated vector graphics](https://www.qt.io/blog/animated-vector-graphics-in-qt-6.10) (CSS keyframes in Qt SVG, plus a tech-preview Lottie backend).

## Adoption order

1. **Vector pack tier, static.** `SvgPack` beside the font packs; Meteocons monochrome and QWeather `currentColor` as the first two, both already single-colour SVG. Also convert the incumbent `wi:` set from its `svg/` folder so existing dashboard values keep working.
2. **Animated poses through `QSvgRenderer`.** No new data model: a pack entry may name an `.svg` whose parts animate, and the item advances `setCurrentFrame` on a display timer. Guard on `animated()` and on the Qt floor.
3. **Layer/role parts and duotone.** The `parts` list, resolved against theme tokens. This is the roadmap's "duotone / two-color icons" item.
4. **Pose morphing between conditions.** Interpolate part transforms; only then consider path morphing.

## Method and provenance

Each candidate was checked against its own repository tree or documentation: counts are file listings, not badge claims. Subagent notes are at `~/AIPlayground/tasks/glyph-hunt/` (01-weather, 02-general, 03-systems), which is scratch and may be pruned; the facts that matter are copied above. The Qt animation table was measured here, and it corrects one claim: SMIL is supported for `animateTransform`, not for arbitrary attribute animation.
