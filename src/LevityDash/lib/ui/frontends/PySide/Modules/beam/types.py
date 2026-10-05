from enum import Enum


class Size(str, Enum):
	"""Preset controlling the beam shape and motion family."""

	SMALL = "sm"
	MEDIUM = "md"
	LINE = "line"
	PULSE_INNER = "pulse-inner"
	PULSE_OUTSIDE = "pulse-outside"

	@property
	def is_rotate(self) -> bool:
		return self in (Size.SMALL, Size.MEDIUM, Size.LINE)

	@property
	def is_pulse(self) -> bool:
		return self in (Size.PULSE_INNER, Size.PULSE_OUTSIDE)


class ColorVariant(str, Enum):
	COLORFUL = "colorful"
	MONO = "mono"
	OCEAN = "ocean"
	SUNSET = "sunset"

	@property
	def is_mono(self) -> bool:
		return self is ColorVariant.MONO


class Theme(str, Enum):
	DARK = "dark"
	LIGHT = "light"
	AUTO = "auto"


class ColorSpace(str, Enum):
	"""Color derivation for the beam blobs.

	HSV keeps the upstream `hue-rotate` / brightness / saturation filter chain.
	OKLCH re-derives the blobs from the color_sphere ring palette (L=0.70,
	C=0.20, ring hues 145/266/30) through the sphere's emissive display chain.
	"""

	HSV = "hsv"
	OKLCH = "oklch"
