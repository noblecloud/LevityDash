"""Oklch palette and emissive display chain, free of Qt.

Ported from ``border_beam/oklch.py`` (``~/Code/border-beam-qt``), which mirrors
``~/Code/color_sphere/demo.html`` one for one. The constants and the formulas keep
the demo's names and values on purpose: a "corrected" constant shows up as a byte
difference against the reference. Do not change them.

Every function takes and returns plain floats. ``Color`` turns the triples into bytes.

Two kinds of triple appear here, and mixing them up is the usual mistake:

- *linear* triples are light, as the demo's ``oklchToRgb`` returns it;
- *sRGB* triples are encoded for a display (the gamma curve is applied).

``oklch_color`` and ``oklch_to_linear`` give linear triples. ``display_color`` takes a
linear triple and gives an encoded one. ``linear_to_srgb`` encodes a plain colour.
"""

from __future__ import annotations

import math
import re

# Oklch primaries used by `oklchColor()`.
OKLCH_L: float = 0.70
OKLCH_C: float = 0.20

# `displayColor()` constants (from the demo).
EMISSION: float = 3.18  # `emission` slider default
EMISSION_MATERIAL: float = 3.2
EXPOSURE: float = 2.0 ** 0.25  # ~1.189
GAMMA: float = 1.0 / 2.2

# The demo's palette schemes: hue offsets in degrees from the base hue.
SCHEMES: dict[str, tuple[float, ...]] = {
	'triadic': (0, 120, 240),
	'split-complement': (0, 150, 210),
	'analogous': (0, 30, -30),
	'complementary': (0, 180, 30),
	'golden': (0, 137.5, 275),
}

Triple = tuple[float, float, float]


def oklch_to_linear(L: float, C: float, h_deg: float) -> Triple:
	"""Oklch to linear sRGB (the demo's `oklchToRgb` matrix). The result may lie outside 0..1."""
	rad = math.radians(h_deg)
	a = C * math.cos(rad)
	b = C * math.sin(rad)
	l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
	m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
	s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3
	r = 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
	g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
	b2 = -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s
	return r, g, b2


def oklch_color(hue: float, L: float = OKLCH_L, C: float = OKLCH_C) -> Triple:
	"""Gamut-clamped Oklch colour as a 0..1 *linear* triple.

	Mirrors `oklchColor(hue)`: a binary search lowers the chroma until the colour is
	inside sRGB, then the result is clamped to 0..1. ``L`` and ``C`` default to the
	demo's ring values.
	"""

	def _in_gamut(chroma: float) -> bool:
		r, g, b = oklch_to_linear(L, chroma, hue)
		return 0.0 <= r <= 1.0 and 0.0 <= g <= 1.0 and 0.0 <= b <= 1.0

	chroma = C
	if not _in_gamut(chroma):
		low, high = 0.0, C
		for _ in range(16):
			mid = (low + high) / 2.0
			if _in_gamut(mid):
				low = mid
			else:
				high = mid
		chroma = low
	r, g, b = oklch_to_linear(L, chroma, hue)
	return (min(1.0, max(0.0, r)), min(1.0, max(0.0, g)), min(1.0, max(0.0, b)))


def display_color(linear: Triple, saturation: float = 1.0, emission: float = EMISSION) -> Triple:
	"""The demo's `displayColor()`: boost, ACES-style tone map, gamma. Gives an *encoded* triple.

	`linear` must be a 0..1 linear triple (for example from :func:`oklch_color`).
	`emission` is the demo's emission slider. `saturation` is its saturation slider: a
	value other than 1 mixes each channel away from the smallest channel.
	"""
	boost = emission * EMISSION_MATERIAL * EXPOSURE
	boosted = [c * boost for c in linear]
	l = 0.2126 * boosted[0] + 0.7152 * boosted[1] + 0.0722 * boosted[2]
	m = l * (2.51 * l + 0.03) / (l * (2.43 * l + 0.59) + 0.14)
	scale = m / max(0.00001, l)
	max_c = max(1.0, max(c * scale for c in boosted))
	color = [math.pow(max(0.0, c * scale / max_c), GAMMA) for c in boosted]
	if saturation != 1.0:
		gray = min(color)
		color = [min(1.0, gray + (v - gray) * saturation) for v in color]
	return tuple(min(1.0, max(0.0, v)) for v in color)


def linear_to_srgb(linear: Triple) -> Triple:
	"""Encode a linear triple with the sRGB curve (a plain colour, no emission)."""
	out = []
	for c in linear:
		c = min(1.0, max(0.0, c))
		out.append(c * 12.92 if c <= 0.0031308 else 1.055 * math.pow(c, 1 / 2.4) - 0.055)
	return tuple(out)


def srgb_to_linear(srgb: Triple) -> Triple:
	"""Decode an encoded sRGB triple to linear light."""
	out = []
	for c in srgb:
		c = min(1.0, max(0.0, c))
		out.append(c / 12.92 if c <= 0.04045 else math.pow((c + 0.055) / 1.055, 2.4))
	return tuple(out)


def oklch_srgb(L: float, C: float, hue: float, emission: float | None = None, saturation: float = 1.0) -> Triple:
	"""One Oklch colour as an encoded sRGB triple.

	With ``emission`` ``None`` the colour is shown as it is. With a number it goes through
	:func:`display_color`, so a bright colour rolls off towards white the way light does.
	"""
	linear = oklch_color(hue, L, C)
	if emission is None:
		return linear_to_srgb(linear)
	return display_color(linear, saturation, emission)


