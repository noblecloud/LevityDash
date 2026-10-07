"""The painting engine — a port of the upstream `styles.ts` layer structure.

Every preset composites the same primitives the CSS does: fixed color blobs
(radial-gradient ellipses), soft masks (conic wedge / travel ellipse / frame
band / ring), blurred blooms, and white highlights. The per-preset painters
below mirror the CSS paint order exactly: pulse-outside paints bloom + core
behind the source widget, everything else paints over it (inner glow, stroke
ring, bloom). All functions are pure painting helpers driven by a `QPainter`;
per-frame animation state comes from the caller (BorderBeamEffect).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
	QColor,
	QConicalGradient,
	QImage,
	QLinearGradient,
	QPainter,
	QPainterPath,
	QPainterPathStroker,
	QPen,
	QRadialGradient,
)

from .ring import ring_color
from .palettes import (
	BORDER_PALETTES,
	LINE_INNER,
	LINE_PALETTES,
	LINE_SPIKES,
	PULSE_INNER_BLOOM,
	PULSE_INNER_SIZES,
	PULSE_OUTER_BLOOM,
	PULSE_OUTER_CORE,
	PULSE_RING_MAP,
	SMALL_BORDER,
	SMALL_INNER,
	SPIKE_COLORS,
	Blob,
	PulseDef,
	apply_filters,
	inner_blobs,
	ping_pong,
)
from .palettes import (
	hue_shift as hue_shift_color,
)
from .types import ColorSpace, ColorVariant, Size

# Per-size theme presets — verbatim from upstream `sizeThemePresets`.
THEME_PRESETS: dict[Size, dict[str, dict]] = {
	Size.SMALL: {
		"dark": {"stroke_opacity": 0.46, "inner_opacity": 0.24, "bloom_opacity": 0.38, "inner_shadow": QColor(255, 255, 255, 76), "saturation": 1.2},
		"light": {"stroke_opacity": 0.12, "inner_opacity": 0.3, "bloom_opacity": 0.16, "inner_shadow": QColor(0, 0, 0, 36), "saturation": 1.8},
	},
	Size.MEDIUM: {
		"dark": {"stroke_opacity": 0.26, "inner_opacity": 0.42, "bloom_opacity": 0.24, "inner_shadow": QColor(255, 255, 255, 69), "saturation": 1.2},
		"light": {"stroke_opacity": 0.12, "inner_opacity": 0.26, "bloom_opacity": 0.34, "inner_shadow": QColor(0, 0, 0, 36), "saturation": 1.5},
	},
	Size.LINE: {
		"dark": {"stroke_opacity": 1.14, "inner_opacity": 0.7, "bloom_opacity": 0.8, "inner_shadow": QColor(255, 255, 255, 26), "saturation": 1.2},
		"light": {"stroke_opacity": 0.16, "inner_opacity": 0.32, "bloom_opacity": 0.3, "inner_shadow": QColor(0, 0, 0, 36), "saturation": 1.95},
	},
	Size.PULSE_OUTSIDE: {
		"dark": {"stroke_opacity": 0.94, "inner_opacity": 0.34, "bloom_opacity": 0.3, "inner_shadow": QColor(0, 0, 0, 0), "saturation": 1.2, "brightness": 1.9},
		"light": {"stroke_opacity": 1.96, "inner_opacity": 1.04, "bloom_opacity": 0.42, "inner_shadow": QColor(0, 0, 0, 0), "saturation": 0.6, "brightness": 1.7},
	},
	Size.PULSE_INNER: {
		"dark": {"stroke_opacity": 1.54, "inner_opacity": 0.44, "bloom_opacity": 0.66, "inner_shadow": QColor(0, 0, 0, 0), "saturation": 1.2, "brightness": 0.75},
		"light": {"stroke_opacity": 0.32, "inner_opacity": 0.4, "bloom_opacity": 0.8, "inner_shadow": QColor(0, 0, 0, 0), "saturation": 0.75, "brightness": 1.3},
	},
}

_MONO_MULTIPLIER = 0.5

# Inner glow frame band width (px), per the CSS 28px linear-gradient masks.
FRAME_BAND = 28

# Pulse-outside halo: bloom is inset -30px with a blur of 15-22.5px.
PULSE_HALO = 75

# Cached masks
_ring_cache: dict[tuple[int, int, float, float], QImage] = {}
_path_cache: dict[tuple, QImage] = {}
_conic_cache: dict[tuple[int, int, int, str], QImage] = {}
_frame_fade_cache: dict[tuple[int, int], QImage] = {}
_conic_frame_cache: dict[tuple[int, int, int, str], QImage] = {}
_ring_defs_cache: dict[ColorVariant, list[PulseDef]] = {}
_inner_defs_cache: dict[ColorVariant, list[PulseDef]] = {}


# ------------------------------------------------------------------ context

@dataclass(frozen=True)
class PaintCtx:
	"""Everything a per-preset painter needs for one frame (logical coords)."""

	size: Size
	rect: QRectF  # content rect, origin (0, 0) in the effect's space
	radius: float
	dark: bool
	variant: ColorVariant
	fade: float  # beam opacity (animated 0..1) x strength
	brightness: float
	saturation: float
	hue_deg: float  # hue-rotate degrees (0 when colors are static)
	progress: float  # rotate phase 0..1 (md/sm/line)
	duration: float = 2.3  # seconds; pulse params scale with it
	values: dict[str, float] | None = None  # pulse oscillator values
	hue_bloom: float = 0.0  # line bloom uses its own 8s hue cycle
	sx: float = 1.0  # pulse-outside glow scale x (measured vs 350px ref)
	sy: float = 1.0  # pulse-outside glow scale y (measured vs 140px ref)
	color_space: ColorSpace = ColorSpace.HSV  # Oklch re-derives blobs from the sphere palette
	path: QPainterPath | None = None  # a custom outline in `rect` coordinates; None follows the rounded rect
	path_key: tuple | None = None  # identifies `path` for the mask cache


# ------------------------------------------------------------------ paths

def rounded_rect_path(rect: QRectF, radius: float) -> QPainterPath:
	path = QPainterPath()
	path.addRoundedRect(rect, radius, radius)
	return path


def ring_path(rect: QRectF, radius: float, border_width: float) -> QPainterPath:
	"""The ring = outer rounded rect minus inner rounded rect (OddEven)."""
	path = QPainterPath()
	path.addRoundedRect(rect, radius, radius)
	inner = QPainterPath()
	inner.addRoundedRect(rect.adjusted(border_width, border_width, -border_width, -border_width), max(0.0, radius - border_width), max(0.0, radius - border_width))
	path.addPath(inner)
	path.setFillRule(Qt.FillRule.OddEvenFill)
	return path


def make_layer(w: int, h: int) -> QImage:
	img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
	img.fill(Qt.GlobalColor.transparent)
	return img


# ------------------------------------------------------------------- blobs

def paint_blob(
	painter: QPainter,
	cx: float,
	cy: float,
	rx: float,
	ry: float,
	color: QColor,
	stops: list[tuple[float, QColor]] | None = None,
) -> None:
	"""Elliptical radial gradient from `color` (or custom stops) to transparent."""
	if rx <= 0 or ry <= 0 or color.alpha() == 0:
		return
	gradient = QRadialGradient(QPointF(0.0, 0.0), 1.0)
	if stops is None:
		gradient.setColorAt(0.0, color)
		transparent = QColor(color)
		transparent.setAlpha(0)
		gradient.setColorAt(1.0, transparent)
	else:
		for pos, c in stops:
			gradient.setColorAt(pos, c)
	painter.save()
	painter.translate(cx, cy)
	painter.scale(rx, ry)
	painter.setPen(Qt.PenStyle.NoPen)
	painter.setBrush(gradient)
	painter.drawRect(QRectF(-1.0, -1.0, 2.0, 2.0))
	painter.restore()


def paint_blobs(
	painter: QPainter,
	rect: QRectF,
	blobs: list[Blob],
	hue_deg: float,
	brightness: float,
	saturation: float,
	color_space: ColorSpace = ColorSpace.HSV,
) -> None:
	"""Paint blobs at percentage positions/sizes, tinted by hue/filters.

	In OKLCH mode each blob's color is re-derived from the sphere ring palette
	(index % 3 ring hue); the base palette feeds geometry + alpha only.
	"""
	for i, b in enumerate(blobs):
		if color_space is ColorSpace.OKLCH:
			color = ring_color(i, hue_deg, saturation, brightness)
			color.setAlpha(b.color.alpha())
		else:
			color = apply_filters(hue_shift_color(b.color, hue_deg), brightness, saturation)
		paint_blob(painter, rect.x() + b.x * rect.width(), rect.y() + b.y * rect.height(), b.w, b.h, color)


def paint_pulse_blobs(
	painter: QPainter,
	rect: QRectF,
	defs: list[PulseDef],
	palette: list[Blob],
	values: dict[str, float],
	hue_deg: float,
	brightness: float,
	saturation: float,
	sx: float = 1.0,
	sy: float = 1.0,
	frozen_alpha: float | None = None,
	scale: tuple[float, float] | None = None,
	color_space: ColorSpace = ColorSpace.HSV,
	snap: "PathSnap | None" = None,
) -> None:
	"""Live pulse blobs: per-quadrant alpha, per-region size/drift oscillators,
	optional glow scale (pulse-outside) and element scale transform.

	With `snap`, each blob moves from where it sits on the rectangle's edge to the point of the
	custom path in the same direction from the centre, so a halo on a circle or a heart lies on
	the outline and not at the corners of its bounding box.

	In OKLCH mode colors are re-derived from the sphere ring palette via
	``def.ci`` (palette index); base palette supplies geometry + alpha.
	"""
	sxs, sys = scale if scale is not None else (1.0, 1.0)
	cx, cy = rect.center().x(), rect.center().y()
	for d in defs:
		if frozen_alpha is not None:
			alpha = frozen_alpha
			wf = hf = 1.0
			ox = oy = 0.0
		else:
			alpha = values[f"bop-{d.quad}"]
			wf = values[f"bw{d.region}"]
			hf = values[f"bh{d.region}"] * values["bgh"]
			ox = values[f"bx{d.region}"]
			oy = values[f"by{d.region}"]
		base_color = palette[d.ci].color
		base_alpha = base_color.alpha()
		if color_space is ColorSpace.OKLCH:
			c = ring_color(d.ci, hue_deg, saturation, brightness)
			c.setAlpha(base_alpha)
			c.setAlphaF(c.alphaF() * alpha)
		else:
			c = QColor(base_color)
			c.setAlphaF(c.alphaF() * alpha)
			c = apply_filters(hue_shift_color(c, hue_deg), brightness, saturation)
		px = (d.x if d.x is not None else palette[d.ci].x) * rect.width() + ox
		py = (d.y if d.y is not None else palette[d.ci].y) * rect.height() + oy
		px = cx + (px - cx) * sxs
		py = cy + (py - cy) * sys
		x, y = rect.x() + px, rect.y() + py
		if snap is not None:
			x, y = snap.move(x, y)
		paint_blob(painter, x, y, d.w * wf * sx * sxs, d.h * hf * sy * sys, c)


_SNAP_SAMPLES = 360
_snap_cache: dict[tuple, list[tuple[float, float, float, float]]] = {}


class PathSnap:
	"""Moves a point near the panel's edge onto the custom path, along the same direction from the centre.

	Directions are measured in the panel's own proportions (a corner of the rectangle is the
	diagonal of the path's box whatever the aspect), and where a direction meets the path twice
	the outer point wins. `origin` is where the panel's top-left lies in the layer being painted.
	"""

	def __init__(self, path: QPainterPath, key: tuple | None, width: float, height: float, origin: QPointF):
		self.width, self.height, self.origin = max(width, 1.0), max(height, 1.0), origin
		cache_key = (key, int(self.width), int(self.height))
		samples = _snap_cache.get(cache_key) if key is not None else None
		if samples is None:
			samples = []
			for i in range(_SNAP_SAMPLES):
				point = path.pointAtPercent(i / _SNAP_SAMPLES)
				nx, ny = (point.x() - self.width / 2) / self.width, (point.y() - self.height / 2) / self.height
				samples.append((point.x(), point.y(), math.atan2(ny, nx), math.hypot(nx, ny)))
			if key is not None:
				if len(_snap_cache) > 64:
					_snap_cache.clear()
				_snap_cache[cache_key] = samples
		self.samples = samples

	def move(self, x: float, y: float) -> tuple[float, float]:
		ix, iy = x - self.origin.x(), y - self.origin.y()
		target = math.atan2((iy - self.height / 2) / self.height, (ix - self.width / 2) / self.width)
		best = min(
			self.samples,
			key=lambda s: (round(abs((s[2] - target + math.pi) % math.tau - math.pi), 3), -s[3]),
		)
		return best[0] + self.origin.x(), best[1] + self.origin.y()


def _snap(ctx: PaintCtx, origin: QPointF) -> PathSnap | None:
	if ctx.path is None:
		return None
	return PathSnap(ctx.path, ctx.path_key, ctx.rect.width(), ctx.rect.height(), origin)


def pulse_ring_defs(variant: ColorVariant) -> list[PulseDef]:
	"""Ring gradients: palette positions/sizes + region/quadrant from the map."""
	defs = _ring_defs_cache.get(variant)
	if defs is None:
		defs = [
			PulseDef(i, r, q, b.w, b.h, b.x, b.y)
			for i, (b, (r, q)) in enumerate(zip(BORDER_PALETTES[variant], PULSE_RING_MAP))
		]
		_ring_defs_cache[variant] = defs
	return defs


def pulse_inner_defs(variant: ColorVariant) -> list[PulseDef]:
	"""Inner-perimeter gradients: smaller PULSE_INNER_SIZES, palette positions."""
	defs = _inner_defs_cache.get(variant)
	if defs is None:
		palette = BORDER_PALETTES[variant]
		defs = []
		for i, (b, (r, q), (w, h)) in enumerate(zip(palette, PULSE_RING_MAP, PULSE_INNER_SIZES)):
			defs.append(PulseDef(i, r, q, w, h))
		_inner_defs_cache[variant] = defs
	return defs


# ------------------------------------------------------------------- masks

def ring_mask(w: int, h: int, radius: float, border_width: float) -> QImage:
	key = (w, h, radius, border_width)
	img = _ring_cache.get(key)
	if img is None:
		img = QImage(w, h, QImage.Format.Format_Alpha8)
		img.fill(Qt.GlobalColor.transparent)
		painter = QPainter(img)
		painter.setRenderHint(QPainter.RenderHint.Antialiasing)
		painter.fillPath(ring_path(QRectF(0, 0, w, h), radius, border_width), QColor(255, 255, 255))
		painter.end()
		_ring_cache[key] = img
	return img


# Travel conic stops: md/sm stroke and md inner (from upstream `travelMask`).
_RING_CONIC_STOPS = (
	(0.0, 0.0), (0.30, 0.0), (0.36, 0.10), (0.44, 0.35),
	(0.52, 1.0), (0.80, 1.0), (0.86, 0.35), (0.92, 0.10),
	(0.95, 0.0), (1.0, 0.0),
)
# sm inner uses a wider travel window (upstream `smallMask`).
_SM_INNER_CONIC_STOPS = (
	(0.0, 0.0), (0.22, 0.0), (0.28, 0.12), (0.36, 0.40),
	(0.46, 1.0), (0.82, 1.0), (0.88, 0.40), (0.94, 0.12),
	(0.97, 0.0), (1.0, 0.0),
)


def conic_wedge_mask(w: int, h: int, css_angle_deg: float, stops=_RING_CONIC_STOPS) -> QImage:
	"""Traveling window: white 52-80% of the circle, soft ramps. Qt conic angle 0 = 12 o'clock
	counter-clockwise; CSS `from` angles are clockwise, so mirror them."""
	key = (w, h, int(css_angle_deg), "wide" if stops is _SM_INNER_CONIC_STOPS else "ring")
	img = _conic_cache.get(key)
	if img is None:
		img = QImage(w, h, QImage.Format.Format_Alpha8)
		img.fill(Qt.GlobalColor.transparent)
		gradient = QConicalGradient(QPointF(w / 2, h / 2), -css_angle_deg)
		for pos, alpha in stops:
			gradient.setColorAt(pos, QColor(255, 255, 255, int(alpha * 255)))
		painter = QPainter(img)
		painter.fillRect(0, 0, w, h, gradient)
		painter.end()
		_conic_cache[key] = img
	return img


def travel_mask(w: int, h: int, x_frac: float, w_scale: float, h_scale: float, mask_w: float = 78, mask_h: float = 60) -> QImage:
	"""Line-variant travel window: soft ellipse anchored at the bottom edge."""
	img = QImage(w, h, QImage.Format.Format_Alpha8)
	img.fill(Qt.GlobalColor.transparent)
	cx = x_frac * w
	cy = h
	rx = mask_w * w_scale
	ry = mask_h * h_scale
	painter = QPainter(img)
	painter.save()
	painter.translate(cx, cy)
	painter.scale(rx, ry)
	gradient = QRadialGradient(QPointF(0.0, 0.0), 1.0)
	gradient.setColorAt(0.0, QColor(255, 255, 255))
	gradient.setColorAt(0.45, QColor(255, 255, 255, 127))
	gradient.setColorAt(1.0, QColor(255, 255, 255, 0))
	painter.setPen(Qt.PenStyle.NoPen)
	painter.setBrush(gradient)
	painter.drawRect(QRectF(-1.0, -1.0, 2.0, 2.0))
	painter.restore()
	painter.end()
	return img


def _fade_stops(g: QLinearGradient, length: float, band: float = FRAME_BAND) -> None:
	"""Full white at the edges, fading linearly to transparent `band` px in
	(the CSS `linear-gradient(white, transparent 28px, ..., white)` pair)."""
	mid1 = min(1.0, band / length)
	mid2 = max(0.0, 1.0 - band / length)
	g.setColorAt(0.0, QColor(255, 255, 255))
	g.setColorAt(mid1, QColor(255, 255, 255, 0))
	g.setColorAt(mid2, QColor(255, 255, 255, 0))
	g.setColorAt(1.0, QColor(255, 255, 255))


def _v_gradient(w: int, h: int) -> QLinearGradient:
	g = QLinearGradient(0.0, 0.0, 0.0, float(h))
	_fade_stops(g, float(h))
	return g


def _h_gradient(w: int, h: int) -> QLinearGradient:
	g = QLinearGradient(0.0, 0.0, float(w), 0.0)
	_fade_stops(g, float(w))
	return g


def frame_fade_mask(w: int, h: int) -> QImage:
	"""`v ∪ h`: the CSS 28px linear-gradient pair (mask-composite: add) —
	soft band fading out `FRAME_BAND` px from each edge."""
	key = (w, h)
	img = _frame_fade_cache.get(key)
	if img is None:
		img = QImage(w, h, QImage.Format.Format_Alpha8)
		img.fill(Qt.GlobalColor.transparent)
		painter = QPainter(img)
		painter.fillRect(0, 0, w, h, _v_gradient(w, h))
		painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
		painter.fillRect(0, 0, w, h, _h_gradient(w, h))
		painter.end()
		_frame_fade_cache[key] = img
	return img


def conic_frame_fade_mask(w: int, h: int, css_angle_deg: float, stops=_RING_CONIC_STOPS) -> QImage:
	"""`(conic ∩ v) ∪ h`: md inner glow mask (mask-composite: intersect, add) —
	the travel window gates only the top/bottom strips; left/right always lit."""
	key = (w, h, int(css_angle_deg), "wide" if stops is _SM_INNER_CONIC_STOPS else "ring")
	img = _conic_frame_cache.get(key)
	if img is None:
		img = QImage(w, h, QImage.Format.Format_Alpha8)
		img.fill(Qt.GlobalColor.transparent)
		painter = QPainter(img)
		painter.fillRect(0, 0, w, h, _v_gradient(w, h))
		gradient = QConicalGradient(QPointF(w / 2, h / 2), -css_angle_deg)
		for pos, alpha in stops:
			gradient.setColorAt(pos, QColor(255, 255, 255, int(alpha * 255)))
		painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
		painter.fillRect(0, 0, w, h, gradient)
		painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
		painter.fillRect(0, 0, w, h, _h_gradient(w, h))
		painter.end()
		_conic_frame_cache[key] = img
	return img


def travel_frame_fade_mask(w: int, h: int, x_frac: float, w_scale: float, h_scale: float, mask_w: float = 78, mask_h: float = 60) -> QImage:
	"""`(travel ∩ v) ∪ h`: line inner glow mask (radial window + frame fades)."""
	img = QImage(w, h, QImage.Format.Format_Alpha8)
	img.fill(Qt.GlobalColor.transparent)
	painter = QPainter(img)
	painter.fillRect(0, 0, w, h, _v_gradient(w, h))
	painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
	painter.drawImage(0, 0, travel_mask(w, h, x_frac, w_scale, h_scale, mask_w, mask_h))
	painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
	painter.fillRect(0, 0, w, h, _h_gradient(w, h))
	painter.end()
	return img


def apply_mask(img: QImage, mask: QImage) -> QImage:
	"""Multiply the image's alpha by the mask (DestinationIn on a scratch copy)."""
	out = QImage(img)
	painter = QPainter(out)
	painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
	painter.drawImage(0, 0, mask)
	painter.end()
	return out


