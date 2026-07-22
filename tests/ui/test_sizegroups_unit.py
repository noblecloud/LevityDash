"""Unit tests for the stateless size-group engine (refit/fit_for/partition).

No Qt scene: a ``SizeGroup`` is built with a bare parent and lightweight stub
items whose size/scale/position/cluster/alignment are injectable, so the
partition + scale + baseline math is exercised deterministically.
"""
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from LevityDash.lib.ui.Groups import SizeGroup, MatchAllSizeGroup, SizeGroupItem, Fit


class _Pt:
	def __init__(self, y):
		self._y = y

	def y(self):
		return self._y


class _Item:
	"""A SizeGroupItem stub. ``cluster`` controls get_neighbors grouping."""

	def __init__(self, size=20.0, scale=1.0, y=0.0, cluster=0, valign="center", text=""):
		self._size = size
		self._scale = scale
		self._y = y
		self._cluster = cluster
		self._valign = valign
		self.text = text
		self._sized = None

	@property
	def suggestedFontPixelSize(self):
		return self._size

	def getTextScale(self):
		return self._scale

	def getTextScenePosition(self):
		return _Pt(self._y)

	def get_neighbors(self, reach, items):
		return {i for i in items if getattr(i, "_cluster", object()) == self._cluster}

	@property
	def alignment(self):
		return SimpleNamespace(vertical=self._valign)

	# remaining protocol members (present so isinstance passes; unused here)
	def getTextPosition(self):
		return _Pt(self._y)

	@property
	def limitRect(self):
		return None

	@property
	def containingRect(self):
		return None

	def scaleSelection(self, *e, **k):
		return min(e)

	def overlap_shape(self, reach):
		return None

	def scene_overlap_shape(self, reach):
		return None


@pytest.fixture
def make_group():
	"""Build throwaway SizeGroups and unregister them from the class list after."""
	created = []

	def _make(items=(), matchAll=False):
		g = SizeGroup(parent=SimpleNamespace(is_loading=False, state_is_loading=False),
		              key="test", matchAll=matchAll)
		for it in items:
			g.addItem(it)
		created.append(g)
		return g

	yield _make
	for g in created:
		try:
			SizeGroup.__groups__.remove(g)
		except ValueError:
			pass


def test_stub_satisfies_protocol():
	assert isinstance(_Item(), SizeGroupItem)


# --------------------------------------------------------------------------- #
# make_size_key: bucket a size to the nearest reach step, floored at reach
# --------------------------------------------------------------------------- #
def test_make_size_key(make_group):
	g = make_group()
	assert g.make_size_key(_Item(size=12.0)) == 10
	assert g.make_size_key(_Item(size=26.9)) == 30
	assert g.make_size_key(_Item(size=1.0)) == 10   # floored at one reach
	assert g.make_size_key(_Item(size=28.0)) == g.make_size_key(_Item(size=31.0)) == 30


# --------------------------------------------------------------------------- #
# tiers: unlike sizes split, near sizes share
# --------------------------------------------------------------------------- #
def test_tiers_partition(make_group):
	small = [_Item(size=12) for _ in range(2)]
	big = [_Item(size=40) for _ in range(3)]
	g = make_group(small + big)
	tiers = g._tiers(g.items)
	assert len(tiers) == 2
	assert {len(t) for t in tiers.values()} == {2, 3}


# --------------------------------------------------------------------------- #
# font_size_for: tier-scoped min suggestedFontPixelSize (cheap, no getTextScale)
# --------------------------------------------------------------------------- #
def test_font_size_is_tier_min(make_group):
	a, b = _Item(size=40), _Item(size=38)   # same tier (key 40)
	c = _Item(size=12)                        # different tier
	g = make_group([a, b, c])
	assert g.font_size_for(a) == 38
	assert g.font_size_for(b) == 38
	assert g.font_size_for(c) == 12


# --------------------------------------------------------------------------- #
# refit scale: min getTextScale within a cluster; clusters are independent (#3)
# --------------------------------------------------------------------------- #
def test_scale_is_per_cluster_min(make_group):
	# same tier (size 20), two clusters; cluster A wants 0.5, cluster B wants 0.9
	a1 = _Item(size=20, scale=0.5, cluster="A")
	a2 = _Item(size=20, scale=0.7, cluster="A")
	b1 = _Item(size=20, scale=0.9, cluster="B")
	g = make_group([a1, a2, b1])
	assert g.fit_for(a1).scale == 0.5
	assert g.fit_for(a2).scale == 0.5    # shares cluster A's min
	assert g.fit_for(b1).scale == 0.9    # cluster B is independent


def test_grow_to_fill_scale_above_one(make_group):
	g = make_group([_Item(size=20, scale=1.4, cluster="A"), _Item(size=20, scale=2.1, cluster="A")])
	assert g.fit_for(_first(g)).scale >= 1.4   # unclamped, > 1


# --------------------------------------------------------------------------- #
# refit baseline: mean scene-y of the aligned members in the cluster (#4)
# --------------------------------------------------------------------------- #
def test_baseline_is_mean_of_aligned(make_group):
	a = _Item(size=20, y=10, cluster="A", valign="center")
	b = _Item(size=20, y=30, cluster="A", valign="center")
	g = make_group([a, b])
	assert g.fit_for(a).baseline_y == 20      # mean of 10 and 30
	assert g.fit_for(b).baseline_y == 20


def test_different_alignment_splits_baseline(make_group):
	top = _Item(size=20, y=10, cluster="A", valign="top")
	bottom = _Item(size=20, y=30, cluster="A", valign="bottom")
	g = make_group([top, bottom])
	# different vertical alignment -> separate groups -> own baselines
	assert g.fit_for(top).baseline_y == 10
	assert g.fit_for(bottom).baseline_y == 30


# --------------------------------------------------------------------------- #
# MatchAll: whole tier is one cluster, no alignment split, no baseline
# --------------------------------------------------------------------------- #
def test_matchall_shares_one_scale_and_no_baseline(make_group):
	a = _Item(size=20, scale=0.5, cluster="A", valign="top")
	b = _Item(size=20, scale=0.9, cluster="B", valign="bottom")  # different cluster+align
	g = make_group([a, b], matchAll=True)
	assert isinstance(g, MatchAllSizeGroup)
	assert g.fit_for(a).scale == g.fit_for(b).scale == 0.5   # whole tier shares min
	assert g.fit_for(a).baseline_y is None                   # keeps own position


def _first(group):
	return next(iter(group.items))
