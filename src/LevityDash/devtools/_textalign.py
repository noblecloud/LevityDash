"""Qt half of the text alignment harness: measure real text items, and draw what was measured.

A label fits its text into a *limit rect* (its box less margins) and places it by `alignment`. Both steps run
through relative geometry, margins, size groups and layouts, which is where text drifts. This module measures
the outcome instead of reading the numbers the code computed:

* `ink` is found by painting the real `Text` item (`Text.paint`, 4x supersampled) into an image and taking the
  bounds of the pixels it drew; `pathInk` is the same bound from the glyph outlines, as a cross-check;
* `limit` is the box the text was told to stay in, mapped to the scene the way `Text.updateTransform` uses it;
* the font metrics (baseline, ascent, descent, strikeout) come from the item's own font and scale.

`_textalign_rules.py` says where those should be. `overlay()` draws everything for a human. Nothing here edits
an item. Not imported by the shipped app.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter, QPen
from PySide6.QtWidgets import QStyleOptionGraphicsItem

from LevityDash.devtools._textalign_rules import Probe, Rect

SUPERSAMPLE = 4
ALPHA_THRESHOLD = 96


def slug(text: str) -> str:
	return re.sub(r'[^A-Za-z0-9._-]+', '-', text).strip('-').lower()


def asTuple(rect: QRectF) -> Rect:
	return (round(rect.x(), 3), round(rect.y(), 3), round(rect.width(), 3), round(rect.height(), 3))


def asRect(rect: Rect) -> QRectF:
	return QRectF(*rect)


def role(text) -> str:
	"""`value`, `unit`, `title` or `label`, from the class of the label that owns the text."""
	name = type(text.parentItem()).__name__.lower()
	for word in ('value', 'unit', 'title'):
		if word in name:
			return word
	return 'label'


def limitRect(text) -> QRectF:
	"""The scene rect `Text.updateTransform` lets the text use: the owner's margin rect, narrowed by `text-height`."""
	rect = text.limitRect  # in the item's own space at identity scale: margin rect less its position
	if (height := text.height_px) is not None:
		centre = rect.center()
		rect.setHeight(height)
		rect.moveCenter(centre)
	return text.parentItem().mapRectToScene(rect.translated(text.pos()))


def rasterInk(text, region: QRectF) -> QRectF:
	"""Bounds, in scene pixels, of what `text.paint` draws inside `region`. Empty if nothing was drawn."""
	scale = SUPERSAMPLE
	image = QImage(max(1, int(region.width() * scale)), max(1, int(region.height() * scale)), QImage.Format.Format_ARGB32_Premultiplied)
	image.fill(0)
	painter = QPainter(image)
	painter.setRenderHint(QPainter.RenderHint.Antialiasing)
	painter.scale(scale, scale)
	painter.translate(-region.topLeft())
	painter.setTransform(text.sceneTransform(), True)
	option = QStyleOptionGraphicsItem()
	option.rect = text.boundingRect().toRect()
	text.paint(painter, option, None)
	painter.end()
	left = top = 10 ** 9
	right = bottom = -1
	for y in range(image.height()):
		for x in range(image.width()):
			if (image.pixel(x, y) >> 24) & 0xFF >= ALPHA_THRESHOLD:
				left, right = min(left, x), max(right, x)
				top, bottom = min(top, y), max(bottom, y)
	if right < 0:
		return QRectF()
	return QRectF(region.left() + left / scale, region.top() + top / scale, (right - left + 1) / scale, (bottom - top + 1) / scale)


def _flag(flag) -> str:
	return getattr(flag, 'name', str(flag)).split('.')[-1]


def _fontPixels(font: QFont) -> float:
	if font.pixelSize() > 0:
		return float(font.pixelSize())
	return font.pointSizeF() * 96 / 72 if font.pointSizeF() > 0 else 0.0