def blur_image(img: QImage, radius: float) -> QImage:
	"""Cheap gaussian-ish blur: smooth downscale + upscale, twice for a soft kernel."""
	if radius <= 0:
		return img
	scale = max(0.125, min(0.5, 4.0 / radius))
	out = img
	for _ in range(2):
		small = out.scaled(max(1, int(img.width() * scale)), max(1, int(img.height() * scale)), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
		out = small.scaled(img.width(), img.height(), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
	return out


# ------------------------------------------------------- custom outlines

def outline(ctx: PaintCtx) -> QPainterPath:
	"""What the beam follows: the custom path, or the panel's rounded rect."""
	return ctx.path if ctx.path is not None else rounded_rect_path(ctx.rect, ctx.radius)


def _stroke_mask(ctx: PaintCtx, w: int, h: int, width: float, blur: float = 0.0) -> QImage:
	"""A band of `width` px centred on the custom path, as an alpha mask."""
	key = ('stroke', ctx.path_key, w, h, width, blur)
	img = _path_cache.get(key)
	if img is None:
		img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
		img.fill(Qt.GlobalColor.transparent)
		stroker = QPainterPathStroker()
		stroker.setWidth(width)
		stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
		stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
		painter = QPainter(img)
		painter.setRenderHint(QPainter.RenderHint.Antialiasing)
		painter.fillPath(stroker.createStroke(ctx.path), QColor(255, 255, 255))
		painter.end()
		img = blur_image(img, blur) if blur > 0 else img
		if len(_path_cache) > 64:
			_path_cache.clear()
		_path_cache[key] = img
	return img


def band_mask(ctx: PaintCtx, w: int, h: int, band: float = 1.0) -> QImage:
	"""The thin band along the edge that the stroke and bloom layers show through."""
	if ctx.path is None:
		return ring_mask(w, h, ctx.radius, band)
	return _stroke_mask(ctx, w, h, max(1.0, band) * 2.0)


def _stop_alpha(stops: tuple, pos: float) -> float:
	for (p0, a0), (p1, a1) in zip(stops, stops[1:]):
		if p0 <= pos <= p1:
			return a0 if p1 == p0 else a0 + (a1 - a0) * (pos - p0) / (p1 - p0)
	return 0.0


def path_travel_mask(ctx: PaintCtx, w: int, h: int, progress: float, stops: tuple, reach: float) -> QImage:
	"""A window that runs along the custom path by arc length.

	`stops` is the conic profile of the rectangle version: its alpha at position p
	becomes the alpha at that share of the way round the path. The window carries
	`reach` px either side of the path, so it lights the band and the glow inside it.
	"""
	path = ctx.path
	img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
	img.fill(Qt.GlobalColor.transparent)
	length = path.length()
	if length < 1.0:
		return img
	count = max(48, min(600, int(length / 3.0)))
	painter = QPainter(img)
	painter.setRenderHint(QPainter.RenderHint.Antialiasing)
	painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Lighten)
	painter.setPen(Qt.PenStyle.NoPen)
	for i in range(count):
		t = i / count
		alpha = _stop_alpha(stops, (t - progress) % 1.0)
		if alpha < 0.01:
			continue
		p = path.pointAtPercent(t)
		gradient = QRadialGradient(p, reach)
		gradient.setColorAt(0.0, QColor(255, 255, 255, int(alpha * 255)))
		gradient.setColorAt(1.0, QColor(255, 255, 255, 0))
		painter.setBrush(gradient)
		painter.drawEllipse(p, reach, reach)
	painter.end()
	return img


def window_mask(ctx: PaintCtx, w: int, h: int, progress: float, stops: tuple, reach: float = 40.0, *, frame: bool = False) -> QImage:
	"""The travelling window: the conic wedge on a rectangle, an arc-length window on a custom path.

	With `frame` the window gates the inner glow, which on a path is the band of
	`FRAME_BAND` px inside the edge instead of the rectangle's top and bottom strips.
	"""
	if ctx.path is None:
		if frame:
			return conic_frame_fade_mask(w, h, progress * 360.0, stops=stops)
		return conic_wedge_mask(w, h, progress * 360.0, stops=stops)
	window = path_travel_mask(ctx, w, h, progress, stops, reach)
	if frame:
		window = apply_mask(window, _stroke_mask(ctx, w, h, FRAME_BAND * 1.6, 6.0))
	return window


def fill_window(painter: QPainter, ctx: PaintCtx, color: QColor, progress: float, stops: tuple, ring: bool = False) -> None:
	"""Fill the layer with `color` through the travelling window (the conic gradient fill on a rectangle)."""
	rect = ctx.rect
	if ctx.path is None:
		painter.fillRect(rect, _conic_fill_gradient(rect, progress * 360.0, stops, ctx.dark))
		return
	w, h = int(rect.width()), int(rect.height())
	layer = make_layer(w, h)
	lp = QPainter(layer)
	lp.fillRect(0, 0, w, h, color)
	lp.end()
	painter.drawImage(0, 0, apply_mask(layer, path_travel_mask(ctx, w, h, progress, stops, 6.0 if ring else 14.0)))


def line_window(ctx: PaintCtx, w: int, h: int, x: float, w_scale: float, h_scale: float, mask_w: float, mask_h: float) -> QImage:
	"""The `line` style's window: a soft spot at `x` along the bottom edge, or at that share of a custom path."""
	if ctx.path is None:
		return travel_mask(w, h, x, w_scale, h_scale, mask_w, mask_h)
	half = 0.08 * w_scale * (mask_w / 78.0)
	stops = ((0.0, 0.0), (0.5 - half, 0.0), (0.5, 1.0), (0.5 + half, 0.0), (1.0, 0.0))
	return path_travel_mask(ctx, w, h, x - 0.5 + 1.0, stops, max(14.0, mask_h * h_scale * 0.5))


def _path_point(ctx: PaintCtx, t: float) -> tuple[float, float]:
	p = ctx.path.pointAtPercent(t % 1.0)
	return p.x(), p.y()


def frame_band(ctx: PaintCtx, w: int, h: int) -> QImage:
	"""The soft band inside the edge that the inner glow shows through."""
	if ctx.path is None:
		return frame_fade_mask(w, h)
	return _stroke_mask(ctx, w, h, FRAME_BAND * 1.6, 6.0)


def line_frame_window(ctx: PaintCtx, w: int, h: int, x: float, w_scale: float, h_scale: float) -> QImage:
	if ctx.path is None:
		return travel_frame_fade_mask(w, h, x, w_scale, h_scale)
	return apply_mask(line_window(ctx, w, h, x, w_scale, h_scale, 78, 60), frame_band(ctx, w, h))


def _halo_mask(ctx: PaintCtx, qp: QPainter, origin: QPointF, width: float) -> None:
	"""Keep a halo layer only near the custom path (the rectangle's halo needs no cut)."""
	if ctx.path is None:
		return
	device = qp.device()
	mask = QImage(device.width(), device.height(), QImage.Format.Format_ARGB32_Premultiplied)
	mask.fill(Qt.GlobalColor.transparent)
	stroker = QPainterPathStroker()
	stroker.setWidth(width)
	mp = QPainter(mask)
	mp.setRenderHint(QPainter.RenderHint.Antialiasing)
	mp.translate(origin)
	mp.fillPath(stroker.createStroke(ctx.path), QColor(255, 255, 255))
	mp.end()
	qp.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
	qp.drawImage(0, 0, mask)
	qp.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)


