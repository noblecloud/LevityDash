"""Pure-math unit tests for the size-group partition/scale/baseline functions.

No Qt scene: the functions are exercised with lightweight stub items and a
fake ``self`` (unbound-method calls), so they stay fast and deterministic and
keep protecting the math while the engine gets rewritten/rewired.

`SizeGroupItem` is a @runtime_checkable Protocol, so a stub carrying the right
members satisfies the isinstance checks inside `make_size_key`.
"""
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from LevityDash.lib.ui.Groups import SizeGroup, SizeGroupItem

SubGroup = SizeGroup.SubGroup


class _Pt:
	def __init__(self, y):
		self._y = y

	def y(self):
		return self._y


class _Item:
	"""Minimal SizeGroupItem: every protocol member present, values injectable."""

	def __init__(self, size=20.0, scale=1.0, y=0.0, text=""):
		self._size = size
		self._scale = scale
		self._y = y
		self.text = text

	# --- the members the functions under test actually read ---
	@property
	def suggestedFontPixelSize(self):
		return self._size

	def getTextScale(self):
		return self._scale

	def getTextScenePosition(self):
		return _Pt(self._y)

	# --- remaining protocol members (unused here, present for isinstance) ---
	def getTextPosition(self):
		return _Pt(self._y)

	@property
	def limitRect(self):
		return None

	@property
	def containingRect(self):
		return None

	def get_neighbors(self, reach, items):
		return set()

	def scaleSelection(self, *elements, **kwargs):
		return min(elements)

	def overlap_shape(self, reach):
		return None

	def scene_overlap_shape(self, reach):
		return None


def test_stub_satisfies_protocol():
	assert isinstance(_Item(), SizeGroupItem)


# --------------------------------------------------------------------------- #
# make_size_key: buckets a size to the nearest `reach` step, floored at reach
# --------------------------------------------------------------------------- #
def _make_key(size):
	fake = SimpleNamespace(reach=10, SubGroup=SubGroup)
	return SizeGroup.make_size_key(fake, _Item(size=size))


def test_make_size_key_buckets_to_reach_step():
	assert _make_key(12.0) == 10   # rounds to nearest 10
	assert _make_key(26.9) == 30
	assert _make_key(41.5) == 40


def test_make_size_key_floored_at_reach():
	assert _make_key(1.0) == 10    # never below one reach step
	assert _make_key(5.0) == 10


def test_make_size_key_near_sizes_share_bucket():
	assert _make_key(28.0) == _make_key(31.0) == 30


def test_make_size_key_unlike_sizes_split():
	assert _make_key(12.0) != _make_key(40.0)


# --------------------------------------------------------------------------- #
# get_scale_for_cluster / get_size_for_cluster: aggregation over a cluster
# --------------------------------------------------------------------------- #
def test_cluster_scale_min_max_ave():
	cluster = {_Item(scale=0.4), _Item(scale=0.7), _Item(scale=1.0)}
	assert SubGroup.get_scale_for_cluster(None, cluster, "min") == 0.4
	assert SubGroup.get_scale_for_cluster(None, cluster, "max") == 1.0
	assert SubGroup.get_scale_for_cluster(None, cluster, "ave") == pytest.approx((0.4 + 0.7 + 1.0) / 3)


def test_cluster_size_min():
	cluster = {_Item(size=12), _Item(size=27), _Item(size=42)}
	assert SubGroup.get_size_for_cluster(None, cluster, "min") == 12
	assert SubGroup.get_size_for_cluster(None, cluster, "max") == 42


def test_cluster_scale_grows_above_one():
	"""#5 grow-to-fill: the shared scale is a raw ratio, never clamped to <=1."""
	cluster = {_Item(scale=1.4), _Item(scale=2.1)}
	assert SubGroup.get_scale_for_cluster(None, cluster, "min") == 1.4  # > 1, unclamped


# --------------------------------------------------------------------------- #
# group_y: baseline = mean scene-y of the aligned members (#4's pure function)
# --------------------------------------------------------------------------- #
def test_group_y_is_mean_of_aligned_members():
	members = {_Item(y=10.0), _Item(y=20.0), _Item(y=30.0)}
	fake = SimpleNamespace(get_similar_aligned_items=lambda item: members)
	assert SubGroup.group_y(fake, _Item()) == 20.0


def test_group_y_handles_single_member():
	members = {_Item(y=42.0)}
	fake = SimpleNamespace(get_similar_aligned_items=lambda item: members)
	assert SubGroup.group_y(fake, _Item()) == 42.0