def scheme_hues(base: float, scheme: str = 'triadic') -> list[float]:
	"""The hues of ``scheme`` around ``base``, in degrees, each in 0..360."""
	try:
		offsets = SCHEMES[scheme]
	except KeyError:
		raise ValueError(f'unknown palette scheme {scheme!r}; use one of {", ".join(SCHEMES)}') from None
	return [((base + o) % 360 + 360) % 360 for o in offsets]


def palette_linear(base: float, scheme: str = 'triadic', L: float = OKLCH_L, C: float = OKLCH_C) -> list[Triple]:
	"""The scheme's colours as linear triples, in scheme order."""
	return [oklch_color(h, L, C) for h in scheme_hues(base, scheme)]


def blend_linear(colors: list[Triple], t: float) -> Triple:
	"""A point along ``colors`` (0 first, 1 last), mixed in linear light as the demo does."""
	if len(colors) == 1:
		return colors[0]
	t = min(1.0, max(0.0, t)) * (len(colors) - 1)
	i = min(int(t), len(colors) - 2)
	f = t - i
	return tuple(a + (b - a) * f for a, b in zip(colors[i], colors[i + 1]))


def srgb_to_oklab(srgb: Triple) -> Triple:
	"""An encoded sRGB triple as Oklab (L, a, b), with Bjorn Ottosson's matrices."""
	r, g, b = srgb_to_linear(srgb)
	l = abs(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
	m = abs(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
	s = abs(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
	return (
		0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
		1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
		0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s,
	)


def oklab_to_srgb(lab: Triple) -> Triple:
	"""Oklab (L, a, b) as an encoded sRGB triple, clamped into gamut."""
	L, a, b = lab
	l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
	m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
	s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3
	return linear_to_srgb((
		4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
		-1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
		-0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
	))


def mix_oklab(a: Triple, b: Triple, t: float) -> Triple:
	"""Mix two encoded sRGB colours in Oklab. Blue to yellow stays light through the middle, not grey."""
	la, lb = srgb_to_oklab(a), srgb_to_oklab(b)
	return oklab_to_srgb(tuple(x + (y - x) * t for x, y in zip(la, lb)))


def oklab_stops(stops: list, steps: int = 16) -> list:
	"""Add ``steps - 1`` Oklab-mixed stops between each pair of ``(position, (r, g, b, a))`` stops (colours 0..1, encoded).

	Qt mixes gradient stops in sRGB, so the way to get Oklab is more stops. Alpha mixes straight.
	"""
	out = []
	stops = sorted(stops, key=lambda s: s[0])
	for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
		out.append((p0, c0))
		for i in range(1, steps):
			t = i / steps
			rgb = mix_oklab(c0[:3], c1[:3], t)
			out.append((p0 + (p1 - p0) * t, (*rgb, c0[3] + (c1[3] - c0[3]) * t)))
	if stops:
		out.append(stops[-1])
	return out


_NUMBER = r'[-+]?(?:\d+\.?\d*|\.\d+)'
_OKLCH = re.compile(
	rf'^\s*oklch\(\s*({_NUMBER})(%?)[\s,]+({_NUMBER})(%?)[\s,]+({_NUMBER})(?:deg)?\s*(?:/\s*({_NUMBER})(%?)\s*)?\)\s*$',
	re.IGNORECASE,
)


def is_oklch(text: str) -> bool:
	"""Whether ``text`` looks like an ``oklch(...)`` colour (it may still fail to parse)."""
	return text.lstrip().lower().startswith('oklch(')


def parse_oklch(text: str) -> tuple[float, float, float, float]:
	"""Read ``oklch(L C h)`` into ``(L, C, h, alpha)``.

	``L`` is 0..1 or a percentage, ``C`` is 0..0.4 or a percentage of 0.4, ``h`` is degrees
	(``deg`` is allowed), and ``/ alpha`` is optional (0..1 or a percentage). Commas are allowed.
	"""
	match = _OKLCH.match(text)
	if match is None:
		raise ValueError(f'not an oklch colour: {text!r}; write oklch(0.70 0.20 145)')
	lightness, lp, chroma, cp, hue, alpha, ap = match.groups()
	L = float(lightness) / 100 if lp else float(lightness)
	C = float(chroma) / 100 * 0.4 if cp else float(chroma)
	a = 1.0 if alpha is None else (float(alpha) / 100 if ap else float(alpha))
	if not 0.0 <= L <= 1.0:
		raise ValueError(f'oklch lightness must be 0 to 1, not {lightness}{lp}')
	if C < 0:
		raise ValueError(f'oklch chroma cannot be negative: {chroma}{cp}')
	return L, C, float(hue), min(1.0, max(0.0, a))


__all__ = (
	'OKLCH_L', 'OKLCH_C', 'EMISSION', 'EMISSION_MATERIAL', 'EXPOSURE', 'GAMMA', 'SCHEMES',
	'oklch_to_linear', 'oklch_color', 'display_color', 'linear_to_srgb', 'srgb_to_linear',
	'oklch_srgb', 'srgb_to_oklab', 'oklab_to_srgb', 'mix_oklab', 'oklab_stops', 'scheme_hues', 'palette_linear', 'blend_linear', 'is_oklch', 'parse_oklch',
)