# ------------------------------------------------------------ rotate (md/sm)

# White traveling hotspot on the stroke ring (dark = white, light = black).
_WHITE_CONIC_STOPS = (
	(0.0, 0.0), (0.54, 0.0), (0.57, 0.10), (0.60, 0.30), (0.63, 0.60), (0.66, 0.75),
	(0.69, 0.60), (0.72, 0.30), (0.75, 0.10), (0.78, 0.0), (1.0, 0.0),
)

# Bloom conic (md/sm): static white flash in the ring band, rotated with the beam.
_BLOOM_CONIC_STOPS_DARK = (
	(0.0, 0.0), (0.58, 0.0), (0.62, 0.03), (0.65, 0.08), (0.67, 0.20), (0.69, 0.45),
	(0.70, 0.85), (0.705, 0.85), (0.715, 0.45), (0.73, 0.20), (0.75, 0.08), (0.78, 0.03),
	(0.82, 0.0), (1.0, 0.0),
)
_BLOOM_CONIC_STOPS_LIGHT = (
	(0.0, 0.0), (0.58, 0.0), (0.62, 0.02), (0.65, 0.08), (0.67, 0.20), (0.69, 0.40),
	(0.70, 0.60), (0.705, 0.60), (0.715, 0.40), (0.73, 0.20), (0.75, 0.08), (0.78, 0.02),
	(0.82, 0.0), (1.0, 0.0),
)