def measure(text, case: str = '', pad: float = 20.0) -> Probe:
	"""Measure one `Text` item as it is now."""
	label = text.parentItem()
	box = label.mapRectToScene(label.rect())
	limit = limitRect(text)
	hint = text.mapRectToScene(text.currentTextRect())
	region = limit.united(box).united(hint).adjusted(-pad, -pad, pad, pad)
	ink = rasterInk(text, region)
	scale = text.transform().m11() or 1.0
	metrics = QFontMetricsF(text.font())
	baseline = text.mapToScene(QPointF(0, text._text_pos.y())).y()
	align = text.alignment
	group = text.size_group
	return Probe(
		case=case,
		role=role(text),
		text=text.text or '',
		horizontal=_flag(align.horizontal),
		vertical=_flag(align.vertical),
		box=asTuple(box),
		limit=asTuple(limit),
		hint=asTuple(hint),
		ink=asTuple(ink),
		pathInk=asTuple(text.scenePath().boundingRect()),
		scale=round(scale, 5),
		fontPixels=round(_fontPixels(text.font()) * scale, 3),
		baseline=round(baseline, 3),
		ascent=round(baseline - metrics.ascent() * scale, 3),
		descent=round(baseline + metrics.descent() * scale, 3),
		strikeout=round(baseline - metrics.strikeOutPos() * scale, 3),
		group=None if group is None else str(getattr(group, 'key', group)),
	)


LAYERS = {
	'box': QColor('#4aa3ff'),
	'limit': QColor('#2fd06b'),
	'hint': QColor('#ffb020'),
	'ink': QColor('#ff3b3b'),
	'baseline': QColor('#ff4de1'),
	'metrics': QColor('#a0a0a0'),
}


def overlay(probes: Iterable[Probe], texts, path: Path, title: str = '', zoom: float = 3.0, pad: float = 14.0) -> Path:
	"""Draw the real glyphs on a grey ground with the box (blue), limit rect (green), fit rect (amber), ink (red),
	baseline (pink) and ascent, descent and strikeout lines (grey). One PNG for all of `probes`."""
	probes = list(probes)
	region = QRectF()
	for probe in probes:
		for rect in (probe.box, probe.limit, probe.hint, probe.ink):
			region = region.united(asRect(rect))
	region = region.adjusted(-pad, -(pad + (14 if title else 0)), pad, pad)
	image = QImage(max(1, int(region.width() * zoom)), max(1, int(region.height() * zoom)), QImage.Format.Format_ARGB32_Premultiplied)
	image.fill(QColor('#2a2d33'))
	painter = QPainter(image)
	painter.setRenderHint(QPainter.RenderHint.Antialiasing)
	painter.scale(zoom, zoom)
	painter.translate(-region.topLeft())
	for text in texts:
		painter.save()
		painter.setTransform(text.sceneTransform(), True)
		option = QStyleOptionGraphicsItem()
		option.rect = text.boundingRect().toRect()
		text.paint(painter, option, None)
		painter.restore()

	def rect(r: Rect, layer: str, dash: bool = False):
		pen = QPen(LAYERS[layer], 1.5 / zoom)
		if dash:
			pen.setStyle(Qt.PenStyle.DashLine)
		painter.setPen(pen)
		painter.setBrush(Qt.BrushStyle.NoBrush)
		painter.drawRect(asRect(r))

	def hline(y: float, x0: float, x1: float, layer: str, dash: bool = True):
		pen = QPen(LAYERS[layer], 1.0 / zoom)
		if dash:
			pen.setStyle(Qt.PenStyle.DotLine)
		painter.setPen(pen)
		painter.drawLine(QLineF(x0, y, x1, y))

	for probe in probes:
		rect(probe.box, 'box')
		rect(probe.limit, 'limit')
		rect(probe.hint, 'hint', dash=True)
		rect(probe.ink, 'ink')
		x0, x1 = probe.limit[0] - 6, probe.limit[0] + probe.limit[2] + 6
		for y in (probe.ascent, probe.descent, probe.strikeout):
			hline(y, x0, x1, 'metrics')
		hline(probe.baseline, x0, x1, 'baseline', dash=False)
	painter.resetTransform()
	painter.setPen(QColor('#e8e8e8'))
	font = QFont('Roboto Mono')
	font.setPixelSize(11)
	painter.setFont(font)
	if title:
		painter.drawText(6, 14, title)
	painter.end()
	path.parent.mkdir(parents=True, exist_ok=True)
	image.save(str(path))
	return path
