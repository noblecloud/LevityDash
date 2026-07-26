"""Labels in a row must share a baseline regardless of which glyphs they contain.

The graph's hour labels sat at two different heights: `12p`/`6p` rendered
~2px above `6a`/`12a`. The distinguishing factor was the descender.

`QPainterPath.addText` takes the BASELINE as its origin, but `_update_path`
derived that origin from `QFontMetricsF.tightBoundingRect` - the *ink*
extents, which hug the glyphs. A descender pushes the ink bottom below the
baseline and makes the ink box taller, so both the origin and the height
correction varied by string, and bottom-aligning by them displaced any label
containing a `p`.

Ink extents are still the right measure for fitting text *into* a box; they
are the wrong one for aligning text *within* a row. Vertical placement now
uses ascent/descent, which are constant for a font and size.

Note `VerticalCenter` never had the bug - centring makes the rect's bottom
exactly half its height, which cancels the height correction - so only the
Top and Bottom branches changed.
"""
import pytest

from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Annotations import AnnotationText

DESCENDERS = set('pgyqj')


def _rows(scene, tolerance: float = 3.0):
	"""Group annotation labels into visual rows by their baseline y."""
	labels = [i for i in scene.items() if isinstance(i, AnnotationText) and (i.text or '').strip()]
	placed = []
	for label in labels:
		text_pos = getattr(label, '_text_pos', None)
		if text_pos is None:
			continue
		placed.append((label.text.strip(), label.mapToScene(text_pos).y()))

	rows: list[list[tuple[str, float]]] = []
	for text, y in sorted(placed, key=lambda p: p[1]):
		if rows and abs(rows[-1][-1][1] - y) <= tolerance:
			rows[-1].append((text, y))
		else:
			rows.append([(text, y)])
	return rows


def test_mixed_descender_labels_share_a_baseline(dashboard):
	"""The reported bug: '12p'/'6p' vs '6a'/'12a' on the graph's hour axis."""
	rows = _rows(dashboard.scene)
	mixed = [
		row for row in rows
		if len(row) > 2
		and any(DESCENDERS & set(t) for t, _ in row)
		and any(not (DESCENDERS & set(t)) for t, _ in row)
	]
	assert mixed, 'expected at least one row mixing descender and non-descender labels'

	for row in mixed:
		ys = [y for _, y in row]
		spread = max(ys) - min(ys)
		labels = sorted({t for t, _ in row})
		assert spread < 0.5, f'labels {labels} span {spread:.3f}px of baseline'


def test_descender_labels_are_not_a_separate_row(dashboard):
	"""Guards the specific shape of the failure.

	Before the fix the hour labels formed *two* rows about 2px apart, split
	precisely by whether the string contained a descender. A row that is
	entirely descender-labels, sitting near a row that has none, is that
	failure returning.
	"""
	rows = _rows(dashboard.scene)
	hour_rows = [r for r in rows if all(t.rstrip('apm').isdigit() or t[:-1].isdigit() for t, _ in r)]
	for row in hour_rows:
		texts = {t for t, _ in row}
		if len(texts) < 2:
			continue
		all_descender = all(DESCENDERS & set(t) for t in texts)
		none_descender = not any(DESCENDERS & set(t) for t in texts)
		assert not (all_descender or none_descender) or len(texts) == 1, (
			f'row {sorted(texts)} is split by descender presence - the labels '
			f'are being aligned by ink extents again'
		)