def _conic_fill_gradient(rect: QRectF, css_angle_deg: float, stops: tuple, dark: bool) -> QConicalGradient:
	base = 255 if dark else 0
	gradient = QConicalGradient(rect.center(), -css_angle_deg)
	for pos, alpha in stops:
		gradient.setColorAt(pos, QColor(base, base, base, int(alpha * 255)))
	return gradient


def _inner_shadow_layer(w: int, h: int, rect: QRectF, radius: float, color: QColor, blur_px: float, spread: float = 1.0, path: QPainterPath | None = None) -> QImage:
	"""Blurred inset ring glow (CSS `box-shadow: inset 0 0 Npx 1px`)."""
	img = make_layer(w, h)
	painter = QPainter(img)
	painter.setRenderHint(QPainter.RenderHint.Antialiasing)
	pen = QPen(color, max(1.0, spread))
	painter.setPen(pen)
	painter.setBrush(Qt.BrushStyle.NoBrush)
	painter.drawPath(path if path is not None else rounded_rect_path(rect, radius - spread))
	painter.end()
	return blur_image(img, blur_px)


def paint_ring_front(painter: QPainter, ctx: PaintCtx) -> None:
	"""md/sm: inner glow (::before, z1), stroke ring (::after, z2), bloom (z3)."""
	small = ctx.size is Size.SMALL
	rect, radius, dark = ctx.rect, ctx.radius, ctx.dark
	preset = THEME_PRESETS[ctx.size]["dark" if dark else "light"]
	mono = _MONO_MULTIPLIER if ctx.variant.is_mono else 1.0
	w, h = int(rect.width()), int(rect.height())
	angle = ctx.progress * 360.0
	hue, b, s = ctx.hue_deg, ctx.brightness, ctx.saturation

	# ::before — inner glow blobs + inset shadow, masked by travel window.
	inner = make_layer(w, h)
	ip = QPainter(inner)
	ip.setRenderHint(QPainter.RenderHint.Antialiasing)
	ip.setClipPath(outline(ctx))
	paint_blobs(ip, rect, SMALL_INNER[ctx.variant] if small else inner_blobs(ctx.variant), hue, b, s, ctx.color_space)
	shadow = preset["inner_shadow"]
	if shadow.alpha() > 0:
		ip.drawImage(0, 0, _inner_shadow_layer(w, h, rect, radius, shadow, 5 if small else 9, path=ctx.path))
	ip.end()
	if small:
		m = window_mask(ctx, w, h, ctx.progress, _SM_INNER_CONIC_STOPS)
	else:
		m = window_mask(ctx, w, h, ctx.progress, _RING_CONIC_STOPS, frame=True)
	inner = apply_mask(inner, m)
	painter.setOpacity(ctx.fade * preset["inner_opacity"] * mono)
	painter.drawImage(0, 0, inner)
	painter.setOpacity(1.0)

	# ::after — white hotspot + color blobs in the 1px ring band, travel-masked.
	stroke = make_layer(w, h)
	sp = QPainter(stroke)
	sp.setRenderHint(QPainter.RenderHint.Antialiasing)
	sp.setClipPath(outline(ctx))
	fill_window(sp, ctx, QColor(255, 255, 255) if dark else QColor(0, 0, 0), ctx.progress, _WHITE_CONIC_STOPS, ring=True)
	paint_blobs(sp, rect, SMALL_BORDER[ctx.variant] if small else BORDER_PALETTES[ctx.variant], hue, b, s, ctx.color_space)
	sp.end()
	band = band_mask(ctx, w, h)
	stroke = apply_mask(stroke, apply_mask(window_mask(ctx, w, h, ctx.progress, _RING_CONIC_STOPS, 10.0), band))
	painter.setOpacity(ctx.fade * preset["stroke_opacity"] * mono)
	painter.drawImage(0, 0, stroke)
	painter.setOpacity(1.0)

	# bloom — blurred static white flash in the ring band.
	bloom = make_layer(w, h)
	bp = QPainter(bloom)
	bp.setRenderHint(QPainter.RenderHint.Antialiasing)
	bp.setClipPath(outline(ctx))
	fill_window(bp, ctx, QColor(255, 255, 255) if dark else QColor(0, 0, 0), ctx.progress, _BLOOM_CONIC_STOPS_DARK if dark else _BLOOM_CONIC_STOPS_LIGHT, ring=True)
	bp.end()
	bloom = apply_mask(bloom, band_mask(ctx, w, h))
	bloom = blur_image(bloom, 8.0)
	painter.setOpacity(ctx.fade * preset["bloom_opacity"] * mono)
	painter.drawImage(0, 0, bloom)
	painter.setOpacity(1.0)


