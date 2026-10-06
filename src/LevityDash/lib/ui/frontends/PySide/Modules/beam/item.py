"""`PanelBeam`: a beam painted around a Panel, built by the `beam:` setting of a `.levity`.

```yaml
- type: group
  beam:
    size: md                 # sm | md | line | pulse-inner | pulse-outside
    variant: colorful        # colorful | mono | ocean | sunset
    theme: dark              # dark | light
    color-space: hsv         # hsv (the upstream look) | oklch (LevityDash's palette ring)
    duration: 1.96           # seconds per cycle; the default depends on the size
    strength: 1.0            # 0 to 1
    radius: 16               # corner radius in px; the default depends on the size
    fill: '#1d1d1d'          # optional card colour under the content (pulse-outside needs one)
    active: false            # true | false | a key or expression: the beam runs while it is true
    sweep: some.key          # a key or expression: one sweep each time the value arrives
    phase: 0.6               # optional: hold the beam at this time in seconds (renders)
```

A panel with no `beam:` has none of this. `active` and `sweep` default to off, so a beam that is
only declared draws nothing. See docs/tasks/emissive-color-and-glow.md, phase 3.

Painting: two items. `PanelBeam` is the front layer, a child of the panel above its content. For
`pulse-outside`, and for a `fill`, a second item sits behind the panel (`ItemStacksBehindParent`),
as upstream paints the halo behind the content. Neither item takes the mouse.

Motion: the shared `PulseDriver` clock. A beam subscribes while it runs, fades in or out, or
sweeps. It unsubscribes when it is idle, and an idle beam is hidden. With no beam animating the
timer is stopped.
"""

from __future__ import annotations

import math
from typing import Any, Optional

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import QGraphicsItem

from LevityDash.lib.log import LevityPluginLog
from LevityDash.lib.stateful import Binding, Stateful, StateProperty
from LevityDash.lib.ui.colors import Color, theme as colour_theme
from LevityDash.lib.valuesource import openValueSource
from . import shapes, styles
from .palettes import line_hue_shift
from .pulse_driver import PulseDriver
from .types import ColorSpace, ColorVariant, Size, Theme

__all__ = ('PanelBeam',)

log = LevityPluginLog.getChild('Beam')

_FADE_IN = 0.6  # seconds, upstream `_FADE_IN_MS`
_FADE_OUT = 0.5

#: Default cycle length per size (seconds), upstream `finalDuration ??`.
DEFAULT_DURATIONS = {
	Size.SMALL: 1.96, Size.MEDIUM: 1.96, Size.LINE: 3.1, Size.PULSE_INNER: 2.3, Size.PULSE_OUTSIDE: 2.3,
}

#: Default corner radius per size (px), upstream `sizePresets`.
DEFAULT_RADII = {
	Size.SMALL: 32.0, Size.MEDIUM: 16.0, Size.LINE: 16.0, Size.PULSE_INNER: 16.0, Size.PULSE_OUTSIDE: 16.0,
}

# pulse-outside glows are authored for a 350x140 card; the painters scale them by the card's share of that.
_PULSE_REF_W = 350.0
_PULSE_REF_H = 140.0
_PULSE_SCALE_MIN, _PULSE_SCALE_MAX = 0.35, 4.0

#: A sweep is one cycle of a rotating beam and two breaths of a pulse.
_SWEEP_CYCLES = {Size.SMALL: 1, Size.MEDIUM: 1, Size.LINE: 1, Size.PULSE_INNER: 2, Size.PULSE_OUTSIDE: 2}


def _truthy(value: Any) -> bool:
	"""A key's value as a condition: a bool, a number, or a measurement. `Missing` and zero are false."""
	value = getattr(value, 'value', value)
	try:
		return bool(value)
	except Exception:
		return False


def _enum(kind, value, default):
	if isinstance(value, kind):
		return value
	try:
		return kind(str(value).lower())
	except ValueError:
		log.warning(f'beam: {value!r} is not one of {[m.value for m in kind]}; using {default.value}')
		return default


class _BehindLayer(QGraphicsItem):
	"""Paints what sits behind the panel's content: the pulse-outside halo, then the card fill."""

	def __init__(self, beam: 'PanelBeam'):
		super().__init__(beam.panel)
		self._beam = beam
		self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemStacksBehindParent, True)
		self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
		self.setVisible(False)

	def shape(self) -> QPainterPath:
		return QPainterPath()

	def boundingRect(self) -> QRectF:
		rect = self._beam.panelRect()
		if self._beam.size is Size.PULSE_OUTSIDE:
			halo = styles.PULSE_HALO
			return rect.adjusted(-halo, -halo, halo, halo)
		return rect

	def paint(self, painter: QPainter, option, widget=None) -> None:
		self._beam.paintBehind(painter)


