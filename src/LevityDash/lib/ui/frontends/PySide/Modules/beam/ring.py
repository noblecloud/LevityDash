"""The beam's Oklch ring colours, built on LevityDash's own Oklch module.

``border-beam-qt`` had its own ``oklch.py``. LevityDash ported that file into
``lib/ui/colors/oklch.py`` (phase 1 of docs/tasks/emissive-color-and-glow.md), so the beam uses
that one and only keeps the ring helper that was specific to it.
"""

from PySide6.QtGui import QColor

from LevityDash.lib.ui.colors.oklch import display_color, oklch_color

# Ring palette hues (A/B/C) from the colour sphere's default source.
SPHERE_RING_HUES: tuple[float, float, float] = (145.0, 266.0, 30.0)

_RING_LEN = len(SPHERE_RING_HUES)


def ring_color(index: int, hue_deg: float, saturation: float = 1.0, brightness: float = 1.0) -> QColor:
	"""Sphere ring blob colour (lightness and chroma fixed) for a palette index, as an opaque QColor.

	``hue_deg`` is the caller's rotation, added to the ring hue. ``brightness`` scales the linear
	value before the display chain, like an exposure change, so the theme brightness keeps its
	meaning in Oklch mode.
	"""
	hue = (SPHERE_RING_HUES[index % _RING_LEN] + hue_deg) % 360.0
	linear = tuple(c * brightness for c in oklch_color(hue))
	r, g, b = display_color(linear, saturation)
	return QColor(round(r * 255), round(g * 255), round(b * 255))