# ------------------------------------------------------------------- line

# Spike geometry per theme: (thinW1..4, thinH1..4) — mono is widened and shortened.
_LINE_THIN_DARK = (0.8, 2.0, 1.2, 0.6), (92, 72, 85, 60)
_LINE_THIN_MONO = (12.0, 14.0, 12.0, 10.0), (42, 38, 40, 32)


def _line_bloom_layer(w: int, h: int, rect: QRectF, ctx: PaintCtx) -> QImage:
	"""The bloom: 5 spikes + glow dot + ambient (9 radial layers)."""
	dark = ctx.dark
	mono = ctx.variant.is_mono
	okl = ctx.color_space is ColorSpace.OKLCH
	primary, secondary, spikes = _line_spike_colors(ctx.variant, dark)
	vals = ctx.values
	x, bottom = (vals["x"] * rect.width(), rect.height()) if ctx.path is None else _path_point(ctx, vals["x"])
	spike, spike2, hv, wv = vals["spike"], vals["spike2"], vals["h"], vals["w"]
	hue, b, s = ctx.hue_bloom if not okl else ctx.hue_deg, ctx.brightness, ctx.saturation
	thin_w, thin_h = _LINE_THIN_MONO if mono else _LINE_THIN_DARK

	if dark:
		primary_mid = primary if not mono else attenuate(primary, 0.09)
		secondary_mid = with_alpha(secondary, 0.49) if not mono else with_alpha(secondary, 0.06)
		light = False
	else:
		primary_lt = primary if not mono else attenuate(primary, 0.11)
		secondary_lt = secondary if not mono else attenuate(secondary, 0.09)
		primary, primary_mid = primary_lt, primary_lt
		secondary, secondary_mid = secondary_lt, secondary_lt
		light = True

	img = make_layer(w, h)
	painter = QPainter(img)
	painter.setRenderHint(QPainter.RenderHint.Antialiasing)
	painter.setClipPath(outline(ctx))

	if okl:
		primary = ring_color(0, hue, s, b)
		primary_mid = primary
		secondary = ring_color(1, hue, s, b)
		secondary_mid = secondary
		spikes = [(ring_color(2, hue, s, b), ring_color(0, hue, s, b)) for _ in spikes]

	def blob(cx, cy, rx, ry, c1, mid, mid_pos, end_pos) -> None:
		if okl:
			c1 = QColor(c1)
			mid = QColor(mid)
		else:
			c1 = apply_filters(hue_shift_color(c1, hue), b, s)
			mid = apply_filters(hue_shift_color(mid, hue), b, s)
		stops = [(0.0, c1), (mid_pos, mid), (end_pos, QColor(c1.red(), c1.green(), c1.blue(), 0))]
		paint_blob(painter, cx, cy, rx, ry, c1, stops=stops)

	# Spikes (thin vertical slivers) — positions 8/22/36/50/64/78/92%.
	# (frac, y_offset, base_w, w_factor, base_h, c1, c2, mid_pos, end_pos)
	spike_specs = (
		(0.08, 2, thin_w[0], spike, thin_h[0], primary, primary_mid, 0.30, 0.88),
		(0.22, 4, 10.0, spike2, 35.0, secondary, secondary_mid, 0.50, 0.95),
		(0.36, 3, thin_w[1], 2 - spike, thin_h[1], spikes[0][0], spikes[0][1], 0.40, 0.90),
		(0.50, 2, 14.0, spike2, 28.0, spikes[1][0], spikes[1][1], 0.55, 0.96),
		(0.64, 4, thin_w[2], 2 - spike2, thin_h[2], spikes[2][0], spikes[2][1], 0.35, 0.89),
		(0.78, 2, 7.0, spike, 45.0, spikes[3][0], spikes[3][1], 0.48, 0.94),
		(0.92, 3, thin_w[3], (1.0 if light else 2.0) - spike, thin_h[3], spikes[4][0], spikes[4][1], 0.42, 0.91),
	)
	for frac, y_off, base_w, w_fac, base_h, c1, mid, mid_pos, end_pos in spike_specs:
		if w_fac > 0:
			blob(
				rect.x() + frac * rect.width(),
				rect.y() + bottom - y_off,
				base_w * w_fac,
				base_h * hv,
				c1, mid, mid_pos, end_pos,
			)

	# Glow dot at the beam position (white), plus ambient or shadow.
	dot = QColor(255, 255, 255, int((0.5 if mono else 1.0) * 255))
	dot20 = QColor(255, 255, 255, int((0.45 if mono else 0.9) * 255))
	dot50 = QColor(255, 255, 255, int((0.25 if mono else 0.5) * 255))
	paint_blob(
		painter,
		rect.x() + x, rect.y() + bottom + 1,
		21.0 * spike, 15.0 * spike2,
		dot,
		stops=[(0.0, dot), (0.20, dot20), (0.50, dot50), (1.0, QColor(255, 255, 255, 0))],
	)
	if not light:
		amb = QColor(255, 255, 255, int((0.15 if mono else 0.3) * 255))
		amb25 = QColor(255, 255, 255, int((0.06 if mono else 0.12) * 255))
		amb55 = QColor(255, 255, 255, int((0.015 if mono else 0.03) * 255))
		paint_blob(
			painter,
			rect.x() + x, rect.y() + bottom,
			42.0 * wv, 40.0 * hv,
			amb,
			stops=[(0.0, amb), (0.25, amb25), (0.55, amb55), (0.80, QColor(255, 255, 255, 0))],
		)
	else:
		sh = QColor(0, 0, 0, 128)
		sh30 = QColor(0, 0, 0, 46)
		sh60 = QColor(0, 0, 0, 8)
		paint_blob(
			painter,
			rect.x() + x, rect.y() + bottom,
			50.0 * wv, 32.0 * hv,
			sh,
			stops=[(0.0, sh), (0.30, sh30), (0.60, sh60), (0.85, QColor(0, 0, 0, 0))],
		)
	painter.end()
	return img


