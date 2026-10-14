"""Pure-Python ports of the CSS layout algorithms that `Stack` lacks.

Status: skeleton. Every function raises `NotImplementedError`. Nothing in the app imports
this package yet, so no board changes.

Why: the dashboard layout system is modelled on CSS (docs in the project folder:
`css-mapping.md`). `Stack` is a one-line flex container with fixed items and an equal split of
the rest. Missing are grow and shrink factors, alignment, wrap and grid tracks.

Rules for the filling threads
- One spec section per task. Find the function by its `@implements(...)` line.
- Port from the spec text only. Never from Taffy, a browser, or any other implementation.
- Pure functions. No Qt, no `lib.ui`. Pixels in, pixels out (see `types.py`).
- Tests come from the examples in the spec text. Put them in `tests/layout/`.
- When a stub is done, set `status='done'` in its decorator and remove `NotImplementedError`.
- Do not wire anything into `Stack` in these tasks. The wiring is a separate reviewed change.

Layout of the package
- `spec.py`   registry of spec sections (`python -m LevityDash.lib.layout` lists what is left)
- `types.py`  shared data types
- `align.py`  CSS Box Alignment: gaps, content distribution, self-alignment, baselines
- `flex.py`   CSS Flexbox section 9
- `grid.py`   CSS Grid sections 7, 8 and 12
- `legacy.py` how today's `Stack` maps to flex, so existing boards render the same
"""

from . import align, flex, grid, legacy, types
from .spec import REGISTRY, Section, implements, pending

__all__ = ['align', 'flex', 'grid', 'legacy', 'types', 'REGISTRY', 'Section', 'implements', 'pending']
