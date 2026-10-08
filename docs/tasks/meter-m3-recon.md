# M3 recon: `GaugeArc`, `Gauge(Meter)`, the shim, and the hand-over

**Status: FIXED 2026-10-06.** M3 landed: `meter/gauge.py` holds `GaugeArc` and
`Gauge` with the hand-over at its foot, and `Gauge.py` is a 16-line shim
(`38579f4`, `f519eed`, on `dev`). This brief is the read-only recon that planned
that move — it changed no source itself, and its writer did not commit it (the
index is the maintainer's). The line numbers below are from `1922538`, the commit
it was written against; the working tree has moved on since.

- Commit read: `1922538` (`git rev-parse HEAD` when this was written). Every line number
  below is from `git show 1922538:<path>`, *not* from the working file: another agent was
  mid-move in the same tree (Gauge.py working copy went 1292 -> 1060 lines while this was
  being written), so the working file will not agree with the numbers here until that batch
  lands.
- Method: an AST scan of every `*.py` under `src/` and `tests/` for imports that resolve to
  `...Displays.Gauge`, plus `src/LevityDash/devtools/render_diff_tools/move_inventory.py` and
  `src/LevityDash/devtools/render_diff_tools/arc_cut.py` run against the commit's `Gauge.py`.
- Job C of [`meter-m2b-remaining.md`](meter-m2b-remaining.md). Working note:
  [`meter-harness-status.md`](meter-harness-status.md). Survey: [`meter-survey.md`](meter-survey.md).

## 0. Where the tree is (quoted from `1922538`)

`src/LevityDash/lib/ui/frontends/PySide/Modules/Displays/Gauge.py` is **1292 lines** and
defines exactly **three** module-level things:

| name | lines | note |
| --- | --- | --- |
| `log` | 63 | `UILogger.getChild('Gauge')` |
| `GaugeArc(StatefulGaugePathItem)` | 67-287 | the arc; `@DebugPaint` |
| `_markerText(spec)` | 292-297 | private helper for marker log text |
| `Gauge(Meter)` | 301-1280 | everything left of the class |
| the hand-over | 1287-1292 | see §4 |

Everything else in the module's namespace is a re-import: 175 public names + 6 private
(`_UNIT_UNDER_VALUE`, `_gaugeKeyName`, `_isWholeSteps`, `_markerText`, `_meter_elements`,
`_meter_module`). `meter/` holds `scale.py` (193), `track.py` (194), `elements.py` (4534),
`meter.py` (569), `__init__.py` (13 — docstring only).

**M3, reconciled with what actually landed.** The survey's file table put `GaugeTickText`,
`GaugeTickTextGroup`, `Arrow`, `GaugeCaption`, … in `meter/gauge.py`. They are already in
`meter/elements.py` (`GaugeTickText` 1382-1705, `GaugeTickTextGroup` 1706-2229, `Arrow`
3004, and the rest), moved by M1b/M1c/M1d/M1e. So M3 as it can actually be executed is:

1. create `meter/gauge.py` and move into it, verbatim: `GaugeArc` (67-287), `_markerText`
   (292-297), and `Gauge` (301-1280), plus the hand-over at its foot;
2. repoint the package's three back-imports (§4.3);
3. leave `Gauge.py` as the shim.

Do **not** move `GaugeTickText`/`GaugeTickTextGroup` a second time: `Graduations.labels` is
annotated `-> 'GaugeTickTextGroup'` and resolves against the module `Graduations` was
*defined* in (`meter/elements.py`). Moving the group out of that module re-opens the exact
`NameError` that cost the M1c afternoon (see `tests/ui/test_meter_annotations.py`).

---

## 1. Every module-level name other files import from `Displays/Gauge.py`

### 1.1 Named imports — the shim's hard contract

Measured by AST over `src/` and `tests/`; all absolute-import forms (`from ...Gauge import
X`) plus the two package-star forms.

| # | name | file:line | form | resolves to |
| --- | --- | --- | --- | --- |
| 1 | `Gauge` | `src/LevityDash/lib/ui/frontends/PySide/Modules/Displays/Realtime.py:313` | `from ...Displays.Gauge import Gauge` | class |
| 2 | `Gauge` | `src/LevityDash/devtools/_studio_stage.py:41` | `from ...Displays.Gauge import Gauge` | class |
| 3 | `Gauge` | `src/LevityDash/devtools/_studio_stage.py:40` | `from ...Displays import Gauge as _gaugeModule` | **class** (see §5.1) |
| 4 | `Gauge` | `src/LevityDash/lib/ui/frontends/PySide/Modules/Displays/Realtime.py:766` | `from ...Modules import Gauge` | class (via `Modules/__init__.py:2` ← `Displays/__init__.py:49`) |
| 5 | `Needle` | `src/LevityDash/devtools/_studio_editors.py:1197` | `from ...Displays.Gauge import Needle` | class |
| 6 | `GaugeTickTextGroup` | `tests/ui/test_gauge_tick_format.py:2` | `from ...Displays.Gauge import GaugeTickTextGroup` | class |
| 7 | `_isWholeSteps` | `tests/ui/test_gauge_interval_steps.py:1` | `from ...Displays.Gauge import _isWholeSteps` | function (private) |
| 8 | `clockTurn` | `tests/ui/test_gauge_helpers.py:4` | `from ...Displays.Gauge import (` … `)` | function |
| 9 | `formatDuration` | `tests/ui/test_gauge_helpers.py:4` | idem | function |
| 10 | `parseClockTime` | `tests/ui/test_gauge_helpers.py:4` | idem | function |
| 11 | `shortestDelta` | `tests/ui/test_gauge_helpers.py:4` | idem | function |
| 12 | `*` (all public) | `src/LevityDash/lib/ui/frontends/PySide/Modules/Displays/__init__.py:49` | `from .Gauge import *` | 175 public names → `Displays.*` → `Modules.*` |

Package-internal pointers at the same module (they must not become imports of a name that
no longer exists):

| name | file:line | form |
| --- | --- | --- |
| `Gauge` | `meter/elements.py:64` | inside `if TYPE_CHECKING:` |
| `Gauge` | `meter/elements.py:88` | inside `gauge_class()` (lazy, runtime) |
| `Gauge` | `meter/meter.py:38` | inside `if TYPE_CHECKING:` |

### 1.2 The star surface (`from .Gauge import *`)

`Displays/__init__.py:49` has no `__all__` to honour, so it copies **every public name**
Gauge.py's namespace has: **175 at `1922538`**. `Modules/__init__.py:2` (`from .Displays
import *`) chains it. Checked by AST: of the names imported downstream from `Displays.*` /
`Modules.*`, the **only** one that originates in `Gauge.py` is `Gauge` itself (the rest —
`Surface`, `SurfaceCentered`, `Text`, `AnnotationText`, `AnnotationLabels`, `Display`,
`Panel`, `SizeGroup`, `Handle`, `NonInteractiveLabel`, `DateTime`, `Moon`, `Realtime`, … —
come from their own modules, which `Displays/__init__.py` star-imports *before* line 49).
So the star surface is a safety net, not a requirement — but keep it intact, because the
gradle of names is cheap to preserve and expensive to lose silently.

The 175 break down as:

**Tier A — defined here, therefore must be re-exported (3):**
`Gauge`, `GaugeArc`, `log` (all three are `def`/`assign` in `Gauge.py`).

**Tier B — today re-exported from the `meter` package through `Gauge.py` (33):**
`ArcTrack`, `Arrow`, `CLOCK_HANDS`, `GaugeCaption`, `GaugeFill`, `GaugeItem`, `GaugeLabel`,
`GaugeMarker`, `GaugePathItem`, `GaugeRange`, `GaugeText`, `GaugeTickText`,
`GaugeTickTextGroup`, `GaugeUnit`, `GaugeValue`, `GaugeValueLabel`, `GaugeZones`,
`Graduations`, `Meter`, `Needle`, `Numeric`, `Scale`, `StatefulGaugeItem`,
`StatefulGaugePathItem`, `SubTick`, `Tick`, `TickSurface`, `clockTurn`, `decode_measurement`,
`filter_factors`, `formatDuration`, `parseClockTime`, `shortestDelta`.

These 33 matter: `Displays` does **not** star-import the `meter` package anywhere, so if the
shim stops re-exporting them, `Displays.<name>` disappears. Four more private `meter` names
are bound in `Gauge.py` and are *not* star-exported: `_UNIT_UNDER_VALUE`, `_gaugeKeyName`,
`_isWholeSteps` (imported by test 7), plus the bookkeeping `_meter_elements`/`_meter_module`
(don't carry these).

**Tier C — incidental imports (139):** 67 project names (`Alignment`, `Size`, `Text`,
`Panel`, `openValueSource`, `radialPoint`, `now`, …) and 72 third-party/stdlib (`QPointF`,
`QPen`, `Qt`, `Optional`, `Union`, `copy`, `pi`, `Angle`, `Measurement`, …). Nothing
imports these from `Displays`/`Modules`; they are in the namespace only because `Gauge.py`
imported them for the members that moved out. They come free if `meter/gauge.py` imports
what `Gauge`/`GaugeArc` need.

### 1.3 The module itself

`_studio_stage.py:40` is written as if it imported the **module**
(`_gaugeModule.openValueSource = _openValueSource`, line 292; docstring "Point the Gauge
module's `openValueSource`"). It does not — see §5.1. Nothing else wants the module object:
`_studio_stage.py:41`, `Realtime.py:313` and the two package-star forms all want the class.

### 1.4 What the shim must contain

```python
# src/LevityDash/lib/ui/frontends/PySide/Modules/Displays/Gauge.py
"""Shim. The gauge classes live in `meter/gauge.py`; this module re-exports them."""
from .meter.gauge import *                     # Gauge, GaugeArc, log (+ gauge.py's public names)
from .meter.gauge import Gauge, GaugeArc       # Tier A, explicitness for readers
from .meter.meter import GaugeRange, Meter     # Tier B (meter.py __all__ is these two)
from .meter.elements import (                  # Tier B - element classes
    Arrow, GaugeCaption, GaugeFill, GaugeItem, GaugeLabel, GaugeMarker, GaugePathItem,
    GaugeText, GaugeTickText, GaugeTickTextGroup, GaugeUnit, GaugeValueLabel, GaugeZones,
    Graduations, Needle, StatefulGaugeItem, StatefulGaugePathItem, SubTick, Tick, TickSurface,
)
from .meter.scale import (                     # Tier B - scale helpers
    CLOCK_HANDS, GaugeValue, Numeric, Scale, _isWholeSteps, clockTurn, decode_measurement,
    filter_factors, formatDuration, parseClockTime, shortestDelta,
)
from .meter.track import ArcTrack
```

Two traps in that snippet:

- `from .meter.elements import *` would **not** work: `meter/elements.py` declares
  `__all__ = ['GaugeItem', 'GaugePathItem', 'GaugeValue', 'Numeric', 'StatefulGaugeItem',
  'StatefulGaugePathItem']` (line 79), so the star form drops every element class. Import
  them by name (as above) or extend `elements.__all__` — the explicit list is safer.
- `_isWholeSteps` is private, so no star form carries it and `tests/ui/test_gauge_interval_steps.py:1`
  imports it directly. It **must** be an explicit import in the shim.

Tier C need not be reproduced, but it is cheap to check: run the name-set diff in §5.5 and
add anything that fell out.

---

## 2. What `GaugeArc` needs in order to live in `meter/gauge.py`

`src/LevityDash/devtools/render_diff_tools/move_inventory.py <Gauge.py> GaugeArc` against `1922538`:

```
classes: GaugeArc
uses 44 outside names:

  imports to bring along (25):
    ArcTrack            from ...Displays.meter.track
    Color, Gradient     from LevityDash.lib.ui
    DebugPaint, addPath, outline_path   from ...PySide.utils
    DimensionType, Size, parseWidth     from LevityDash.lib.ui.Geometry
    Length              from WeatherUnits
    Optional            from typing
    QBrush, QColor, QPainter, QPainterPath, QPen, Qt   from PySide6.QtGui
    QPoint, QPointF, QRectF                            from PySide6.QtCore
    StateProperty       from LevityDash.lib.stateful
    StatefulGaugePathItem  from ...meter.elements
    camelCase, closestStringInList, defer, radialPoint from LevityDash.lib.utils.shared

  Gauge.py's own functions/classes it calls:
    GaugeArc            (self-reference only)

  not at module level: angle, args, brush, cap, capNames, caps, current_pos, inner_rect,
    inner_safe_radius, kwargs, outer_safe_radius, path, radius_rect, rect, start_pos,
    width, width_vector   (all locals)
```

**Result: `GaugeArc` needs nothing that is defined in `Gauge.py`.** All 25 outside names are
importable in `meter/gauge.py`; the only "Gauge.py own" name in the list is `GaugeArc`
itself. There is no helper to hand over for the class to import.

Two constraints the inventory cannot see:

1. **`GaugeArc` talks to the gauge by attribute, not by import.** `self.gauge.<attr>` reads:
   `center` (L175, L194), `exterior_safe_radius` (L122), `gaugeRect` (L115),
   `map_gradient_to` (L186), `pen` (L179), `rect` (L107), `safe_radius` (L121),
   `sizeAcross` (L238), `update_center_offset` (L168). Every one of these is a member of
   `Gauge`/`Meter`. So `GaugeArc` must land in the **same module as `Gauge`** (or be handed
   the class): `meter/gauge.py`. It needs no import of `Gauge` for this to work.
2. **Its one class-level annotation must resolve in the new module.**
   `_track: Optional[ArcTrack] = None` (L73). `tests/ui/test_meter_annotations.py` calls
   `typing.get_type_hints` on every class in the package; `Optional` and `ArcTrack` therefore
   have to be module-level names in `meter/gauge.py` (both are in the 25 above). The same
   test must be extended to include `meter.gauge` in its `MODULES` tuple
   (`tests/ui/test_meter_annotations.py:20-25`) or the new module is not walked at all.

`GaugeArc` also inherits the item machinery (`StatefulGaugePathItem` → `GaugeItem` →
`_extract_gauge`, which finds the owning `Gauge` among constructor arguments), and is
decorated with `@DebugPaint`; both come from outside `Gauge.py`.

---

## 3. The arc-only members of `Gauge`

`src/LevityDash/devtools/render_diff_tools/arc_cut.py <Gauge.py> Gauge` against `1922538` (125 members, 33 rows
with an arc reference). Grouped by member, the arc-specific set is:

| member | lines (`1922538`) | why it is arc-only |
| --- | --- | --- |
| `arc` (property, factory, setter, field) | 307, 353-363 | the `GaugeArc` itself |
| `startAngle` / `leading_angle` / `endAngle` / `trailing_angle` | 597-615 | delegations to the arc |
| `fullAngle` | 1019-1021 | sweep width |
| `convert_gradient` | 617-628 | `QConicalGradient` swept start→end |
| `value_to_angle` (live) | 1074-1075 | `startAngle + t * fullAngle` |
| `value_to_angle_degrees` / `angle_degrees_to_value` | 1077-1136 | px↔angle via `radius`/`fullAngle` |
| `safe_radius` / `exterior_safe_radius` / `value_safe_radius` | 1141-1199 | trim `radius` by tick/label size |
| `radius_max` / `radius` (both defs) | 997-1011 | `_dialRect`, short side |
| `gaugeRect` | 1013-1017 | the `radius*2` square |
| `arc_length` | 1055-1058 | `radius * fullAngle / 180 * pi` |
| `sizeAcross` / `sizeAlong` | 1060-1072 | resolve against `radius` / `arc_length` |
| `tickFont` | 1027-1031 | point size `max(radius*.1, 18)` |
| `center` | 962-987 | alignment over `_dialRect` |
| `refresh` | 757-782 | drives `arc.refresh()` |
| `recenter` | 661-747 | resets and re-applies the arc/needle/ticks transform |
| `safe_area` | 1201-1203 | `arc.mapToParent(arc.shape())` |
| `_gauge_path` / `full_gauge_path` / `full_gauge_rect` | 1228-1280 | add `arc.shape()` first |
| `_debug_paint` | 1205-1214 | paints the arc gradient |

All of these are members of `Gauge`, and `Gauge` is the thing moving to `meter/gauge.py`, so
they travel with it. The M2b brief's "these stay in `Gauge` by decision" list
(`meter-m2b-remaining.md:44-51`) is exactly this set plus the layout members; note that the
members already moved to `meter/meter.py` by M2b batches 1-2 (`_buildLabel`, `valueLabel`,
`unitLabel`, `subLabel`, `caption`, `value`, `valueClass`, `range`, `value_scale`, …) are
**not** in the arc list and must not come back.

### What the arc-specific label classes in `meter/elements.py` need from the gauge

`GaugeTickText` (1382-1705) and `GaugeTickTextGroup` (1706-2229) are the arc-shaped label
overrides and they live in `meter/elements.py` today. Their reads off the gauge:

| class | needs from the gauge |
| --- | --- |
| `GaugeTickText` | `arc` (L1571 `setPos`, L1606 `_placementKey`), `safe_radius` and `exterior_safe_radius` (L1654, `allowedWidth`), `fullAngle` (L1623, L1657), `range` (L1659) |
| `GaugeTickTextGroup` | `radius` (L1736, `text_size_relative_to`), `localGroup` (L1921 — a `Display` member, not a gauge one) |
| `GaugeValueLabel` (adjacent, for completeness) | `arc` (L4295, `limitRect`), `needle` |

So of the arc-only members above, the label classes need **`arc`, `safe_radius`,
`exterior_safe_radius`, `fullAngle`, `radius`** (plus `range` from `Meter`). All five are
attribute reads on the gauge instance at runtime — **no import of them into `elements.py` is
needed and none is possible** (that way lies the cycle). What `elements.py` does need is the
*annotation* names `Gauge` / `GaugeArc` in its module globals (§4.4).

---

## 4. The import-order constraint and the hand-over

### 4.1 The DAG

```
meter/scale.py     (leaf: Qt-free, no package imports)
meter/track.py     (leaf: Qt only)
meter/elements.py  -> meter.scale                       (must not import .meter or .gauge at module level)
meter/meter.py     -> meter.elements, meter.scale       (must not import .gauge at module level)
meter/gauge.py     -> meter.meter, meter.elements, meter.scale, meter.track     <-- top of the package
Gauge.py (shim)    -> meter.gauge                                                <-- top-most
```

`elements` <- `meter` <- `gauge` is a strict order: each module may import only the ones
above it in that list. The only edges that close a loop are the two that already exist as
lazy/`TYPE_CHECKING` stubs, plus the hand-over. `meter/__init__.py` must stay a docstring —
if it imported `meter.gauge`, every `from .meter import X` in the package would re-enter the
package during `gauge.py`'s own import.

### 4.2 The three back-imports to repoint

Today all three point at `...Displays.Gauge`, i.e. at the shim:

| file:line | today | after M3 |
| --- | --- | --- |
| `meter/elements.py:88` (`gauge_class()` body) | `from ...Displays.Gauge import Gauge` | `from .gauge import Gauge` |
| `meter/elements.py:64` (`if TYPE_CHECKING`) | `from ...Displays.Gauge import Gauge` | `from .gauge import Gauge` |
| `meter/meter.py:38` (`if TYPE_CHECKING`) | `from ...Displays.Gauge import Gauge` | `from .gauge import Gauge` |

Leaving them pointing at the shim also works (the shim still re-exports the class), and is
the smaller diff — but then `meter/gauge.py` cannot be imported on its own without the shim,
which is the whole point of the move. Recommend repointing; the `gauge_class()` one is
lazy (inside a function), so importing `.gauge` there is not a cycle.

### 4.3 The hand-over

Today, at the foot of `Gauge.py` (1287-1292):

```python
from ...Displays.meter import elements as _meter_elements
from ...Displays.meter import meter as _meter_module

_meter_elements.Gauge = Gauge
_meter_elements.GaugeArc = GaugeArc
_meter_module.Gauge = Gauge
```

Why each line exists (verified, not assumed):

- `_meter_elements.Gauge` — `meter/elements.py:76` sets `Gauge = None` and **class-level**
  annotations read it: `gauge : Gauge` (L188) is evaluated when the class body runs, so the
  name must exist at import; `parent: 'Gauge'` (L3825) and `surface: 'Gauge'` (L4302) are
  quoted and resolved later by `typing.get_type_hints` (which `Text.surface` calls at layout
  time) against `elements.py`'s globals. The hand-over is what turns `None` into the real
  class so those hints resolve.
- `_meter_elements.GaugeArc` — only needed for the F821 linter on a **local** annotation
  `arc: GaugeArc = gauge.arc` (`elements.py:3927`); local annotations are never evaluated at
  runtime, and `get_type_hints` never sees them. Keep the line (it keeps the name honest and
  ruff quiet), but do not mistake it for a runtime requirement.
- `_meter_module.Gauge` — **functionally required.** `meter/meter.py:42` sets `Gauge = None`
  and two methods call it at runtime: `return Gauge._decodeCaption(value)`
  (`meter/meter.py:380` and `:397`). Its `TYPE_CHECKING` import exists only for the
  annotations. Without the hand-over, a `GaugeRange` in `Meter` mode raises
  `AttributeError: 'NoneType' object has no attribute '_decodeCaption'`.

**Once `Gauge` and `GaugeArc` move to `meter/gauge.py`, the hand-over moves with them** — the
block belongs at the foot of the file that defines the classes, not in the shim, so that any
import path that reaches `meter/gauge.py` performs it:

```python
# foot of meter/gauge.py, after class Gauge / class GaugeArc
from . import elements as _meter_elements
from . import meter as _meter_module

_meter_elements.Gauge = Gauge
_meter_elements.GaugeArc = GaugeArc
_meter_module.Gauge = Gauge
```

and `Gauge.py` then carries **no** hand-over of its own: it imports `meter.gauge`, whose
module body runs the assignment before the shim's `from .meter.gauge import *` returns.
Keep the explanatory comment with the block (it is quoted by
`tests/ui/test_meter_annotations.py:66` as the reason the arrangement exists).

Alternative, if the writer prefers the smallest conceivable diff: leave the block in the
shim (`Gauge.py`) and have it import `meter.elements` / `meter.meter` exactly as today. It
still works for every current import path, but a future `bar.py` or any direct
`from .meter.gauge import Gauge` bypasses it.

Ordering inside `meter/gauge.py`: the hand-over is the **last** executable statement; it must
be after both class definitions, and `from . import meter as _meter_module` there is safe
because `meter/meter.py` is fully loaded by then (`gauge.py` imported it at the top).

### 4.4 The logger and `_gaugeKeyName`

- `Gauge.py:63` is `log = UILogger.getChild('Gauge')`. Following `meter/elements.py:67`
  (`'meter.elements'`) and `meter/meter.py:44` (`'meter'`), the moved module's own logger
  should be `log = UILogger.getChild('meter.gauge')`. This changes the log *channel*, not the
  message text; keep every message string byte-identical.
- `Gauge`'s warning paths call `_gaugeKeyName(self)`, imported at `Gauge.py:47-51` as
  `gaugeKeyName as _gaugeKeyName`. Importing it the same way in `meter/gauge.py`
  (`gaugeKeyName as _gaugeKeyName`) keeps every moved body byte-identical, which is what
  Job B's audit measures. The rename to `gaugeKeyName` (if wanted) belongs in the later
  names-only commit, with the log text unchanged.

---

## 5. Verification, and the things that will bite

### 5.1 `_studio_stage.py:40` binds the class, not the module — flag this

`Displays/__init__.py:49` is `from .Gauge import *`, and `Gauge.py` defines a module-level
name `Gauge` (L301). A star import copies that name into the package namespace, so
`Displays.Gauge` is the **class**, overwriting the submodule attribute the import system had
put there. Therefore:

- `_studio_stage.py:40` `from ...Displays import Gauge as _gaugeModule` gives the **class**;
- `_studio_stage.py:292` `_gaugeModule.openValueSource = _openValueSource` sets an attribute
  on the class, which is not the name `meter/elements.py` reads (`elements.py:55` imports
  `openValueSource` into its own globals; it is used at `elements.py:3116, :3444, :3658`).

Reproduced in isolation (a two-file package with the same shape: `__init__` does
`from .Gauge import *`, `Gauge.py` defines `class Gauge`):

```
pkgexp.Gauge                -> <class 'type'>   # class, not module
from pkgexp import Gauge    -> <class 'type'>
import pkgexp.Gauge as m    -> <class 'type'>   # even the `as` form resolves the attribute
```

Only `sys.modules['...Displays.Gauge']` gives the module object. So either the studio's
`installSources()` is a no-op for key-bound markers/fills/labels, or it never mattered
because the presets use plain numbers. **Verify before M3 relies on it**, and if M3 wants to
keep the studio working, the shim has to expose `openValueSource` as a real module attribute
that `meter/elements.py` reads (which it does not today — `elements.py` binds its own copy).
This is a pre-existing defect, not one M3 introduces; the recon records it so M3 does not
"fix" it by accident and does not preserve it by accident either.

### 5.2 The star-export check (run before and after M3)

```python
import ast
from pathlib import Path

def public_names(path):
    tree = ast.parse(Path(path).read_text())
    out = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(node.name)
        elif isinstance(node, ast.Assign):
            out |= {t.id for t in node.targets if isinstance(t, ast.Name)}
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            out |= {a.asname or a.name.split('.')[0] for a in node.names}
    return {n for n in out if not n.startswith('_')}

before = public_names('.../Displays/Gauge.py')      # at 1922538: 175 names
after  = public_names('.../Displays/Gauge.py')      # the shim, after M3
print(sorted(before - after))                        # must be empty
```

`before - after` is the check; run it against the shim (or against
`importlib.import_module(...)` and `vars()`, which is the same set).

### 5.3 Pyflakes/F821 is the fast net, not the gate

`.venv/bin/ruff check --no-cache --select F821,F811 <files>` on `meter/gauge.py` and the
repointed `elements.py`/`meter.py` catches a missed import in a second. It caught the
`GaugeArc` local annotation and the two missing import-backs earlier. It cannot catch
"right name, wrong object". The pixel diff is still the real gate:

```
.venv/bin/python -m pytest tests -q -p no:warnings
.venv/bin/python src/LevityDash/devtools/render_diff.py capture <dir> --jobs 4
.venv/bin/python src/LevityDash/devtools/render_diff.py compare .render-diff/baseline <dir>
```

### 5.4 Tests that must be updated alongside M3

- `tests/ui/test_meter_annotations.py:20-25` — add
  `'LevityDash.lib.ui.frontends.PySide.Modules.Displays.meter.gauge'` to `MODULES`, or the
  new module's `StateProperty.returns` and class annotations are never resolved and the
  trap M3 is most likely to hit is the one test that will not fire.
- Nothing else has to change: `test_gauge_tick_format.py:2`, `test_gauge_helpers.py:4` and
  `test_gauge_interval_steps.py:1` import from the shim and keep working.

### 5.5 Risk list, short

1. `from .meter.elements import *` silently drops the element classes (`__all__` is 6
   names). Use the explicit list in §1.4.
2. `_isWholeSteps` is private; only an explicit import keeps
   `tests/ui/test_gauge_interval_steps.py:1` green.
3. The two `test_meter_annotations` failures arrive as a **segfault** through pytest's rich
   repr before they arrive as a `NameError` — re-run with `--tb=native` if the suite dies.
4. `Gauge.value_to_angle` is defined twice at `1922538` (L799-801 and L1074-1075); the
   second wins. Move both verbatim, in order, or the shadowing changes.
5. `Gauge.radius` is likewise defined twice (L1004-1006 and L1008-1011); same rule.
6. `_studio_stage.py:40` binds the class (§5.1) — do not assume it gives the module.
7. `Gauge`'s class-level fields include `__value` (L305, L315). Python mangles it to
   `_Gauge__value`; moving the class body must keep the two `__value` rows together and the
   `_init_defaults_` write (L326) in the same class body.


## Review notes to carry into M3 (owner's review, 2026-10-05)

Two changes the review requires *inside* M3, and one to leave alone:

1. **The dial geometry goes to the Gauge side before a second Meter exists.**
   `center`, `scene_center`, `center_offset`, `_dialRect` and `_sideValueRect` are
   on `Meter` today, which is acceptable only because `Gauge` is the sole subclass.
   They are the dial's geometry, not the meter's, so they move back to the
   arc-side module as part of M3 — before `Bar` gives `Meter` a second subclass
   that would inherit a dial.
2. **`dependencies={'range', 'arc'}` names a key only `Gauge` owns.** `fill`,
   `zones`, `caption` and `sub-label` declare it on `Meter`. `range` is fine —
   Meter holds the range — but `arc` is a Gauge key, so a `Bar` would carry a
   dependency on a state item it does not have. Decide the shape in M3: either the
   dependency is split (Meter keeps `range`, the Arc-side declares `arc`), or the
   items that need `arc` move their declaration to the Gauge side.
3. **One mechanism for the hand-over, not two.** Once the hand-over runs from
   `meter/gauge.py`, `gauge_class()` can simply return that module's own `Gauge`
   global and the lazy import becomes a fallback rather than the mechanism. Fold
   them together there; do not add a third.
4. **Not this branch:** `meter/elements.py`'s `get(kwargs, 'gauge' 'parent', ...)`
   is a string-literal join, so the lookup key is `'gaugeparent'` and never
   matches. It came over unchanged and is filed as its own job — do not fix it
   inside M3.

## M3 step 2: the decisions (2026-10-05)

- **The dial geometry is Gauge-side again.** `center`, `scene_center`, `center_offset`
  (with its setter, decode and encode), `update_center_offset`, `_valueSide`,
  `_sideStripWidth`, `_underStripHeight`, `_dialRect` and `_sideValueRect` moved from
  `Meter` into `Gauge`. One seam is left and recorded rather than papered over:
  `Meter._valueAnchor` still calls `self._dialRect()` for the line that offsets the value
  box by the dial's centre. It is label layout and belongs on Meter; a `Bar` will have to
  answer that call, and that is the point at which a hook is worth writing.
- **The `arc` and `needle` dependencies stay where they are.** `fill`, `zones`, `caption`
  and `sub-label` declare `dependencies={'range', 'arc'}` on `Meter`; `markers` declares
  `{'range', 'needle'}` — a fourth case the review's list did not name. `dependencies`
  only feeds a property's set order (statekit `core.py:999`), and a key the class does not
  have is simply never satisfied: no error, no hidden write. `arc` and `needle` are Gauge
  keys, the only Meter that exists is a Gauge, so the ordering is correct today; when
  `Bar` arrives it declares the ordering its own items need.
- **One hand-over mechanism**, as the review asked: `gauge_class()` answers with
  `meter/gauge.py`'s own global once the hand-over has run, and the import is the
  fallback for a caller that runs first.
- `rebuild` is a `Meter` method, so the moved `center_offset` schedules
  `after=Meter.rebuild` — a decorator evaluates in the class body, where an inherited
  name is not visible. Same family as the `_FillEnd` swallow: a move takes the code but
  not the names it was reading.
