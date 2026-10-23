"""Dev-only, Qt-free: checks on the rhythm of a dashboard, the spacing between things and where text sits on a line.

`design-standards.md` gives a dashboard one spacing scale (the theme's `space_1` to `space_6`). Two checks:

- spacing: a `spacing`, `gap`, `padding` or `margin` written as a length (`3mm`) that is not on the scale is named, with the
  nearest steps. A `$token`, a share (`%`), `0`, `auto`, `calc()` and pixel lengths (a pixel is a different size on each screen, so it has no place on a scale in millimetres) are left alone: they are on the scale or
  relative by construction.
- baselines: panels that sit side by side should start on one baseline. The first row of text of each panel (read from the
  fitted text rects of the size groups) is compared, for panels whose first rows are the same size; a small gap that is
  not zero reads as a mistake, a large one as a choice.

Findings are `_studio_tiers.Finding`, so the Size groups tab lists them with the tier checks.
"""
import re
from statistics import median
from typing import Any, Dict, Iterable, List, Optional, Tuple

from LevityDash.devtools._studio_tiers import Finding, NOTE, WARN

SPACING_KEYS = ('spacing', 'gap', 'padding', 'margin', 'margins')
#: A length may be this far from a step (mm) and still be on it: it covers the rounding of `1.0mm` against `1mm`.
TOLERANCE = 0.05
#: Pixels a baseline may differ by and still be one baseline; above `BASELINE_MAX` the difference is a choice.
BASELINE_SLACK = 1.5
BASELINE_MAX = 40.0

_LENGTH = re.compile(r'^\s*(-?\d*\.?\d+)\s*(mm|cm|in|pt)\s*$')
_TO_MM = {'mm': 1.0, 'cm': 10.0, 'in': 25.4, 'pt': 25.4 / 72}


def millimetres(value: Any) -> Optional[float]:
	"""`value` as millimetres when it is a plain absolute length, else None. A bare number is not a length here."""
	if isinstance(value, str) and (found := _LENGTH.match(value)):
		return float(found.group(1)) * _TO_MM[found.group(2)]
	return None


def scale(sizes: Dict[str, Any]) -> Dict[str, float]:
	"""The spacing steps (`space_1`...) of a theme's sizes, as {name: millimetres}."""
	steps = {}
	for name, value in sizes.items():
		if re.fullmatch(r'space_\d+', str(name)) and (mm := millimetres(value)) is not None:
			steps[str(name)] = mm
	return steps


def _lengths(value: Any) -> Iterable[str]:
	if isinstance(value, str):
		yield value
	elif isinstance(value, (list, tuple)):
		for v in value:
			yield from _lengths(v)
	elif isinstance(value, dict):
		for v in value.values():
			yield from _lengths(v)


def _scan(node: Any) -> Iterable[Tuple[str, str]]:
	"""(key, length text) for every spacing-like value in a mapping, below `items` excluded (the caller walks those)."""
	if isinstance(node, dict):
		for key, value in node.items():
			if key == 'items':
				continue
			if key in SPACING_KEYS:
				for text in _lengths(value):
					yield key, text
			elif isinstance(value, (dict, list)) and key in ('flex', 'grid', 'shared', 'display', 'geometry'):
				yield from _scan(value)
	elif isinstance(node, list):
		for value in node:
			yield from _scan(value)


def _where(path: tuple) -> str:
	return ''.join(f'[{i}]' for i in path) or 'root'


def check_spacing(nodes: Iterable[Tuple[tuple, dict]], steps: Dict[str, float]) -> List[Finding]:
	"""Findings for lengths that are not on `steps`. `nodes` is (path, item) for every item, as `Piece.walk` yields."""
	if not steps:
		return []
	on = sorted(steps.values())
	names = ', '.join(f'{v:g}' for v in on)
	out: List[Finding] = []
	for path, node in nodes:
		for key, text in _scan(node):
			mm = millimetres(text)
			if mm is None or mm == 0 or any(abs(mm - s) <= TOLERANCE for s in on):
				continue
			lower = max((s for s in on if s < mm), default=None)
			upper = min((s for s in on if s > mm), default=None)
			near = ' or '.join(f'{s:g}mm' for s in (lower, upper) if s is not None)
			out.append(Finding(NOTE, f'{_where(path)}: {key} {text} is not on the spacing scale ({names} mm); nearest {near}.', [], path))
	return out


def _panel(member) -> Optional[tuple]:
	path = getattr(member, 'path', None)
	return path[:1] if path else None


def check_baselines(found: Iterable) -> List[Finding]:
	"""Panels side by side whose first rows of text are the same size but sit on different baselines.

	`found` is the groups `_studio_groups.collect` returns. A panel is the top-level item a text is in. The first row of a
	panel is its text within half a line of its top; its baseline is the median bottom of that row's rects.
	"""
	panels: Dict[tuple, list] = {}
	for g in found:
		if getattr(g, 'unresolved', None):
			continue
		for m in g.members:
			if (p := _panel(m)) is not None and m.rect is not None:
				panels.setdefault(p, []).append(m)
	rows: List[Tuple[tuple, float, float, float, list]] = []  # path, top, baseline, font, members
	for p, members in panels.items():
		top = min(m.rect.top() for m in members)
		first = [m for m in members if m.rect.top() - top <= m.rect.height() * 0.5]
		rows.append((p, top, float(median(m.rect.bottom() for m in first)), float(median(m.font for m in first)), first))
	out: List[Finding] = []
	rows.sort(key=lambda r: r[1])
	for i, (pa, ta, ba, fa, ma) in enumerate(rows):
		for pb, tb, bb, fb, mb in rows[i + 1:]:
			if abs(fa - fb) > 1 or abs(ta - tb) > max(fa, fb):
				continue  # a different size or a different band: not meant to line up
			diff = abs(ba - bb)
			if BASELINE_SLACK < diff <= BASELINE_MAX:
				out.append(Finding(NOTE, f'{_where(pa)} and {_where(pb)} start on different baselines ({diff:.0f}px apart) at the same text size.', ma + mb))
	return out


def check(nodes: Iterable[Tuple[tuple, dict]], sizes: Dict[str, Any], found: Iterable) -> List[Finding]:
	"""Spacing findings in the order of the tree, then baseline findings."""
	return check_spacing(nodes, scale(sizes)) + check_baselines(found)
