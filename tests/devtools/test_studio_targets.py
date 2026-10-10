"""The snap targets: the maths only. The drags themselves are checked in a real Studio window."""
import math

import pytest

from LevityDash.devtools import _studio_targets as targets


def test_a_share_near_a_fraction_lands_on_it():
	t = targets.near('fraction', 0.335, 0.01)
	assert (t.name, t.value) == ('1/3', pytest.approx(1 / 3))


def test_a_share_near_the_golden_ratio_lands_on_it_and_is_named():
	t = targets.near('fraction', 0.62, 0.01)
	assert t.name == '1/φ' and t.value == pytest.approx(1 / targets.PHI)
	assert targets.describe(t, 'fraction') == '1/φ · 61.8%'


def test_nothing_within_tolerance_is_none():
	assert targets.near('fraction', 0.45, 0.01) is None


def test_a_family_switched_off_is_not_a_target():
	assert targets.near('fraction', 0.618, 0.002, [targets.FRACTIONS_FAMILY]) is None
	assert targets.near('fraction', 0.5, 0.01, [targets.RATIOS_FAMILY]) is None


def test_an_offset_keeps_its_sign():
	t = targets.near('offset', -0.26, 0.02)
	assert t.value == pytest.approx(-0.25)


def test_angles_land_on_multiples_and_the_golden_angle():
	assert targets.near('angle', 134, 3).value == 135
	assert targets.near('angle', 134, 3).name == '3×45°'
	assert targets.near('angle', 22, 1) is None
	golden = targets.near('angle', 138, 1)
	assert golden.name == 'golden angle' and golden.value == pytest.approx(137.5077, abs=1e-3)
	assert targets.near('angle', -138, 1).value == pytest.approx(-137.5077, abs=1e-3)
	assert targets.near('angle', 138, 1, [targets.FRACTIONS_FAMILY]) is None


def test_every_ratio_and_its_reciprocal_is_listed():
	names = {t.name for t in targets._shareTargets([targets.RATIOS_FAMILY])}
	assert {'φ', '1/φ', '1/φ²', '√2', '1/√2', '16:9', '9:16'} <= names
