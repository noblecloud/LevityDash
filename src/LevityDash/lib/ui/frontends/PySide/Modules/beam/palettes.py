"""Ported color data and color math from the upstream `styles.ts`.

The effect is built from fixed color "blobs" (radial-gradient ellipses) placed
at fixed percentage positions around the border. Each preset reveals/moves
them differently (rotating soft window, traveling line, breathing pulse).
All tables below are copied verbatim from the React project so a future sync
is a mechanical copy-paste.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from PySide6.QtGui import QColor

from .types import ColorVariant, Theme

_SIZE_RE = re.compile(r"(\d+(?:\.\d+)?)px\s+(\d+(?:\.\d+)?)px")
_POS_RE = re.compile(r"(-?\d+(?:\.\d+)?)%\s+(-?\d+(?:\.\d+)?)%")
_RGB_RE = re.compile(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*([\d.]+))?\s*\)")


@dataclass(frozen=True)
class Blob:
	"""One radial-gradient ellipse: color, position (fractions), size (px)."""

	color: QColor
	x: float  # 0..1 of element width
	y: float  # 0..1 of element height (may be negative or > 1)
	w: float  # ellipse rx in px
	h: float  # ellipse ry in px

	@classmethod
	def parse(cls, color: str, pos: str, size: str) -> Blob:
		m = _RGB_RE.match(color)
		assert m, color
		r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
		alpha = float(m.group(4)) if m.group(4) else 1.0
		px, py = _POS_RE.match(pos).groups()
		sw, sh = _SIZE_RE.match(size).groups()
		return cls(
			QColor(r, g, b, round(alpha * 255)),
			float(px) / 100.0,
			float(py) / 100.0,
			float(sw),
			float(sh),
		)


# ---------------------------------------------------------------- rotate md/sm

# 9 gradient blobs per variant (positions/sizes from upstream `colorPalettes`).
BORDER_PALETTES: dict[ColorVariant, list[Blob]] = {
	ColorVariant.COLORFUL: [
		Blob.parse("rgb(255, 50, 100)", "33% -7.4%", "70px 40px"),
		Blob.parse("rgb(40, 140, 255)", "12% -5%", "60px 35px"),
		Blob.parse("rgb(50, 200, 80)", "2.1% 68.3%", "40px 70px"),
		Blob.parse("rgb(30, 185, 170)", "2.1% 68.3%", "20px 35px"),
		Blob.parse("rgb(100, 70, 255)", "74.4% 100%", "180px 32px"),
		Blob.parse("rgb(40, 140, 255)", "55% 100%", "85px 26px"),
		Blob.parse("rgb(255, 120, 40)", "93.9% 0%", "74px 32px"),
		Blob.parse("rgb(240, 50, 180)", "100% 27.1%", "26px 42px"),
		Blob.parse("rgb(180, 40, 240)", "100% 27.1%", "52px 48px"),
	],
	ColorVariant.MONO: [
		Blob.parse("rgb(180, 180, 180)", "33% -7.4%", "70px 40px"),
		Blob.parse("rgb(140, 140, 140)", "12% -5%", "60px 35px"),
		Blob.parse("rgb(160, 160, 160)", "2.1% 68.3%", "40px 70px"),
		Blob.parse("rgb(130, 130, 130)", "2.1% 68.3%", "20px 35px"),
		Blob.parse("rgb(170, 170, 170)", "74.4% 100%", "180px 32px"),
		Blob.parse("rgb(150, 150, 150)", "55% 100%", "85px 26px"),
		Blob.parse("rgb(190, 190, 190)", "93.9% 0%", "74px 32px"),
		Blob.parse("rgb(145, 145, 145)", "100% 27.1%", "26px 42px"),
		Blob.parse("rgb(165, 165, 165)", "100% 27.1%", "52px 48px"),
	],
	ColorVariant.OCEAN: [
		Blob.parse("rgb(100, 80, 220)", "33% -7.4%", "70px 40px"),
		Blob.parse("rgb(60, 120, 255)", "12% -5%", "60px 35px"),
		Blob.parse("rgb(80, 100, 200)", "2.1% 68.3%", "40px 70px"),
		Blob.parse("rgb(50, 140, 220)", "2.1% 68.3%", "20px 35px"),
		Blob.parse("rgb(120, 80, 255)", "74.4% 100%", "180px 32px"),
		Blob.parse("rgb(70, 130, 255)", "55% 100%", "85px 26px"),
		Blob.parse("rgb(140, 100, 240)", "93.9% 0%", "74px 32px"),
		Blob.parse("rgb(90, 110, 230)", "100% 27.1%", "26px 42px"),
		Blob.parse("rgb(130, 70, 255)", "100% 27.1%", "52px 48px"),
	],
	ColorVariant.SUNSET: [
		Blob.parse("rgb(255, 80, 50)", "33% -7.4%", "70px 40px"),
		Blob.parse("rgb(255, 160, 40)", "12% -5%", "60px 35px"),
		Blob.parse("rgb(255, 120, 60)", "2.1% 68.3%", "40px 70px"),
		Blob.parse("rgb(255, 200, 50)", "2.1% 68.3%", "20px 35px"),
		Blob.parse("rgb(255, 100, 80)", "74.4% 100%", "180px 32px"),
		Blob.parse("rgb(255, 180, 60)", "55% 100%", "85px 26px"),
		Blob.parse("rgb(255, 60, 60)", "93.9% 0%", "74px 32px"),
		Blob.parse("rgb(255, 140, 50)", "100% 27.1%", "26px 42px"),
		Blob.parse("rgb(255, 90, 70)", "100% 27.1%", "52px 48px"),
	],
}

# Inner glow blobs: same colors at 0.45 alpha (0.225 mono), 0.9x size.
def inner_blobs(variant: ColorVariant) -> list[Blob]:
	mono_alpha = 0.225 if variant.is_mono else 0.45
	out = []
	for b in BORDER_PALETTES[variant]:
		c = QColor(b.color)
		c.setAlphaF(mono_alpha)
		out.append(Blob(c, b.x, b.y, b.w * 0.9, b.h * 0.9))
	return out


# sm palette: 8 blobs + 8 inner blobs (rgba already baked in).
SMALL_BORDER: dict[ColorVariant, list[Blob]] = {
	ColorVariant.COLORFUL: [
		Blob.parse("rgb(50, 200, 80)", "2% 68%", "9px 18px"),
		Blob.parse("rgb(30, 185, 170)", "2% 68%", "4px 8px"),
		Blob.parse("rgb(255, 120, 40)", "72% -3%", "59px 9px"),
		Blob.parse("rgb(100, 70, 255)", "74% 100%", "42px 7px"),
		Blob.parse("rgb(240, 50, 180)", "100% 27%", "10px 17px"),
		Blob.parse("rgb(180, 40, 240)", "100% 27%", "10px 18px"),
		Blob.parse("rgb(40, 140, 255)", "100% 27%", "5px 10px"),
		Blob.parse("rgb(255, 50, 100)", "100% 27%", "11px 12px"),
	],
	ColorVariant.MONO: [
		Blob.parse("rgb(160, 160, 160)", "2% 68%", "9px 18px"),
		Blob.parse("rgb(140, 140, 140)", "2% 68%", "4px 8px"),
		Blob.parse("rgb(180, 180, 180)", "72% -3%", "59px 9px"),
		Blob.parse("rgb(150, 150, 150)", "74% 100%", "42px 7px"),
		Blob.parse("rgb(170, 170, 170)", "100% 27%", "10px 17px"),
		Blob.parse("rgb(155, 155, 155)", "100% 27%", "10px 18px"),
		Blob.parse("rgb(145, 145, 145)", "100% 27%", "5px 10px"),
		Blob.parse("rgb(165, 165, 165)", "100% 27%", "11px 12px"),
	],
	ColorVariant.OCEAN: [
		Blob.parse("rgb(60, 140, 200)", "2% 68%", "9px 18px"),
		Blob.parse("rgb(50, 120, 180)", "2% 68%", "4px 8px"),
		Blob.parse("rgb(100, 80, 220)", "72% -3%", "59px 9px"),
		Blob.parse("rgb(80, 100, 255)", "74% 100%", "42px 7px"),
		Blob.parse("rgb(120, 70, 240)", "100% 27%", "10px 17px"),
		Blob.parse("rgb(90, 80, 220)", "100% 27%", "10px 18px"),
		Blob.parse("rgb(70, 110, 255)", "100% 27%", "5px 10px"),
		Blob.parse("rgb(110, 90, 230)", "100% 27%", "11px 12px"),
	],
	ColorVariant.SUNSET: [
		Blob.parse("rgb(255, 180, 50)", "2% 68%", "9px 18px"),
		Blob.parse("rgb(255, 150, 40)", "2% 68%", "4px 8px"),
		Blob.parse("rgb(255, 80, 60)", "72% -3%", "59px 9px"),
		Blob.parse("rgb(255, 100, 80)", "74% 100%", "42px 7px"),
		Blob.parse("rgb(255, 60, 80)", "100% 27%", "10px 17px"),
		Blob.parse("rgb(255, 120, 60)", "100% 27%", "10px 18px"),
		Blob.parse("rgb(255, 200, 50)", "100% 27%", "5px 10px"),
		Blob.parse("rgb(255, 90, 70)", "100% 27%", "11px 12px"),
	],
}

SMALL_INNER: dict[ColorVariant, list[Blob]] = {
	variant: [
		Blob.parse(
			f"rgba({b.color.red()}, {b.color.green()}, {b.color.blue()}, {alpha})",
			pos,
			size,
		)
		for b, pos, size, alpha in zip(
			SMALL_BORDER[variant],
			["2% 68%", "2% 68%", "72% -3%", "74% 100%", "100% 27%", "100% 27%", "100% 27%", "100% 27%"],
			["9px 18px", "4px 8px", "59px 9px", "42px 7px", "10px 17px", "10px 18px", "5px 10px", "11px 12px"],
			[0.5, 0.45, 0.35, 0.35, 0.3, 0.4, 0.3, 0.3],
		)
	]
	for variant in ColorVariant
}


# ------------------------------------------------------------------- line

@dataclass(frozen=True)
class LineBlob:
	"""Line-variant blob: pixel sizes with px offsets from the bottom edge."""

	color: QColor
	w: float
	h: float
	ox: float  # px offset from beam position
	oy: float  # px offset upward from bottom

	@classmethod
	def parse(cls, color: str, w: float, h: float, ox: float, oy: float) -> LineBlob:
		m = _RGB_RE.match(color)
		r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
		return cls(QColor(r, g, b), w, h, ox, oy)


# (color, sizeW, sizeH, offsetX, offsetY) — dark and light per variant.
LINE_PALETTES: dict[ColorVariant, dict[str, list[LineBlob]]] = {}
_LINE_TABLES: dict[ColorVariant, tuple[tuple, ...]] = {
	ColorVariant.COLORFUL: (
		(("rgb(255, 50, 100)", 36, 36, 0, 2), ("rgb(40, 180, 220)", 30, 32, 39, 0), ("rgb(50, 200, 80)", 33, 28, -36, 2),
		 ("rgb(180, 40, 240)", 29, 34, -54, 0), ("rgb(255, 160, 30)", 27, 30, 51, -1), ("rgb(100, 70, 255)", 36, 24, 21, 1),
		 ("rgb(40, 140, 255)", 30, 22, -21, 0), ("rgb(240, 50, 180)", 25, 28, 66, 1), ("rgb(30, 185, 170)", 23, 30, -66, -1)),
		(("rgb(255, 50, 100)", 45, 36, 0, 2), ("rgb(40, 140, 255)", 35, 32, 65, 0), ("rgb(50, 200, 80)", 40, 28, -60, 2),
		 ("rgb(180, 40, 240)", 35, 34, -90, 0), ("rgb(30, 185, 170)", 38, 30, 85, -1), ("rgb(100, 70, 255)", 50, 24, 35, 1),
		 ("rgb(40, 140, 255)", 40, 22, -35, 0), ("rgb(255, 120, 40)", 35, 28, 110, 1), ("rgb(240, 50, 180)", 30, 30, -110, -1)),
	),
	ColorVariant.MONO: (
		(("rgb(200, 200, 200)", 36, 36, 0, 2), ("rgb(170, 170, 170)", 30, 32, 39, 0), ("rgb(155, 155, 155)", 33, 28, -36, 2),
		 ("rgb(185, 185, 185)", 29, 34, -54, 0), ("rgb(165, 165, 165)", 27, 30, 51, -1), ("rgb(180, 180, 180)", 36, 24, 21, 1),
		 ("rgb(160, 160, 160)", 30, 22, -21, 0), ("rgb(175, 175, 175)", 25, 28, 66, 1), ("rgb(190, 190, 190)", 23, 30, -66, -1)),
		(("rgb(100, 100, 100)", 45, 36, 0, 2), ("rgb(80, 80, 80)", 35, 32, 65, 0), ("rgb(90, 90, 90)", 40, 28, -60, 2),
		 ("rgb(70, 70, 70)", 35, 34, -90, 0), ("rgb(85, 85, 85)", 38, 30, 85, -1), ("rgb(95, 95, 95)", 50, 24, 35, 1),
		 ("rgb(75, 75, 75)", 40, 22, -35, 0), ("rgb(105, 105, 105)", 35, 28, 110, 1), ("rgb(65, 65, 65)", 30, 30, -110, -1)),
	),
	ColorVariant.OCEAN: (
		(("rgb(100, 80, 220)", 36, 36, 0, 2), ("rgb(60, 120, 255)", 30, 32, 39, 0), ("rgb(80, 100, 200)", 33, 28, -36, 2),
		 ("rgb(130, 70, 255)", 29, 34, -54, 0), ("rgb(70, 130, 255)", 27, 30, 51, -1), ("rgb(120, 80, 255)", 36, 24, 21, 1),
		 ("rgb(90, 110, 230)", 30, 22, -21, 0), ("rgb(110, 90, 240)", 25, 28, 66, 1), ("rgb(140, 100, 255)", 23, 30, -66, -1)),
		(("rgb(80, 60, 200)", 45, 36, 0, 2), ("rgb(50, 100, 220)", 35, 32, 65, 0), ("rgb(70, 90, 190)", 40, 28, -60, 2),
		 ("rgb(110, 60, 220)", 35, 34, -90, 0), ("rgb(60, 110, 230)", 38, 30, 85, -1), ("rgb(100, 70, 240)", 50, 24, 35, 1),
		 ("rgb(80, 100, 210)", 40, 22, -35, 0), ("rgb(90, 80, 225)", 35, 28, 110, 1), ("rgb(120, 90, 245)", 30, 30, -110, -1)),
	),
	ColorVariant.SUNSET: (
		(("rgb(255, 100, 60)", 36, 36, 0, 2), ("rgb(255, 180, 50)", 30, 32, 39, 0), ("rgb(255, 140, 70)", 33, 28, -36, 2),
		 ("rgb(255, 80, 80)", 29, 34, -54, 0), ("rgb(255, 200, 60)", 27, 30, 51, -1), ("rgb(255, 120, 50)", 36, 24, 21, 1),
		 ("rgb(255, 160, 80)", 30, 22, -21, 0), ("rgb(255, 90, 60)", 25, 28, 66, 1), ("rgb(255, 70, 70)", 23, 30, -66, -1)),
		(("rgb(220, 80, 40)", 45, 36, 0, 2), ("rgb(230, 150, 30)", 35, 32, 65, 0), ("rgb(210, 110, 50)", 40, 28, -60, 2),
		 ("rgb(200, 60, 60)", 35, 34, -90, 0), ("rgb(220, 170, 40)", 38, 30, 85, -1), ("rgb(210, 100, 30)", 50, 24, 35, 1),
		 ("rgb(230, 130, 60)", 40, 22, -35, 0), ("rgb(190, 70, 50)", 35, 28, 110, 1), ("rgb(180, 50, 50)", 30, 30, -110, -1)),
	),
}
for _variant, (_dark, _light) in _LINE_TABLES.items():
	LINE_PALETTES[_variant] = {
		"dark": [LineBlob.parse(*row) for row in _dark],
		"light": [LineBlob.parse(*row) for row in _light],
	}

# Inner line blobs: fixed rgba + slightly smaller sizes.
LINE_INNER: dict[ColorVariant, list[LineBlob]] = {}
_LINE_INNER_TABLES: dict[ColorVariant, tuple] = {
	ColorVariant.COLORFUL: (
		("rgba(255, 50, 100, 0.48)", 33, 30, 0, 0), ("rgba(40, 180, 220, 0.42)", 24, 26, 39, -3),
		("rgba(50, 200, 80, 0.48)", 27, 24, -36, 0), ("rgba(180, 40, 240, 0.42)", 23, 28, -54, -2),
		("rgba(255, 160, 30, 0.50)", 24, 24, 51, -1), ("rgba(100, 70, 255, 0.45)", 30, 20, 21, 0),
		("rgba(40, 140, 255, 0.40)", 25, 18, -21, -2), ("rgba(240, 50, 180, 0.45)", 21, 24, 66, 0),
		("rgba(30, 185, 170, 0.52)", 18, 26, -66, -1),
	),
	ColorVariant.MONO: (
		("rgba(200, 200, 200, 0.48)", 33, 30, 0, 0), ("rgba(170, 170, 170, 0.42)", 24, 26, 39, -3),
		("rgba(155, 155, 155, 0.48)", 27, 24, -36, 0), ("rgba(185, 185, 185, 0.42)", 23, 28, -54, -2),
		("rgba(165, 165, 165, 0.50)", 24, 24, 51, -1), ("rgba(180, 180, 180, 0.45)", 30, 20, 21, 0),
		("rgba(160, 160, 160, 0.40)", 25, 18, -21, -2), ("rgba(175, 175, 175, 0.45)", 21, 24, 66, 0),
		("rgba(190, 190, 190, 0.52)", 18, 26, -66, -1),
	),
	ColorVariant.OCEAN: (
		("rgba(100, 80, 220, 0.48)", 33, 30, 0, 0), ("rgba(60, 120, 255, 0.42)", 24, 26, 39, -3),
		("rgba(80, 100, 200, 0.48)", 27, 24, -36, 0), ("rgba(130, 70, 255, 0.42)", 23, 28, -54, -2),
		("rgba(70, 130, 255, 0.50)", 24, 24, 51, -1), ("rgba(120, 80, 255, 0.45)", 30, 20, 21, 0),
		("rgba(90, 110, 230, 0.40)", 25, 18, -21, -2), ("rgba(110, 90, 240, 0.45)", 21, 24, 66, 0),
		("rgba(140, 100, 255, 0.52)", 18, 26, -66, -1),
	),
	ColorVariant.SUNSET: (
		("rgba(255, 100, 60, 0.48)", 33, 30, 0, 0), ("rgba(255, 180, 50, 0.42)", 24, 26, 39, -3),
		("rgba(255, 140, 70, 0.48)", 27, 24, -36, 0), ("rgba(255, 80, 80, 0.42)", 23, 28, -54, -2),
		("rgba(255, 200, 60, 0.50)", 24, 24, 51, -1), ("rgba(255, 120, 50, 0.45)", 30, 20, 21, 0),
		("rgba(255, 160, 80, 0.40)", 25, 18, -21, -2), ("rgba(255, 90, 60, 0.45)", 21, 24, 66, 0),
		("rgba(255, 70, 70, 0.52)", 18, 26, -66, -1),
	),
}
for _variant, _rows in _LINE_INNER_TABLES.items():
	LINE_INNER[_variant] = [LineBlob.parse(*row) for row in _rows]

# Bloom spikes for the line variant: 5 (color1, color2) pairs per theme.
LINE_SPIKES: dict[ColorVariant, dict[str, tuple[QColor, ...]]] = {}
_LINE_SPIKE_TABLES: dict[ColorVariant, tuple] = {
	ColorVariant.COLORFUL: (
		("rgb(100, 70, 255)", "rgba(100, 70, 255, 1)", "rgba(255, 170, 40, 0.59)", "rgba(255, 170, 40, 0.29)",
		 "rgb(50, 200, 100)", "rgba(50, 200, 100, 1)", "rgba(200, 50, 240, 0.91)", "rgba(200, 50, 240, 0.45)",
		 "rgb(40, 140, 255)", "rgba(40, 140, 255, 1)"),
		("rgb(80, 50, 200)", "rgba(80, 50, 200, 0.8)", "rgba(210, 130, 0, 0.7)", "rgba(210, 130, 0, 0.46)",
		 "rgb(30, 160, 70)", "rgba(30, 160, 70, 0.82)", "rgb(160, 30, 190)", "rgba(160, 30, 190, 0.7)",
		 "rgb(30, 100, 200)", "rgba(30, 100, 200, 0.78)"),
	),
	ColorVariant.MONO: (
		("rgb(200, 200, 200)", "rgba(200, 200, 200, 1)", "rgba(180, 180, 180, 0.59)", "rgba(180, 180, 180, 0.29)",
		 "rgb(190, 190, 190)", "rgba(190, 190, 190, 1)", "rgba(170, 170, 170, 0.91)", "rgba(170, 170, 170, 0.45)",
		 "rgb(185, 185, 185)", "rgba(185, 185, 185, 1)"),
		("rgb(80, 80, 80)", "rgba(80, 80, 80, 0.8)", "rgba(100, 100, 100, 0.7)", "rgba(100, 100, 100, 0.46)",
		 "rgb(70, 70, 70)", "rgba(70, 70, 70, 0.82)", "rgb(90, 90, 90)", "rgba(90, 90, 90, 0.7)",
		 "rgb(85, 85, 85)", "rgba(85, 85, 85, 0.78)"),
	),
	ColorVariant.OCEAN: (
		("rgb(100, 80, 255)", "rgb(100, 80, 255)", "rgba(80, 130, 220, 0.59)", "rgba(80, 130, 220, 0.29)",
		 "rgb(60, 100, 255)", "rgb(60, 100, 255)", "rgba(90, 120, 200, 0.91)", "rgba(90, 120, 200, 0.45)",
		 "rgb(120, 90, 255)", "rgb(120, 90, 255)"),
		("rgb(50, 40, 180)", "rgba(50, 40, 180, 0.8)", "rgba(40, 80, 200, 0.7)", "rgba(40, 80, 200, 0.46)",
		 "rgb(30, 50, 190)", "rgba(30, 50, 190, 0.82)", "rgb(60, 90, 180)", "rgba(60, 90, 180, 0.7)",
		 "rgb(70, 60, 200)", "rgba(70, 60, 200, 0.78)"),
	),
	ColorVariant.SUNSET: (
		("rgb(255, 100, 80)", "rgb(255, 100, 80)", "rgba(255, 150, 80, 0.59)", "rgba(255, 150, 80, 0.29)",
		 "rgb(255, 80, 60)", "rgb(255, 80, 60)", "rgba(255, 120, 50, 0.91)", "rgba(255, 120, 50, 0.45)",
		 "rgb(255, 140, 70)", "rgb(255, 140, 70)"),
		("rgb(200, 60, 30)", "rgba(200, 60, 30, 0.8)", "rgba(220, 100, 20, 0.7)", "rgba(220, 100, 20, 0.46)",
		 "rgb(180, 40, 20)", "rgba(180, 40, 20, 0.82)", "rgb(210, 80, 10)", "rgba(210, 80, 10, 0.7)",
		 "rgb(190, 70, 30)", "rgba(190, 70, 30, 0.78)"),
	),
}

def _parse_qcolor(spec: str) -> QColor:
	m = _RGB_RE.match(spec)
	r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
	a = float(m.group(4)) if m.group(4) else 1.0
	return QColor(r, g, b, round(a * 255))


# Primary/secondary bloom glow colors per variant/theme (upstream `spike`/`spikeLt`).
SPIKE_COLORS: dict[ColorVariant, dict[str, tuple[QColor, QColor]]] = {}
_SPIKE_COLOR_TABLES: dict[ColorVariant, tuple] = {
	ColorVariant.COLORFUL: (("rgb(255, 60, 80)", "rgba(40, 190, 180, 0.98)"), ("rgb(200, 30, 60)", "rgb(20, 150, 140)")),
	ColorVariant.MONO: (("rgb(200, 200, 200)", "rgb(170, 170, 170)"), ("rgb(80, 80, 80)", "rgb(120, 120, 120)")),
	ColorVariant.OCEAN: (("rgb(100, 120, 255)", "rgba(130, 100, 220, 0.98)"), ("rgb(60, 60, 180)", "rgb(80, 100, 200)")),
	ColorVariant.SUNSET: (("rgb(255, 140, 80)", "rgba(255, 100, 60, 0.98)"), ("rgb(200, 80, 40)", "rgb(220, 120, 30)")),
}
for _variant, (_dark, _light) in _SPIKE_COLOR_TABLES.items():
	SPIKE_COLORS[_variant] = {
		"dark": (_parse_qcolor(_dark[0]), _parse_qcolor(_dark[1])),
		"light": (_parse_qcolor(_light[0]), _parse_qcolor(_light[1])),
	}


for _variant, (_dark, _light) in _LINE_SPIKE_TABLES.items():
	LINE_SPIKES[_variant] = {
		"dark": tuple(_parse_qcolor(c) for c in _dark),
		"light": tuple(_parse_qcolor(c) for c in _light),
	}


# ------------------------------------------------------------------ pulse

@dataclass(frozen=True)
class PulseDef:
	"""Pulse blob: index into the palette + region/quadrant + explicit size."""

	ci: int
	region: int  # 1..3 — size oscillator group
	quad: str  # tl/tr/bl/br — opacity oscillator
	w: float
	h: float
	x: float | None = None  # explicit position override (fraction)
	y: float | None = None

	@classmethod
	def parse(cls, ci: int, region: int, quad: str, w: float, h: float, x: str = "", y: str = "") -> PulseDef:
		return cls(ci, region, quad, w, h, float(x.rstrip("%")) / 100 if x else None, float(y.rstrip("%")) / 100 if y else None)


# Which region/quadrant each of the 9 ring blobs belongs to (v5 Card 4 ordering).
PULSE_RING_MAP: list[tuple[int, str]] = [
	(1, "tl"), (2, "tl"), (3, "bl"), (1, "bl"), (2, "br"),
	(3, "br"), (1, "tr"), (2, "tr"), (3, "tr"),
]

# pulse-inner inner-perimeter sizes (::before), slightly smaller than the ring.
PULSE_INNER_SIZES: list[tuple[float, float]] = [
	(65, 35), (55, 30), (35, 65), (15, 30), (173, 28), (80, 22), (69, 28), (22, 38), (47, 44),
]

# pulse-inner bloom — 7 blobs with expanded sizes (positions from palette).
PULSE_INNER_BLOOM: list[PulseDef] = [
	PulseDef.parse(0, 1, "tl", 84, 48), PulseDef.parse(1, 2, "tl", 72, 42), PulseDef.parse(2, 3, "bl", 48, 84),
	PulseDef.parse(4, 2, "br", 216, 38), PulseDef.parse(5, 3, "br", 102, 31), PulseDef.parse(6, 1, "tr", 89, 38),
	PulseDef.parse(8, 3, "tr", 62, 58),
]

# pulse-outside stroke/core blobs — edge-positioned.
PULSE_OUTER_CORE: list[PulseDef] = [
	PulseDef.parse(0, 1, "tl", 80, 19, "27%", "0%"), PulseDef.parse(6, 2, "tr", 74, 11, "73%", "-1%"),
	PulseDef.parse(7, 3, "tr", 15, 44, "100%", "33%"), PulseDef.parse(8, 1, "br", 19, 38, "101%", "72%"),
	PulseDef.parse(4, 2, "br", 84, 13, "67%", "100%"), PulseDef.parse(1, 3, "bl", 60, 21, "24%", "101%"),
	PulseDef.parse(2, 1, "bl", 17, 40, "0%", "60%"), PulseDef.parse(3, 2, "tl", 13, 32, "-1%", "28%"),
]

# pulse-outside bloom — wider halo (7 blobs).
PULSE_OUTER_BLOOM: list[PulseDef] = [
	PulseDef.parse(0, 1, "tl", 110, 30, "27%", "3%"), PulseDef.parse(6, 2, "tr", 100, 20, "73%", "1%"),
	PulseDef.parse(7, 3, "tr", 26, 62, "100%", "33%"), PulseDef.parse(8, 1, "br", 30, 56, "101%", "72%"),
	PulseDef.parse(4, 2, "br", 120, 22, "67%", "99%"), PulseDef.parse(1, 3, "bl", 88, 32, "24%", "99%"),
	PulseDef.parse(2, 1, "bl", 28, 58, "0%", "60%"),
]


# ------------------------------------------------------------- color math

def hue_shift(color: QColor, degrees: float) -> QColor:
	"""Approximate CSS `filter: hue-rotate(deg)` via HSV hue rotation."""
	if degrees == 0.0:
		return color
	h, s, v, a = color.getHsvF()
	if s == 0.0:
		return color  # gray/white stays gray
	return QColor.fromHsvF((h + degrees / 360.0) % 1.0, s, v, a)


def apply_filters(color: QColor, brightness: float, saturation: float) -> QColor:
	h, s, v, a = color.getHsvF()
	s = min(1.0, max(0.0, s * saturation))
	v = min(1.0, max(0.0, v * brightness))
	return QColor.fromHsvF(h, s, v, a)


def ping_pong(phase: float) -> float:
	"""CSS ease-in-out ping-pong factor in [0,1] (cosine curve)."""
	return (1.0 - math.cos(2.0 * math.pi * phase)) / 2.0


def line_hue_shift(seconds: float, hue_range: float) -> float:
	"""Rotate/line hue drift: ±hue_range over a 12s ease-in-out cycle."""
	return -hue_range + 2.0 * hue_range * ping_pong(seconds / 12.0)


def theme_dark(theme: Theme) -> bool:
	return theme is Theme.DARK