def _line_spike_colors(variant: ColorVariant, dark: bool) -> tuple[QColor, QColor, list[tuple[QColor, QColor]]]:
	"""(primary, secondary, 5 spike (c1, c2) pairs) — mono attenuated per upstream."""
	primary, secondary = SPIKE_COLORS[variant]["dark" if dark else "light"]
	colors = LINE_SPIKES[variant]["dark" if dark else "light"]
	is_mono = variant.is_mono
	if is_mono:
		primary, secondary = attenuate(primary, 0.14), attenuate(secondary, 0.12)
	spikes = [(colors[i], colors[i + 1]) for i in range(0, len(colors), 2)]
	if is_mono:
		spikes = [(attenuate(c1, 0.14), attenuate(c2, 0.098)) for c1, c2 in spikes]
	return primary, secondary, spikes


def paint_line_front(painter: QPainter, ctx: PaintCtx) -> None:
	"""line: inner (::before), travel stroke (::after), blurred bloom (z3)."""
	rect, radius, dark = ctx.rect, ctx.radius, ctx.dark
	preset = THEME_PRESETS[Size.LINE]["dark" if dark else "light"]
	w, h = int(rect.width()), int(rect.height())
	vals = ctx.values
	x, wv, hv, edge = vals["x"], vals["w"], vals["h"], vals["edge"]
	cx = x * rect.width()
	px, py = (cx, rect.height()) if ctx.path is None else _path_point(ctx, x)
	hue, b, s = ctx.hue_deg, ctx.brightness, ctx.saturation

	# ::after — white highlight + line blobs in the ring band, travel-masked.
	stroke = make_layer(w, h)
	sp = QPainter(stroke)
	sp.setRenderHint(QPainter.RenderHint.Antialiasing)
	sp.setClipPath(outline(ctx))
	if dark:
		hl = QColor(255, 255, 255, 97)
		hl30 = QColor(255, 255, 255, 31)
		hl_w = 24.0
		hl_stops = [(0.0, hl), (0.30, hl30), (0.65, QColor(255, 255, 255, 0))]
	else:
		hl = QColor(0, 0, 0, 153)
		hl30 = QColor(0, 0, 0, 64)
		hl_w = 35.0
		hl_stops = [(0.0, hl), (0.35, hl30), (0.70, QColor(0, 0, 0, 0))]
	paint_blob(sp, px, py + 2, hl_w * wv, 28.0 * hv, hl, stops=hl_stops)
	for i, lb in enumerate(LINE_PALETTES[ctx.variant]["dark" if dark else "light"]):
		if ctx.color_space is ColorSpace.OKLCH:
			color = ring_color(i, hue, s, b)
		else:
			color = apply_filters(hue_shift_color(lb.color, hue), b, s)
		paint_blob(sp, px + lb.ox, py + lb.oy, lb.w * wv, lb.h * hv, color)
	sp.end()
	m = apply_mask(line_window(ctx, w, h, x, wv, hv, 78, 60), band_mask(ctx, w, h))
	stroke = apply_mask(stroke, m)
	painter.setOpacity(ctx.fade * edge * preset["stroke_opacity"])
	painter.drawImage(0, 0, stroke)
	painter.setOpacity(1.0)

	# ::before — inner blobs + inset shadow, travel + frame-band masked.
	inner = make_layer(w, h)
	ip = QPainter(inner)
	ip.setRenderHint(QPainter.RenderHint.Antialiasing)
	ip.setClipPath(outline(ctx))
	for i, lb in enumerate(LINE_INNER[ctx.variant]):
		color = (
			ring_color(i, hue, s, b)
			if ctx.color_space is ColorSpace.OKLCH
			else apply_filters(hue_shift_color(lb.color, hue), b, s)
		)
		paint_blob(ip, px + lb.ox, py - abs(lb.oy), lb.w * wv, lb.h * hv, color)
	shadow = preset["inner_shadow"]
	if shadow.alpha() > 0:
		ip.drawImage(0, 0, _inner_shadow_layer(w, h, rect, radius, shadow, 9, path=ctx.path))
	ip.end()
	m = line_frame_window(ctx, w, h, x, wv, hv)
	inner = apply_mask(inner, m)
	painter.setOpacity(ctx.fade * edge * preset["inner_opacity"])
	painter.drawImage(0, 0, inner)
	painter.setOpacity(1.0)

	# bloom — spike burst + glow dot, travel-masked, blurred.
	bloom = _line_bloom_layer(w, h, rect, ctx)
	m = line_window(ctx, w, h, x, wv, hv, 84.0, 110.0)
	bloom = apply_mask(bloom, m)
	bloom = blur_image(bloom, 6.0 if ctx.variant.is_mono else 8.0)
	painter.setOpacity(ctx.fade * edge * preset["bloom_opacity"])
	painter.drawImage(0, 0, bloom)
	painter.setOpacity(1.0)


