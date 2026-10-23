"""Checks on a theme's palette, run when a theme is loaded. Pure Python, no Qt.

`design-standards.md` asks two things of colour: text must be readable on the ground, and two different quantities
must not look alike. So:

- contrast: `text`, `muted` and `faint` are measured against `background` (WCAG relative luminance; a colour with
  alpha is first laid over the background). Under 4.5:1 is a warning.
- hue: the data colours `series-1` to `series-6` are compared in Oklch. Two that are both coloured (chroma above
  0.04) and within 20 degrees of hue are too alike to tell two lines or two quantities apart.

`audit` returns the findings as text and never raises: a colour it cannot read is left out, because the theme's own
loading reports that. `check_theme` logs them once per theme.
"""
from __future__ import annotations

import math
from typing import Any, Optional

from LevityDash.lib.ui.colors import oklch

#: WCAG AA for body text.
MIN_CONTRAST = 4.5
#: Oklch chroma under which a colour reads as grey and has no hue to share.
MIN_CHROMA = 0.04
#: Degrees of hue under which two colours read as one hue.
MIN_HUE_GAP = 20.0

TEXT_TOKENS = ('text', 'muted', 'faint')
SERIES_TOKENS = tuple(f'series-{n}' for n in range(1, 7))


def _rgba(theme, token: str) -> Optional[tuple[float, float, float, float]]:
	"""The token as (r, g, b, a), each 0 to 1, or None when it cannot be read as a colour."""
	try:
		from LevityDash.lib.ui.colors.color import Color
		color = Color.decode(theme.resolve(f'${token}', 'colors'))
		return color.red / 255, color.green / 255, color.blue / 255, color.alpha / 255
	except Exception:  # noqa: BLE001
		return None


def luminance(rgb: tuple[float, float, float]) -> float:
	r, g, b = oklch.srgb_to_linear(rgb)
	return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
	"""WCAG contrast ratio, 1 to 21, of two opaque sRGB colours."""
	hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
	return (hi + 0.05) / (lo + 0.05)


def _over(fore: tuple[float, float, float, float], back: tuple[float, float, float]) -> tuple[float, float, float]:
	a = fore[3]
	return tuple(f * a + b * (1 - a) for f, b in zip(fore[:3], back))


def hue_chroma(rgb: tuple[float, float, float]) -> tuple[float, float]:
	"""(hue in degrees, chroma) of an sRGB colour in Oklch."""
	_, a, b = oklch.srgb_to_oklab(rgb)
	return math.degrees(math.atan2(b, a)) % 360, math.hypot(a, b)


def audit(theme) -> list[str]:
	"""What is wrong with the palette of `theme`, one sentence each; empty when nothing is."""
	found: list[str] = []
	ground = _rgba(theme, 'background')
	if ground is not None:
		back = ground[:3]
		for token in TEXT_TOKENS:
			if (fore := _rgba(theme, token)) is None:
				continue
			ratio = contrast(_over(fore, back), back)
			if ratio < MIN_CONTRAST:
				found.append(f'${token} is {ratio:.1f}:1 on $background; text needs {MIN_CONTRAST:g}:1')
	series = [(token, _rgba(theme, token)) for token in SERIES_TOKENS]
	hues = [(token, *hue_chroma(c[:3])) for token, c in series if c is not None]
	for i, (a, ha, ca) in enumerate(hues):
		for b, hb, cb in hues[i + 1:]:
			if ca < MIN_CHROMA or cb < MIN_CHROMA:
				continue
			gap = abs(ha - hb)
			gap = min(gap, 360 - gap)
			if gap < MIN_HUE_GAP:
				found.append(f'${a} and ${b} share a hue ({gap:.0f} degrees apart); two quantities in them look alike')
	return found


_checked: set[int] = set()


def check_theme(theme, log) -> list[str]:
	"""`audit` a theme once and log each finding as a warning that names the theme."""
	if id(theme) in _checked:
		return []
	_checked.add(id(theme))
	found = audit(theme)
	for message in found:
		log.warning(f'theme {theme.name!r}: {message}')
	return found
