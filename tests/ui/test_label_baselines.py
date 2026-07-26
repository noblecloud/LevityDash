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


def _rows(scene):
	"""Group annotation labels by the label group they belong to.

	Grouped by `labelGroup` rather than by proximity: a dashboard has several
	graphs, and their label rows can sit a few pixels apart, so a
	distance-based grouping merges two legitimately-separate rows and reports
	their offset as misalignment. Labels that must share a baseline are
	exactly those managed by the same AnnotationLabels group.
	"""
	groups: dict[int, list[tuple[str, float]]] = {}
	for label in scene.items():
		if not isinstance(label, AnnotationText) or not (label.text or '').strip():
			continue
		text_pos = getattr(label, '_text_pos', None)
		if text_pos is None:
			continue
		owner = id(getattr(label, 'labelGroup', None) or label.parentItem())
		groups.setdefault(owner, []).append((label.text.strip(), label.mapToScene(text_pos).y()))
	return list(groups.values())


def _median(values):
	ordered = sorted(values)
	return ordered[len(ordered) // 2]


def test_descenders_do_not_shift_a_label(dashboard):
	"""The reported bug: '12p'/'6p' sat above '6a'/'12a' on the hour axis.

	Asserted as the *invariant that was violated* rather than as a flat
	spread, on purpose. A group's labels can be legitimately offset for
	reasons that have nothing to do with glyphs - a couple of the hour
	labels sit ~3px low as a pair, independent of their descenders (see
	docs/tasks/text-baseline-alignment.md). A spread check would fold that
	unrelated offset into this test and make it fail for the wrong reason.

	What must hold is that descender-ness makes no difference: within one
	label group, labels containing a descender must sit at the same baseline
	as those without.
	"""
	rows = _rows(dashboard.scene)
	checked = 0
	for row in rows:
		with_desc = [y for t, y in row if DESCENDERS & set(t)]
		without = [y for t, y in row if not (DESCENDERS & set(t))]
		if not with_desc or not without:
			continue
		checked += 1
		offset = abs(_median(with_desc) - _median(without))
		labels = sorted({t for t, _ in row})
		assert offset < 0.5, (
			f'descender labels sit {offset:.3f}px off the others in {labels} - '
			f'text is being aligned by ink extents again'
		)
	assert checked, 'expected a label group mixing descender and non-descender labels'


def test_descender_labels_are_not_a_separate_row(dashboard):
	"""Guards the specific shape of the failure.

	Before the fix the hour labels formed *two* clusters about 2px apart,
	split precisely by whether the string contained a descender. Clustering
	a group's baselines and finding that the split lines up with descender
	presence is that failure returning.
	"""
	for row in _rows(dashboard.scene):
		if len(row) < 4:
			continue
		with_desc = {round(y, 1) for t, y in row if DESCENDERS & set(t)}
		without = {round(y, 1) for t, y in row if not (DESCENDERS & set(t))}
		if not with_desc or not without:
			continue
		labels = sorted({t for t, _ in row})
		assert with_desc & without, (
			f'no baseline is shared between descender and non-descender '
			f'labels in {labels} - they have separated into two rows'
		)