# ------------------------------------------------------------------ pulse

def _frozen_alpha(pm: PulseParams) -> float:
	"""Frozen bloom alpha = 1 - op*0.5 (upstream `pulseTableGradientsStatic`)."""
	return 1.0 - pm.op * 0.5


def paint_pulse_inner_front(painter: QPainter, ctx: PaintCtx) -> None:
	"""pulse-inner: inner perimeter (::before), ring (::after), blurred bloom."""
	rect, radius, dark = ctx.rect, ctx.radius, ctx.dark
	preset = THEME_PRESETS[Size.PULSE_INNER]["dark" if dark else "light"]
	mono = _MONO_MULTIPLIER if ctx.variant.is_mono else 1.0
	w, h = int(rect.width()), int(rect.height())
	values = ctx.values
	palette = BORDER_PALETTES[ctx.variant]
	pm = pulse_params(Size.PULSE_INNER, dark, ctx.duration)
	hue, b, s = ctx.hue_deg, ctx.brightness, ctx.saturation

	# ::after — full perimeter ring in the 1px band, live oscillators.
	stroke = make_layer(w, h)
	sp = QPainter(stroke)
	sp.setRenderHint(QPainter.RenderHint.Antialiasing)
	sp.setClipPath(outline(ctx))
	paint_pulse_blobs(sp, rect, pulse_ring_defs(ctx.variant), palette, values, hue, b, s, color_space=ctx.color_space)
	sp.end()
	stroke = apply_mask(stroke, band_mask(ctx, w, h))
	painter.setOpacity(ctx.fade * preset["stroke_opacity"] * mono)
	painter.drawImage(0, 0, stroke)
	painter.setOpacity(1.0)

	# ::before — smaller inner perimeter + white corner accents, frame-band masked.
	inner = make_layer(w, h)
	ip = QPainter(inner)
	ip.setRenderHint(QPainter.RenderHint.Antialiasing)
	ip.setClipPath(outline(ctx))
	paint_pulse_blobs(ip, rect, pulse_inner_defs(ctx.variant), palette, values, hue, b, s, color_space=ctx.color_space)
	base = 0.18 if dark else 0.08
	corner = 255 if dark else 0
	for fx, fy, quad in ((0.0, 0.0, "tl"), (1.0, 0.0, "tr"), (0.0, 1.0, "bl"), (1.0, 1.0, "br")):
		alpha = base * values[f"bop-{quad}"]
		if alpha > 0.002:
			c = QColor(corner, corner, corner, int(alpha * 255))
			paint_blob(ip, rect.x() + fx * rect.width(), rect.y() + fy * rect.height(), 60.0, 60.0, c)
	ip.end()
	inner = apply_mask(inner, frame_band(ctx, w, h))
	painter.setOpacity(ctx.fade * preset["inner_opacity"] * mono)
	painter.drawImage(0, 0, inner)
	painter.setOpacity(1.0)

	# bloom — frozen-alpha expanded blobs in the ring band, blurred.
	bloom = make_layer(w, h)
	bp = QPainter(bloom)
	bp.setRenderHint(QPainter.RenderHint.Antialiasing)
	bp.setClipPath(outline(ctx))
	paint_pulse_blobs(bp, rect, PULSE_INNER_BLOOM, palette, values, hue, b, s, frozen_alpha=_frozen_alpha(pm), color_space=ctx.color_space)
	bp.end()
	bloom = apply_mask(bloom, band_mask(ctx, w, h))
	bloom = blur_image(bloom, 8.0)
	painter.setOpacity(ctx.fade * preset["bloom_opacity"] * mono)
	painter.drawImage(0, 0, bloom)
	painter.setOpacity(1.0)


def paint_pulse_outside_behind(painter: QPainter, ctx: PaintCtx) -> None:
	"""pulse-outside bloom (inset -30, blurred halo) and core (inset -10) — behind the content."""
	rect, dark = ctx.rect, ctx.dark
	preset = THEME_PRESETS[Size.PULSE_OUTSIDE]["dark" if dark else "light"]
	mono = _MONO_MULTIPLIER if ctx.variant.is_mono else 1.0
	values = ctx.values
	palette = BORDER_PALETTES[ctx.variant]
	pm = pulse_params(Size.PULSE_OUTSIDE, dark, ctx.duration)
	hue, b, s = ctx.hue_deg, ctx.brightness, ctx.saturation

	# bloom — wide blurred halo, scaled 0.95 x 0.9 about its center.
	bloom_rect = rect.adjusted(-30.0, -30.0, 30.0, 30.0)
	bloom_blur = 22.5 if dark else 15.0
	bloom = _paint_padded_blur(
		bloom_rect, bloom_blur,
		lambda bp, r: (paint_pulse_blobs(
			bp, r, PULSE_OUTER_BLOOM, palette, values, hue, b, s,
			sx=ctx.sx, sy=ctx.sy, frozen_alpha=_frozen_alpha(pm), scale=(0.95, 0.9),
			color_space=ctx.color_space, snap=_snap(ctx, QPointF(r.x() + 30.0, r.y() + 30.0)),
		), _halo_mask(ctx, bp, QPointF(r.x() + 30.0, r.y() + 30.0), 90.0)),
	)
	painter.setOpacity(ctx.fade * preset["bloom_opacity"] * mono)
	painter.drawImage(bloom[0], bloom[1])
	painter.setOpacity(1.0)

	# core — bright blurred edge blobs, same transform.
	core_rect = rect.adjusted(-10.0, -10.0, 10.0, 10.0)
	core = _paint_padded_blur(
		core_rect, 3.0 if dark else 6.0,
		lambda cp, r: (paint_pulse_blobs(cp, r, PULSE_OUTER_CORE, palette, values, hue, b, s, sx=ctx.sx, sy=ctx.sy, scale=(0.95, 0.9), color_space=ctx.color_space, snap=_snap(ctx, QPointF(r.x() + 10.0, r.y() + 10.0))), _halo_mask(ctx, cp, QPointF(r.x() + 10.0, r.y() + 10.0), 30.0)),
	)
	painter.setOpacity(ctx.fade * preset["inner_opacity"] * mono)
	painter.drawImage(core[0], core[1])
	painter.setOpacity(1.0)


def _paint_padded_blur(rect: QRectF, blur: float, paint) -> tuple[QRectF, QImage]:
	"""Paint into a layer larger than `rect` and blur it; returns where to draw the result and the image.

	Blobs reach past `rect` and a blur spreads further, so a layer cut at `rect` shows hard edges
	where the glow runs out of image. Padding by twice the blur lets both fade to nothing.
	"""
	pad = math.ceil(blur * 2.0)
	outer = rect.adjusted(-pad, -pad, pad, pad)
	layer = make_layer(int(outer.width()), int(outer.height()))
	qp = QPainter(layer)
	qp.setRenderHint(QPainter.RenderHint.Antialiasing)
	paint(qp, QRectF(pad, pad, rect.width(), rect.height()))
	qp.end()
	return outer, blur_image(layer, blur)