class PanelBeam(QGraphicsItem, Stateful, tag=...):
	"""The front layer of a beam, and the owner of its settings and its clock."""

	_size: Size = Size.MEDIUM
	_variant: ColorVariant = ColorVariant.COLORFUL
	_theme: Theme = Theme.AUTO
	_colorSpace: ColorSpace = ColorSpace.HSV

	def __init__(self, parent, *args, **kwargs):
		super().__init__()
		self.panel = parent
		self._behind: Optional[_BehindLayer] = None
		self._activeSpec: Any = False
		self._sweepSpec: Optional[str] = None
		self._activeOn = False
		self._activeBinding: Optional[Binding] = None
		self._sweepBinding: Optional[Binding] = None
		self._sweepArmed = False
		self._duration: Optional[float] = None
		self._strength = 1.0
		self._radius: Optional[float] = None
		self._pathSpec: Optional[str] = None
		self._pathUnits: Optional[QPainterPath] = None
		self._pathFit: Optional[tuple] = None
		self._fill: Optional[Color] = None
		self._phase: Optional[float] = None
		self._fade = 0.0
		self._lastT: Optional[float] = None
		self._t0 = 0.0
		self._sweepEnd = -1.0
		self._subscribed = False
		self.setParentItem(parent)
		self.setZValue(10_000)
		self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
		self.setVisible(False)
		self.prep_init(args=args, kwargs=kwargs, stateful_parent=parent)
		self.add_defaults_to_state(kwargs)
		self.state = kwargs
		self._bind()
		self._sync()

	# section geometry and painting

	def panelRect(self) -> QRectF:
		rect = self.panel.rect()
		return QRectF(rect.x(), rect.y(), rect.width(), rect.height())

	def shape(self) -> QPainterPath:
		return QPainterPath()

	def boundingRect(self) -> QRectF:
		return self.panelRect()

	def parentResized(self, *args) -> None:
		"""Connected by the panel when this item is added to it."""
		self._geometryChanged()

	def _geometryChanged(self) -> None:
		self.prepareGeometryChange()
		if self._behind is not None:
			self._behind.prepareGeometryChange()
		self._repaint()

	def _repaint(self) -> None:
		self.update()
		if self._behind is not None:
			self._behind.update()

	def outlinePath(self) -> tuple[Optional[QPainterPath], Optional[tuple]]:
		"""The custom outline fitted to the panel, with a key for the mask cache. (None, None) without one."""
		if self._pathUnits is None:
			return None, None
		rect = self.panelRect()
		key = (self._pathSpec, int(rect.width()), int(rect.height()))
		if self._pathFit is None or self._pathFit[0] != key:
			self._pathFit = (key, shapes.fitPath(self._pathUnits, rect.width(), rect.height()))
		return self._pathFit[1], key

	@property
	def cornerRadius(self) -> float:
		rect = self.panelRect()
		radius = self._radius if self._radius is not None else DEFAULT_RADII[self._size]
		return max(0.0, min(radius, rect.width() / 2, rect.height() / 2))

	@property
	def cycle(self) -> float:
		return self._duration if self._duration is not None else DEFAULT_DURATIONS[self._size]

	def clock(self) -> float:
		"""The time this beam shows: its pinned phase, or the shared clock."""
		return self._phase if self._phase is not None else PulseDriver.shared().t

	def paintContext(self) -> Optional[styles.PaintCtx]:
		"""One frame of state for the painters, or None when nothing should show."""
		rect = self.panelRect()
		if rect.width() <= 1 or rect.height() <= 1:
			return None
		size = self._size
		dark = self._theme is Theme.DARK or (self._theme is Theme.AUTO and colour_theme.active().mode == 'dark')
		preset = styles.THEME_PRESETS[size]['dark' if dark else 'light']
		brightness = preset.get('brightness', 1.3)
		saturation = preset['saturation']
		static = self._variant.is_mono
		t = self.clock() - (self._t0 if self._phase is None else 0.0)
		duration = self.cycle
		local = QRectF(0.0, 0.0, rect.width(), rect.height())
		progress = 0.0
		values = None
		hue_bloom = 0.0
		sx = sy = 1.0
		if size.is_pulse:
			params = styles.pulse_params(size, dark, duration)
			values = styles.pulse_values(params, t)
			hue = 0.0 if static else ((t / params.hue_period) % 1.0) * 360.0
			if size is Size.PULSE_OUTSIDE:
				sx = max(_PULSE_SCALE_MIN, min(_PULSE_SCALE_MAX, local.width() / _PULSE_REF_W))
				sy = max(_PULSE_SCALE_MIN, min(_PULSE_SCALE_MAX, local.height() / _PULSE_REF_H))
		else:
			progress = (t / duration) % 1.0
			hue_range = 13.0 if size is Size.LINE else 30.0
			hue = 0.0 if static else line_hue_shift(progress * duration, hue_range)
			if size is Size.LINE:
				values = styles.line_values(progress)
				if not static:
					hue_bloom = line_hue_shift(progress * duration, hue_range + 10.0)
		path, pathKey = self.outlinePath()
		return styles.PaintCtx(
			size=size, rect=local, radius=self.cornerRadius, dark=dark, variant=self._variant,
			fade=self._fade * self._strength, brightness=brightness, saturation=saturation, hue_deg=hue,
			progress=progress, duration=duration, values=values, hue_bloom=hue_bloom, sx=sx, sy=sy,
			color_space=self._colorSpace, path=path, path_key=pathKey,
		)

	def paint(self, painter: QPainter, option, widget=None) -> None:
		ctx = self.paintContext()
		if ctx is None or ctx.fade <= 0.0:
			return
		painter.save()
		try:
			painter.setRenderHint(QPainter.RenderHint.Antialiasing)
			painter.translate(self.panelRect().topLeft())
			size = ctx.size
			if size is Size.PULSE_OUTSIDE:
				styles.paint_pulse_outside_front(painter, ctx)
			elif size is Size.LINE:
				styles.paint_line_front(painter, ctx)
			elif size is Size.PULSE_INNER:
				styles.paint_pulse_inner_front(painter, ctx)
			else:
				styles.paint_ring_front(painter, ctx)
		finally:
			painter.restore()

	def paintBehind(self, painter: QPainter) -> None:
		"""The halo (pulse-outside only), then the card fill."""
		painter.save()
		try:
			painter.setRenderHint(QPainter.RenderHint.Antialiasing)
			painter.translate(self.panelRect().topLeft())
			if self._size is Size.PULSE_OUTSIDE:
				ctx = self.paintContext()
				if ctx is not None and ctx.fade > 0.0:
					styles.paint_pulse_outside_behind(painter, ctx)
			if self._fill is not None:
				rect = self.panelRect()
				radius = self.cornerRadius
				painter.setPen(Qt.PenStyle.NoPen)
				painter.setBrush(self._fill.QColor)
				if (path := self.outlinePath()[0]) is not None:
					painter.drawPath(path)
				else:
					painter.drawRoundedRect(QRectF(0.0, 0.0, rect.width(), rect.height()), radius, radius)
		finally:
			painter.restore()

	def _syncBehind(self) -> None:
		"""Make the behind layer exist when the halo or a fill needs it."""
		need = self._size is Size.PULSE_OUTSIDE or self._fill is not None
		if need and self._behind is None:
			self._behind = _BehindLayer(self)
		if self._behind is not None:
			self._behind.prepareGeometryChange()
			self._behind.setVisible(need and (self._fill is not None or self.isVisible()))
			if not need:
				scene = self._behind.scene()
				if scene is not None:
					scene.removeItem(self._behind)
				self._behind = None
		self.prepareGeometryChange()

	# section motion

	@property
	def wanted(self) -> bool:
		"""True while the beam is meant to show: active, or inside a sweep."""
		if self._activeOn:
			return True
		return self._sweepEnd >= 0.0 and self.clock() < self._sweepEnd

	def _sync(self) -> None:
		"""Decide what the beam does next: pinned, animating or idle. Call after any change."""
		driver = PulseDriver.shared()
		if self._phase is not None:
			# Held: no clock, no fade. It shows fully or not at all.
			self._unsubscribe()
			self._fade = 1.0 if self._activeOn else 0.0
		elif self.wanted or self._fade > 0.0:
			self._lastT = driver.t
			self._subscribe()
		else:
			self._unsubscribe()
			self._fade = 0.0
		self._syncBehind()
		self.setVisible(self._fade > 0.0 or self.wanted)
		if self._behind is not None and self._fill is None:
			self._behind.setVisible(self.isVisible())
		self._repaint()

	def _subscribe(self) -> None:
		if not self._subscribed:
			self._subscribed = True
			PulseDriver.shared().subscribe(self)

	def _unsubscribe(self) -> None:
		if self._subscribed:
			self._subscribed = False
			PulseDriver.shared().unsubscribe(self)

	def tick(self, t: float) -> None:
		"""One frame from the shared clock."""
		last = self._lastT if self._lastT is not None else t
		self._lastT = t
		dt = max(0.0, t - last)
		if self.wanted:
			self._fade = min(1.0, self._fade + dt / _FADE_IN)
		else:
			self._fade = max(0.0, self._fade - dt / _FADE_OUT)
			if self._fade <= 0.0:
				self._sweepEnd = -1.0
				self._sync()
				return
		self._repaint()

	def runSweep(self) -> None:
		"""Run the beam once: one cycle of a rotating beam, two breaths of a pulse."""
		driver = PulseDriver.shared()
		now = driver.t
		self._t0 = now
		self._sweepEnd = now + self.cycle * _SWEEP_CYCLES[self._size]
		self._sync()

	# section bindings

	def _setActive(self, value: Any) -> None:
		on = _truthy(value)
		if on == self._activeOn:
			return
		self._activeOn = on
		if on:
			# A run that starts from a condition begins at its own zero, not mid-cycle.
			self._t0 = PulseDriver.shared().t
		self._sync()

	def _onSweepValue(self, value: Any) -> None:
		if not self._sweepArmed:
			return  # the value that was already there when the binding opened is not news
		self.runSweep()

	def _unbind(self) -> None:
		for name in ('_activeBinding', '_sweepBinding'):
			binding = getattr(self, name)
			if binding is not None:
				binding.unlink()
				setattr(self, name, None)
		self._sweepArmed = False

	def _bind(self) -> None:
		"""Open the value sources for `active` and `sweep`. Replaces any open ones."""
		self._unbind()
		spec = self._activeSpec
		if isinstance(spec, str):
			if (source := openValueSource(spec, 'beam active', 'the beam stays off')) is not None:
				self._activeBinding = Binding(source, self._setActive)
		else:
			self._setActive(bool(spec))
		if self._sweepSpec:
			if (source := openValueSource(self._sweepSpec, 'beam sweep', 'the beam does not sweep')) is not None:
				self._sweepBinding = Binding(source, self._onSweepValue)
				self._sweepArmed = True

	def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: Any) -> Any:
		if change == QGraphicsItem.GraphicsItemChange.ItemSceneChange:
			if value is None:
				# Leaving the scene (the panel was deleted, or the dashboard reloaded): stop the clock and release the sources.
				self._unbind()
				self._unsubscribe()
		elif change == QGraphicsItem.GraphicsItemChange.ItemSceneHasChanged:
			if value is not None and self._activeBinding is None and self._sweepBinding is None and (self._sweepSpec or isinstance(self._activeSpec, str)):
				self._bind()
		return super().itemChange(change, value)

	# section state properties

	def _changed(self) -> None:
		self._sync()
		self._geometryChanged()

	@StateProperty(default=Size.MEDIUM, allowNone=False, after=_changed, choices=[s for s in Size])
	def size(self) -> Size:
		"""The shape: `sm` a compact ring, `md` a full border, `line` bottom only, `pulse-inner` a breathing inner edge, `pulse-outside` a halo."""
		return self._size

	@size.setter
	def size(self, value: Size):
		self._size = value

	@size.decode
	def size(self, value) -> Size:
		return _enum(Size, value, Size.MEDIUM)

	@size.encode
	def size(self, value: Size) -> str:
		return value.value

	@StateProperty(default=ColorVariant.COLORFUL, allowNone=False, after=_changed, choices=[v for v in ColorVariant])
	def variant(self) -> ColorVariant:
		"""The palette: `colorful` (rainbow), `mono` (grey), `ocean` (blue and purple), `sunset` (orange and red)."""
		return self._variant

	@variant.setter
	def variant(self, value: ColorVariant):
		self._variant = value

	@variant.decode
	def variant(self, value) -> ColorVariant:
		return _enum(ColorVariant, value, ColorVariant.COLORFUL)

	@variant.encode
	def variant(self, value: ColorVariant) -> str:
		return value.value

	@StateProperty(default=Theme.AUTO, allowNone=False, after=_changed, choices=[Theme.AUTO, Theme.DARK, Theme.LIGHT])
	def theme(self) -> Theme:
		"""`dark` for a dark card, `light` for a light one. The strengths and saturation differ. `auto` follows the dashboard theme's mode."""
		return self._theme

	@theme.setter
	def theme(self, value: Theme):
		self._theme = value

	@theme.decode
	def theme(self, value) -> Theme:
		return _enum(Theme, value, Theme.AUTO)

	@theme.encode
	def theme(self, value: Theme) -> str:
		return value.value

	@StateProperty(key='color-space', default=ColorSpace.HSV, allowNone=False, after=_changed, choices=[s for s in ColorSpace])
	def colorSpace(self) -> ColorSpace:
		"""`hsv` keeps the upstream colours. `oklch` takes them from LevityDash's palette ring."""
		return self._colorSpace

	@colorSpace.setter
	def colorSpace(self, value: ColorSpace):
		self._colorSpace = value

	@colorSpace.decode
	def colorSpace(self, value) -> ColorSpace:
		return _enum(ColorSpace, value, ColorSpace.HSV)

	@colorSpace.encode
	def colorSpace(self, value: ColorSpace) -> str:
		return value.value

	@StateProperty(default=None, allowNone=True, after=_changed)
	def duration(self) -> Optional[float]:
		"""Seconds per cycle. Left out, the size decides: 1.96 for sm and md, 3.1 for line, 2.3 for the pulses."""
		return self._duration

	@duration.setter
	def duration(self, value: Optional[float]):
		self._duration = value

	@duration.decode
	def duration(self, value) -> Optional[float]:
		return None if value is None else max(0.1, float(value))

	@StateProperty(default=1.0, allowNone=False, after=_changed)
	def strength(self) -> float:
		"""How bright the beam is, 0 to 1."""
		return self._strength

	@strength.setter
	def strength(self, value: float):
		self._strength = value

	@strength.decode
	def strength(self, value) -> float:
		return min(1.0, max(0.0, float(value)))

	@StateProperty(default=None, allowNone=True, after=_changed)
	def radius(self) -> Optional[float]:
		"""Corner radius in px. Left out, the size decides (32 for sm, 16 for the rest)."""
		return self._radius

	@radius.setter
	def radius(self, value: Optional[float]):
		self._radius = value

	@radius.decode
	def radius(self, value) -> Optional[float]:
		return None if value is None else max(0.0, float(value))

	@StateProperty(default=None, allowNone=True, after=_changed)
	def path(self) -> Optional[str]:
		"""The outline the beam follows: SVG path data (M, L, H, V, C, S, Q, T, A, Z), or one of `circle`, `diamond`, `triangle`, `arc`, `wave`, `heart`. It is scaled to fill the panel. Left out, the beam follows the panel's rounded rectangle."""
		return self._pathSpec

	@path.setter
	def path(self, value: Optional[str]):
		self._pathSpec = value
		self._pathFit = None
		try:
			self._pathUnits = shapes.resolve(value)
		except ValueError as e:
			log.warning(f'beam path {value!r} is not usable ({e}); following the panel outline')
			self._pathUnits = None

	@path.decode
	def path(self, value) -> Optional[str]:
		return None if value in (None, False, '') else str(value)

	@StateProperty(default=None, allowNone=True, after=_changed)
	def fill(self) -> Optional[Color]:
		"""A card colour painted under the content and inside the beam. `pulse-outside` needs one, as its halo lies behind the card."""
		return self._fill

	@fill.setter
	def fill(self, value: Optional[Color]):
		self._fill = value

	@fill.decode
	def fill(self, value) -> Optional[Color]:
		if value in (None, False):
			return None
		return value if isinstance(value, Color) else Color(value)

	@fill.encode
	def fill(self, value: Optional[Color]):
		return None if value is None else str(value)

	@StateProperty(default=False, allowNone=False, after=_bind)
	def active(self) -> bool | str:
		"""`true` runs the beam, `false` turns it off. A key or expression runs it while the value is true, for example `environment.wind.speed.speed > 25`."""
		return self._activeSpec

	@active.setter
	def active(self, value: bool | str):
		self._activeSpec = value

	@active.decode
	def active(self, value) -> bool | str:
		return value if isinstance(value, (bool, str)) else bool(value)

	@StateProperty(default=None, allowNone=True, after=_bind)
	def sweep(self) -> Optional[str]:
		"""A key or expression. The beam runs once each time a new value arrives."""
		return self._sweepSpec

	@sweep.setter
	def sweep(self, value: Optional[str]):
		self._sweepSpec = value

	@sweep.decode
	def sweep(self, value) -> Optional[str]:
		return None if value in (None, False, '') else str(value)

	@StateProperty(default=None, allowNone=True, after=_sync)
	def phase(self) -> Optional[float]:
		"""Hold the beam at this time in seconds, with no animation. For renders and previews."""
		return self._phase

	@phase.setter
	def phase(self, value: Optional[float]):
		self._phase = value

	@phase.decode
	def phase(self, value) -> Optional[float]:
		return None if value is None else max(0.0, float(value))
