"""Plain data types shared by the layout algorithms.

Everything here is Qt-free and in pixels. The caller resolves `%`, `mm` and the like to
pixels first (with `size_px` in `lib/ui/Geometry`) and passes floats in. `None` means `auto`
or "indefinite" wherever a size is optional. `math.inf` means "no maximum".

Main axis and cross axis follow the CSS spec. For a `Stack` with `direction: vertical`
the main axis is y.
"""

from dataclasses import dataclass
from enum import Enum
from math import inf
from typing import Callable, NamedTuple

__all__ = [
	'INF', 'Rect', 'Axis', 'Direction', 'Wrap', 'ContentAlign', 'ItemAlign', 'Alignment',
	'Measure', 'Gap', 'Edge',
]

INF = inf


class Rect(NamedTuple):
	x: float
	y: float
	width: float
	height: float


class Axis(Enum):
	"""`x` is the inline axis in a left-to-right layout."""
	x = 'x'
	y = 'y'


class Direction(Enum):
	"""`flex-direction`. `Stack.direction` maps to `row` (horizontal) and `column` (vertical)."""
	row = 'row'
	row_reverse = 'row-reverse'
	column = 'column'
	column_reverse = 'column-reverse'


class Wrap(Enum):
	"""`flex-wrap`."""
	nowrap = 'nowrap'
	wrap = 'wrap'
	wrap_reverse = 'wrap-reverse'


class ContentAlign(Enum):
	"""Values of `justify-content` and `align-content` (content distribution)."""
	normal = 'normal'
	start = 'start'
	end = 'end'
	flex_start = 'flex-start'
	flex_end = 'flex-end'
	center = 'center'
	space_between = 'space-between'
	space_around = 'space-around'
	space_evenly = 'space-evenly'
	stretch = 'stretch'


class ItemAlign(Enum):
	"""Values of `align-items`, `align-self`, `justify-items` and `justify-self`."""
	auto = 'auto'
	normal = 'normal'
	start = 'start'
	end = 'end'
	flex_start = 'flex-start'
	flex_end = 'flex-end'
	center = 'center'
	baseline = 'baseline'
	last_baseline = 'last baseline'
	stretch = 'stretch'


@dataclass(frozen=True, slots=True)
class Alignment:
	"""An alignment value with its overflow keyword: `safe center` is `Alignment(center, safe=True)`.

	Layouts here default to `safe` for centring. Text that is wider than its slot should run
	off the far edge, not the near edge, where it cannot be reached.
	"""
	value: ContentAlign | ItemAlign
	safe: bool = False


class Gap(NamedTuple):
	"""`row-gap` and `column-gap` in pixels. `normal` is 0 for flex and grid."""
	row: float = 0.0
	column: float = 0.0


class Edge(NamedTuple):
	"""A margin or other pair on one axis. `None` is `auto`, which takes free space."""
	start: float | None = 0.0
	end: float | None = 0.0


# A cross size for a given main size, for content whose height depends on its width
# (wrapped text, an item with `size-ratio`). `measure(main)` returns the cross size.
Measure = Callable[[float], float]