def paint_pulse_outside_front(painter: QPainter, ctx: PaintCtx) -> None:
	"""pulse-outside stroke ring (::after) — above the content, in the 1px band."""
	rect, radius, dark = ctx.rect, ctx.radius, ctx.dark
	preset = THEME_PRESETS[Size.PULSE_OUTSIDE]["dark" if dark else "light"]
	mono = _MONO_MULTIPLIER if ctx.variant.is_mono else 1.0
	w, h = int(rect.width()), int(rect.height())
	values = ctx.values
	palette = BORDER_PALETTES[ctx.variant]
	hue, b, s = ctx.hue_deg, ctx.brightness, ctx.saturation

	stroke = make_layer(w, h)
	sp = QPainter(stroke)
	sp.setRenderHint(QPainter.RenderHint.Antialiasing)
	sp.setClipPath(outline(ctx))
	paint_pulse_blobs(sp, rect, PULSE_OUTER_CORE, palette, values, hue, b, s, sx=ctx.sx, sy=ctx.sy, color_space=ctx.color_space, snap=_snap(ctx, rect.topLeft()))
	sp.end()
	stroke = apply_mask(stroke, band_mask(ctx, w, h))
	painter.setOpacity(ctx.fade * preset["stroke_opacity"] * mono)
	painter.drawImage(0, 0, stroke)
	painter.setOpacity(1.0)


# ------------------------------------------------------------- line keyframes

LINE_TRAVEL = (
	(0.00, 0.06, 0.5), (0.10, 0.15, 0.8), (0.20, 0.25, 1.1), (0.30, 0.35, 1.3), (0.40, 0.44, 1.45),
	(0.50, 0.50, 1.5), (0.60, 0.56, 1.45), (0.70, 0.65, 1.3), (0.80, 0.75, 1.1), (0.90, 0.85, 0.8),
	(1.00, 0.94, 0.5),
)
LINE_EDGE = ((0.0, 0.0), (0.125, 0.0), (0.325, 1.0), (0.675, 1.0), (0.875, 0.0), (1.0, 0.0))
LINE_BREATHE = ((0.0, 0.8), (0.25, 1.25), (0.55, 0.85), (0.8, 1.3), (1.0, 0.8))
LINE_SPIKE = ((0.0, 0.8), (0.25, 1.3), (0.5, 0.9), (0.75, 1.4), (1.0, 0.8))
LINE_SPIKE2 = ((0.0, 1.2), (0.25, 0.7), (0.5, 1.4), (0.75, 0.8), (1.0, 1.2))


def keyframe(keys: tuple, progress: float) -> float:
	keys = list(keys)
	for i, (pos, val) in enumerate(keys):
		if progress <= pos:
			if i == 0:
				return val
			prev_pos, prev_val = keys[i - 1]
			span = pos - prev_pos
			if span <= 0:
				return val
			return prev_val + (val - prev_val) * (progress - prev_pos) / span
	return keys[-1][1]


def line_values(progress: float) -> dict[str, float]:
	x, w = LINE_TRAVEL[0][1], LINE_TRAVEL[0][2]
	for i, (pos, xv, wv) in enumerate(LINE_TRAVEL):
		if progress <= pos:
			if i == 0:
				x, w = xv, wv
				break
			prev_pos, prev_x, prev_w = LINE_TRAVEL[i - 1]
			frac = (progress - prev_pos) / (pos - prev_pos)
			x = prev_x + (xv - prev_x) * frac
			w = prev_w + (wv - prev_w) * frac
			break
	else:
		x, w = LINE_TRAVEL[-1][1], LINE_TRAVEL[-1][2]
	return {
		"x": x,
		"w": w,
		"h": keyframe(LINE_BREATHE, progress),
		"edge": keyframe(LINE_EDGE, progress),
		"spike": keyframe(LINE_SPIKE, progress),
		"spike2": keyframe(LINE_SPIKE2, progress),
	}


# ------------------------------------------------------------------ pulse math

@dataclass(frozen=True)
class PulseParams:
	sp: float
	dr: float
	op: float
	gh: float
	bs: float
	ss: float
	ghs: float
	hue_period: float


def pulse_params(size: Size, dark: bool, duration: float) -> PulseParams:
	"""Breathing parameters, verbatim from upstream `pulseParams()`."""
	dur_scale = duration / 2.3
	if size is Size.PULSE_INNER:
		return PulseParams(
			sp=0.28, dr=33 if dark else 40, op=0.48 if dark else 0.45, gh=0.34 if dark else 0.22,
			bs=(1.9 if dark else 2.6) * dur_scale, ss=(2.6 if dark else 4.6) * dur_scale,
			ghs=(2.4 if dark else 5.5) * dur_scale, hue_period=16,
		)
	return PulseParams(
		sp=0.28 if dark else 0.36, dr=14 if dark else 19, op=0.46 if dark else 0.0, gh=0.16 if dark else 0.58,
		bs=(2.3 if dark else 3.7) * dur_scale, ss=(6.4 if dark else 4.6) * dur_scale,
		ghs=(2.4 if dark else 3.8) * dur_scale, hue_period=14,
	)


# Oscillator specs: (key, a, b, period, delay, unit) — verbatim from upstream.
def oscillators(p: PulseParams) -> list[tuple[str, float, float, float, float, str]]:
	sp, dr, op, gh, bs, ss, ghs = p.sp, p.dr, p.op, p.gh, p.bs, p.ss, p.ghs
	return [
		("bw1", 1 - sp, 1 + sp * 1.1, ss * 0.9, 0, ""),
		("bh1", 1 + sp * 0.9, 1 - sp * 0.85, ss * 1.26, 0, ""),
		("bx1", -dr, dr * 0.9, bs * 1.6, 0, "px"),
		("by1", dr * 0.55, -dr * 0.7, bs * 1.6, 0, "px"),
		("bw2", 1 + sp, 1 - sp * 0.85, ss * 1.1, 0, ""),
		("bh2", 1 - sp * 0.8, 1 + sp * 1.05, ss * 0.81, 0, ""),
		("bx2", dr * 0.8, -dr * 0.9, bs * 1.88, 0, "px"),
		("by2", -dr, dr * 0.65, bs * 1.88, 0, "px"),
		("bw3", 1 - sp * 0.6, 1 + sp * 1.15, ss * 0.98, 0, ""),
		("bh3", 1 + sp * 0.75, 1 - sp, ss * 1.4, 0, ""),
		("bx3", -dr * 0.6, dr, bs * 1.45, 0, "px"),
		("by3", -dr * 0.85, dr * 0.45, bs * 1.45, 0, "px"),
		("bgh", 1 - gh, 1 + gh, ghs, 0, ""),
		("bop-tl", 1 - op, 1, bs, 0, ""),
		("bop-tr", 1 - op, 1, bs * 1.32, bs * 0.28, ""),
		("bop-bl", 1 - op, 1, bs * 0.84, bs * 0.55, ""),
		("bop-br", 1 - op, 1, bs * 1.58, bs * 0.83, ""),
	]


def pulse_values(p: PulseParams, t: float) -> dict[str, float]:
	"""All live oscillator values at time t (seconds)."""
	values = {}
	for key, a, b, period, delay, _ in oscillators(p):
		phase = (t - delay) / period
		values[key] = a + (b - a) * ping_pong(phase)
	values["hue"] = ((t / p.hue_period) % 1.0) * 360.0
	return values


def region_values(values: dict[str, float], region: int) -> tuple[float, float, float, float]:
	"""(bw, bh, bx, by) for a region — region size scale + pixel drift."""
	return values[f"bw{region}"], values[f"bh{region}"], values[f"bx{region}"], values[f"by{region}"]


# ------------------------------------------------------------------ helpers

def attenuate(color: QColor, factor: float) -> QColor:
	out = QColor(color)
	out.setAlphaF(color.alphaF() * factor)
	return out


def with_alpha(color: QColor, alpha: float) -> QColor:
	out = QColor(color)
	out.setAlphaF(alpha)
	return out
