from math import isclose

from LevityDash.lib.ui.frontends.PySide.Modules.Displays.curvetext import warp_point


def test_warp_point_keeps_middle_line_arc_length():
	# On the band's middle line the label centre stays put, and x maps to arc length.
	for side in (1, -1):
		assert warp_point(0.0, 5.0, 5.0, 100.0, side) == (0.0, 0.0)
		x, y = warp_point(10.0, 5.0, 5.0, 100.0, side)
		assert isclose(x, 100 * 0.0998334166, rel_tol=1e-6)
		# the middle line bends toward the dial centre: +y for upright, -y for flipped
		assert (y > 0) == (side == 1)
