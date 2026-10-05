"""A palette of colours derived from one hue by a scheme (triadic, analogous, ...).

The colours are Oklch at fixed lightness and chroma, as in the color_sphere demo. Pure
Python: no Qt. ``Color`` reads ``{palette: {hue: 145, scheme: triadic}, index: 1}``.
"""
from LevityDash.lib.ui.colors import oklch as _oklch


class Palette:
	"""Colours from ``hue`` in the order of ``scheme``. Held as linear triples."""

	__slots__ = ('hue', 'scheme', 'lightness', 'chroma', '_linear')

	def __init__(self, hue: float = 145.0, scheme: str = 'triadic', lightness: float = _oklch.OKLCH_L, chroma: float = _oklch.OKLCH_C):
		self.hue = float(hue)
		self.scheme = scheme
		self.lightness = float(lightness)
		self.chroma = float(chroma)
		self._linear = _oklch.palette_linear(self.hue, scheme, self.lightness, self.chroma)

	@classmethod
	def decode(cls, data) -> 'Palette':
		"""From ``{hue: 145, scheme: triadic}``. ``lightness`` and ``chroma`` are optional; a bare number is a hue."""
		if isinstance(data, Palette):
			return data
		if isinstance(data, (int, float)) and not isinstance(data, bool):
			return cls(hue=data)
		if not isinstance(data, dict):
			raise TypeError(f'a palette is a mapping like {{hue: 145, scheme: triadic}}, not {data!r}')
		unknown = set(data) - {'hue', 'scheme', 'lightness', 'chroma'}
		if unknown:
			raise ValueError(f'unknown palette keys {sorted(map(str, unknown))}')
		return cls(**data)

	def __len__(self) -> int:
		return len(self._linear)

	def sample(self, index=None, at=None) -> _oklch.Triple:
		"""One colour as a linear triple: the ``index``-th, or a mix at ``at`` (0 to 1). Default: the first."""
		if index is not None and at is not None:
			raise ValueError('give index or at, not both')
		if at is not None:
			return _oklch.blend_linear(self._linear, float(at))
		return self._linear[int(index or 0) % len(self._linear)]

	def colors(self, emission: float | None = None, saturation: float = 1.0) -> list[_oklch.Triple]:
		"""Every colour as an encoded sRGB triple, through the emissive chain when ``emission`` is set."""
		if emission is None:
			return [_oklch.linear_to_srgb(c) for c in self._linear]
		return [_oklch.display_color(c, saturation, emission) for c in self._linear]

	def stops(self, count: int, emission: float | None = None, saturation: float = 1.0) -> list[_oklch.Triple]:
		"""``count`` colours spread evenly along the palette, mixed in linear light, as encoded sRGB triples."""
		count = max(1, int(count))
		out = []
		for i in range(count):
			linear = _oklch.blend_linear(self._linear, i / (count - 1) if count > 1 else 0.0)
			out.append(_oklch.linear_to_srgb(linear) if emission is None else _oklch.display_color(linear, saturation, emission))
		return out


__all__ = ('Palette',)
