"""`matchingGroup` on a label set (gauge tick labels, graph hour and day labels) puts every label in a size group.

Until this the label sets were in no group: a commented-out line in the gauge ticks and a
`sizeGroup.items = self` in `HourLabels` that no label ever joined.
"""
import pytest

from LevityDash.lib.ui.Groups import MatchAllSizeGroup


def _label_sets(dashboard):
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Annotations import AnnotationText

	seen = {}
	for item in dashboard.scene.items():
		if isinstance(item, AnnotationText):
			seen.setdefault(id(item.labelGroup), item.labelGroup)
	return [group for group in seen.values() if len(group)]


def test_label_sets_join_and_leave_a_group(dashboard):
	sets = _label_sets(dashboard)
	if not sets:
		pytest.skip('the default dashboard has no gauge tick labels or graph labels')
	labels = sets[0]
	assert labels.matchingGroup is None
	members = list(labels)

	labels.setItemState({'matchingGroup': {'group': 'local.annotation-test', 'matchAll': True}})
	group = labels.matchingGroup
	assert isinstance(group, MatchAllSizeGroup)
	assert all(label in group.items and label._sized is group for label in members)

	# A label added later joins too, and a deleted one leaves.
	extra = members[0]
	labels.remove(extra)
	group.removeItem(extra)
	assert extra not in group.items
	labels.append(extra)
	assert extra in group.items

	labels.matchingGroup = None
	assert not group.items
