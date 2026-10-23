"""A size condition for `when:`, in the spirit of CSS media and container queries.

```yaml
when: {min-width: 1200px}                       # the window is at least this wide
when: {max-width: 800px, orientation: portrait}
when: {of: parent, min-aspect: 16:9}            # the item's parent, not the window
when: {min-width: 1200px, and: environment.precipitation.precipitation > 0}   # size and data
```

Size is a fact of the display, so it is read where the item is drawn (the window, or the item's parent) and never
goes through the plugin layer or a backend. `and:` takes the same value source as a plain `when:`, so the two
combine: the item shows while both hold.

Qt-free: `SizeQuery.parse` checks the mapping and `matches(width, height)` is arithmetic, so a test can call both.
"""
import re
from dataclasses import dataclass
from typing import Any, Mapping, Optional

__all__ = ['SizeQuery', 'SIZE_KEYS', 'isSizeQuery']

SIZE_KEYS = ('min-width', 'max-width', 'min-height', 'max-height', 'min-aspect', 'max-aspect', 'orientation', 'of', 'and')
SCOPES = ('window', 'parent')
ORIENTATIONS = ('landscape', 'portrait')
_PIXELS = re.compile(r'^\s*(\d+(?:\.\d+)?)\s*(?:px)?\s*$')
_RATIO = re.compile(r'^\s*(\d+(?:\.\d+)?)\s*[:/]\s*(\d+(?:\.\d+)?)\s*$')


def isSizeQuery(spec: Any) -> bool:
	"""True for a mapping `when:`; whether it is a good one is `SizeQuery.parse`'s to say."""
	return isinstance(spec, Mapping)


def _pixels(name: str, value: Any) -> float:
	if isinstance(value, bool):
		raise ValueError(f'{name}: {value!r} is not a size in pixels')
	if isinstance(value, (int, float)):
		return float(value)
	if isinstance(value, str) and (match := _PIXELS.match(value)):
		return float(match.group(1))
	raise ValueError(f'{name}: {value!r} must be a number of pixels such as 900 or 900px (other units are not supported)')


def _ratio(name: str, value: Any) -> float:
	if isinstance(value, bool):
		raise ValueError(f'{name}: {value!r} is not a ratio')
	if isinstance(value, (int, float)):
		return float(value)
	if isinstance(value, str):
		if match := _RATIO.match(value):
			return float(match.group(1)) / float(match.group(2))
		try:
			return float(value)
		except ValueError:
			pass
	raise ValueError(f'{name}: {value!r} must be a number or a ratio such as 16:9')


@dataclass(frozen=True)
class SizeQuery:
	minWidth: Optional[float] = None
	maxWidth: Optional[float] = None
	minHeight: Optional[float] = None
	maxHeight: Optional[float] = None
	minAspect: Optional[float] = None
	maxAspect: Optional[float] = None
	orientation: Optional[str] = None
	of: str = 'window'
	#: A value source that must also hold, or None.
	data: Any = None

	@classmethod
	def parse(cls, spec: Mapping) -> 'SizeQuery':
		unknown = [str(key) for key in spec if key not in SIZE_KEYS]
		if unknown:
			raise ValueError(f'when: unknown key {", ".join(unknown)}; a size condition knows {", ".join(SIZE_KEYS)}')
		of = str(spec.get('of', 'window')).strip().lower()
		if of not in SCOPES:
			raise ValueError(f'of: {of!r} must be one of {", ".join(SCOPES)}')
		orientation = spec.get('orientation')
		if orientation is not None:
			orientation = str(orientation).strip().lower()
			if orientation not in ORIENTATIONS:
				raise ValueError(f'orientation: {orientation!r} must be one of {", ".join(ORIENTATIONS)}')
		query = cls(
			minWidth=_pixels('min-width', spec['min-width']) if 'min-width' in spec else None,
			maxWidth=_pixels('max-width', spec['max-width']) if 'max-width' in spec else None,
			minHeight=_pixels('min-height', spec['min-height']) if 'min-height' in spec else None,
			maxHeight=_pixels('max-height', spec['max-height']) if 'max-height' in spec else None,
			minAspect=_ratio('min-aspect', spec['min-aspect']) if 'min-aspect' in spec else None,
			maxAspect=_ratio('max-aspect', spec['max-aspect']) if 'max-aspect' in spec else None,
			orientation=orientation,
			of=of,
			data=spec.get('and'),
		)
		for low, high, name in ((query.minWidth, query.maxWidth, 'width'), (query.minHeight, query.maxHeight, 'height'),
		                        (query.minAspect, query.maxAspect, 'aspect')):
			if low is not None and high is not None and low > high:
				raise ValueError(f'min-{name} {low:g} is more than max-{name} {high:g}, so nothing can match')
		return query

	def matches(self, width: float, height: float) -> bool:
		"""The size half of the condition. A size of nothing (an item not laid out yet) matches nothing."""
		if width <= 0 or height <= 0:
			return False
		checks = (
			self.minWidth is None or width >= self.minWidth,
			self.maxWidth is None or width <= self.maxWidth,
			self.minHeight is None or height >= self.minHeight,
			self.maxHeight is None or height <= self.maxHeight,
			self.minAspect is None or width / height >= self.minAspect,
			self.maxAspect is None or width / height <= self.maxAspect,
			self.orientation is None or (width >= height) == (self.orientation == 'landscape'),
		)
		return all(checks)
