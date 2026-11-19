"""A band shows a row (or column) of items and scrolls through the ones that do not fit.

```yaml
- type: band
  mode: step          # step (a page at a time, with a pause) or continuous (a marquee)
  visible: 3          # how many items are in view at once (may be fractional: 3.5 lets the next one peek in)
  direction: left     # left, right, up or down: which way the content moves
  gap: 2%             # space between items, a share of the band's length
  dwell: 8s           # step: how long each stop lasts
  transition: 600ms   # step: how long a move takes
  step: 1             # step: items per move (`page` moves a whole page of `visible`)
  speed: 0.25         # continuous: items per second
  fps: 30             # continuous: frames per second (a lower number costs less on a slow machine)
  items:
    - type: group
      ...
```

Every item is as long as `(band - gaps) / visible` and as wide as the band is tall (or the other way round when the
band scrolls up or down). The items sit in a ring: the one that leaves one end comes in at the other, so the wrap has no
seam. A band needs at least `visible + 1` items to scroll; with fewer it shows them in a row and stands still.

It is made to be cheap. The layout is worked out once, as shares of the band, and never again, so a resize costs
what it costs any group. A move only changes each item's own translation, with no geometry update, and in continuous
mode each item is drawn once into a pixmap that is then just moved (`cache: false` turns that off, for an item with
something that changes every frame). A step band does nothing at all between moves.

Nothing here raises. A band that is not on screen does not tick.
"""
import math
import time
from typing import Any, List, Optional

from PySide6.QtCore import QEasingCurve, QTimer, QVariantAnimation
from PySide6.QtGui import QTransform
from PySide6.QtWidgets import QGraphicsItem

from LevityDash.lib.stateful import DefaultGroup, StateProperty
from LevityDash.lib.ui import UILogger as guiLog
from LevityDash.lib.ui.frontends.PySide.Modules.Panel import Panel
from LevityDash.lib.ui.frontends.PySide.Modules.condition import parseSeconds
from LevityDash.lib.ui.frontends.PySide.utils import itemLoader

__all__ = ["Band"]

log = guiLog.getChild(__name__)

MODES = {'step': 'step', 'piecewise': 'step', 'page': 'step', 'pages': 'step',
         'continuous': 'continuous', 'marquee': 'continuous', 'smooth': 'continuous'}
DIRECTIONS = ('left', 'right', 'up', 'down')


def slots(count: int, position: float, sign: int) -> List[float]:
	"""Where each of `count` items in a ring sits, in item steps from the start of the window.

	At position 0 item `i` is at slot `i`. Moving by `position` steps shifts every slot back (`sign` 1) or forward
	(`sign` -1), and an item that leaves one end comes in at the other: slots are always in [-1, count - 1).
	"""
	return [((i - sign * position + 1) % count) - 1 for i in range(count)]


def scrolls(count: int, visible: float) -> bool:
	"""Whether there is anything to scroll: at least one item more than is in view, so the wrap happens off screen."""
	return count - 1 >= visible and count > 1


class Band(Panel, tag='band'):
	_mode: str = 'step'
	_visible: float = 3.0
	_direction: str = 'left'
	_gap: float = 0.0
	_dwell: float = 8.0
	_transition: float = 0.6
	_stepSize: Optional[float] = 1.0
	_speed: float = 0.25
	_fps: float = 30.0
	_cache: bool = True

	def __init__(self, *args, **kwargs):
		self._position = 0.0
		self._started = 0.0
		self._applied: dict = {}
		self._moving = False
		self._dwellTimer = QTimer()
		self._dwellTimer.setSingleShot(True)
		self._dwellTimer.timeout.connect(self._advance)
		self._frameTimer = QTimer()
		self._frameTimer.timeout.connect(self._frame)
		self._animation: Optional[QVariantAnimation] = None
		super().__init__(*args, **kwargs)
		self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape, True)

	# section ring

	@property
	def choices(self) -> List[Panel]:
		return [child for child in self.childItems() if isinstance(child, Panel) and hasattr(child, 'condition')]

	@property
	def shown(self) -> List[Panel]:
		"""The items in the ring now: those whose `when:` holds (an item without one always does)."""
		return [child for child in self.choices if child.condition.holds]

	def childConditionChanged(self, child: Panel) -> None:
		"""An item's `when:` changed: it leaves or joins the ring, and the others close up around it."""
		self._reflowShown()

	def _reflowShown(self) -> None:
		"""Hide the items whose `when:` fails. Each keeps its laid-out slot; `place` translates the rest to close the gap."""
		shown = self.shown
		for child in self.choices:
			child.setVisible(child in shown)
		self._applied.clear()
		if shown:
			self._position %= len(shown)
		self._restart()

	@property
	def vertical(self) -> bool:
		return self._direction in ('up', 'down')

	@property
	def sign(self) -> int:
		return 1 if self._direction in ('left', 'up') else -1

	@property
	def running(self) -> bool:
		return scrolls(len(self.shown), self._visible)

	@property
	def position(self) -> float:
		"""How many item steps the ring has moved."""
		return self._position

	def _length(self) -> float:
		"""Pixels along the scroll axis."""
		rect = self.rect()
		return rect.height() if self.vertical else rect.width()

	def _share(self) -> float:
		"""One item's length as a share of the band."""
		visible = max(self._visible, 1e-6)
		return max(0.0, (1.0 - self._gap * (math.ceil(visible) - 1)) / visible)

	def _stride(self) -> float:
		"""Distance between two neighbours as a share of the band."""
		return self._share() + self._gap

	def place(self, position: Optional[float] = None) -> None:
		"""Move every item to where `position` puts it. Only translations change; nothing is laid out."""
		if position is not None:
			self._position = position
		every = self.choices
		children = [child for child in every if child.condition.holds]
		count = len(children)
		if count == 0:
			return
		length = self._length()
		stride = self._stride() * length
		moving = scrolls(count, self._visible)
		where = slots(count, self._position, self.sign) if moving else list(range(count))
		for index, child in enumerate(children):
			# Each item was laid out at its place in the file; a hidden one before it leaves a gap to close.
			delta = round((where[index] - every.index(child)) * stride, 2)
			if self._applied.get(child) == delta:
				continue
			self._applied[child] = delta
			child.setTransform(QTransform.fromTranslate(0.0, delta) if self.vertical else QTransform.fromTranslate(delta, 0.0))

	def afterSurface(self):
		"""The band was sized or moved: translations are in pixels, so work them out again for the new length."""
		super().afterSurface()
		length = self._length()
		if length != getattr(self, '_placedLength', None):
			self._placedLength = length
			self._applied.clear()
			if self.running:
				self.place()

	# section clock

	def _wanted(self) -> bool:
		return self.running and self.scene() is not None and self.isVisible()

	def _restart(self) -> None:
		"""Start, stop or switch the clock to match the settings and the items."""
		self._stopClock()
		self.place(self._position if self.running else 0.0)
		self._cacheChildren(self._cache and self._mode == 'continuous' and self.running)
		if not self._wanted():
			return
		if self._mode == 'continuous':
			self._started = time.monotonic() - self._position / max(self._speed, 1e-6) * self.sign
			if self._speed > 0:
				self._frameTimer.start(max(1, int(1000 / max(self._fps, 1.0))))
		else:
			self._dwellTimer.start(int(max(self._dwell, 0.05) * 1000))

	def _stopClock(self) -> None:
		self._dwellTimer.stop()
		self._frameTimer.stop()
		if self._animation is not None:
			self._animation.stop()
			self._animation = None

	def _frame(self) -> None:
		if not self._wanted():
			return
		try:
			elapsed = time.monotonic() - self._started
			count = len(self.shown)
			self.place((elapsed * self._speed * self.sign) % count)
		except Exception:
			log.exception('band could not move; stopping it')
			self._frameTimer.stop()

	def _advance(self) -> None:
		if not self._wanted():
			self._dwellTimer.start(int(max(self._dwell, 0.05) * 1000))  # look again later; costs nothing
			return
		try:
			count = len(self.shown)
			step = self._stepSize if self._stepSize else max(1.0, math.floor(self._visible))
			start, end = self._position, self._position + step * self.sign
			if self._transition <= 0:
				self._arrive(end % count)
				return
			animation = QVariantAnimation()
			animation.setStartValue(float(start))
			animation.setEndValue(float(end))
			animation.setDuration(int(self._transition * 1000))
			animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
			animation.valueChanged.connect(lambda value: self.place(float(value) % count))
			animation.finished.connect(lambda: self._arrive(end % count))
			self._animation = animation
			animation.start()
		except Exception:
			log.exception('band could not step; stopping it')

	def _arrive(self, position: float) -> None:
		self._animation = None
		self.place(position)
		self._dwellTimer.start(int(max(self._dwell, 0.05) * 1000))

	def _cacheChildren(self, on: bool) -> None:
		mode = QGraphicsItem.CacheMode.DeviceCoordinateCache if on else QGraphicsItem.CacheMode.NoCache
		for child in self.choices:
			if child.cacheMode() != mode:
				child.setCacheMode(mode)

	def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: Any) -> Any:
		if change == QGraphicsItem.GraphicsItemChange.ItemSceneChange and value is None:
			self._stopClock()  # leaving the scene: the dashboard reloaded or this was deleted
		elif change == QGraphicsItem.GraphicsItemChange.ItemSceneHasChanged and value is not None:
			QTimer.singleShot(0, self._restart)
		elif change == QGraphicsItem.GraphicsItemChange.ItemVisibleHasChanged:
			QTimer.singleShot(0, self._restart)
		return super().itemChange(change, value)

	# section items

	def _layout(self, items: List[dict]) -> None:
		"""Give each item its share of the band, once. A resize then needs nothing: shares follow the parent."""
		share, stride = self._share(), self._stride()
		for index, item in enumerate(items):
			if not isinstance(item, dict):
				continue
			if self.vertical:
				item['geometry'] = {'x': '0%', 'y': f'{index * stride * 100:.4f}%', 'width': '100%', 'height': f'{share * 100:.4f}%'}
			else:
				item['geometry'] = {'x': f'{index * stride * 100:.4f}%', 'y': '0%', 'width': f'{share * 100:.4f}%', 'height': '100%'}

	@StateProperty(
		sort=True,
		sortKey=lambda x: x.geometry.sortValue,
		default=DefaultGroup(None, []),
		dependencies={'geometry', 'margins'},
		sortOrder=-1,
	)
	def items(self) -> List[Panel]:
		return self.choices

	@items.setter
	def items(self, value: List[dict]):
		self._rawItems = [dict(item) if isinstance(item, dict) else item for item in value]
		self._layout(value)
		self.geometry.updateSurface()
		self._applied.clear()
		itemLoader(self, value, existing=self.choices)
		self._reflowShown()

	@items.condition(method='get')
	def items(owner: 'Band') -> bool:
		return owner.hasChildren

	@items.condition(method={'get', 'set'})
	def items(value: List[Panel]) -> bool:
		return hasattr(value, '__len__') and len(value) > 0

	__child_exclude__ = {'geometry', 'movable'}

	def _relayout(self) -> None:
		"""A setting that changes the shares (`visible`, `gap`, `direction`) places the items again."""
		raw = getattr(self, '_rawItems', None)
		children = self.choices
		if not children or not self.scene():
			return
		for index, child in enumerate(sorted(children, key=lambda c: c.geometry.sortValue)):
			share, stride = self._share(), self._stride()
			geometry = ({'x': '0%', 'y': f'{index * stride * 100:.4f}%', 'width': '100%', 'height': f'{share * 100:.4f}%'} if self.vertical else
			            {'x': f'{index * stride * 100:.4f}%', 'y': '0%', 'width': f'{share * 100:.4f}%', 'height': '100%'})
			try:
				child.state = {'geometry': geometry}
			except Exception:
				log.exception('band could not place an item')
		self._applied.clear()
		self._restart()

	# section settings

	@StateProperty(default='step', allowNone=False, sortOrder=60)
	def mode(self) -> str:
		"""`step` moves a page at a time and rests between moves (`dwell`, `transition`, `step`); `continuous` scrolls smoothly like a marquee (`speed`, `fps`)."""
		return self._mode

	@mode.setter
	def mode(self, value: str):
		self._mode = value
		self._restart()

	@mode.decode
	def mode(self, value) -> str:
		key = str(value).strip().casefold()
		if key not in MODES:
			raise ValueError(f'mode is {value!r}; it is step or continuous')
		return MODES[key]

	@StateProperty(default=3.0, allowNone=False, sortOrder=61)
	def visible(self) -> float:
		"""How many items are in view at once. A fraction (`3.5`) lets the next item peek in at the edge."""
		return self._visible

	@visible.setter
	def visible(self, value: float):
		self._visible = value
		self._relayout()

	@visible.decode
	def visible(self, value) -> float:
		number = float(value)
		if number < 1:
			raise ValueError('visible is at least 1')
		return number

	@StateProperty(default='left', allowNone=False, sortOrder=62)
	def direction(self) -> str:
		"""Which way the content moves: `left` (new items come in from the right; the default), `right`, `up` or `down`."""
		return self._direction

	@direction.setter
	def direction(self, value: str):
		was = self.vertical
		self._direction = value
		if was != self.vertical:
			self._relayout()
		else:
			self._restart()

	@direction.decode
	def direction(self, value) -> str:
		key = str(value).strip().casefold()
		if key not in DIRECTIONS:
			raise ValueError(f'direction is {value!r}; it is {", ".join(DIRECTIONS)}')
		return key

	@StateProperty(default=0.0, allowNone=False, sortOrder=63)
	def gap(self) -> float:
		"""Space between items as a share of the band's length: `2%` or `0.02`."""
		return self._gap

	@gap.setter
	def gap(self, value: float):
		self._gap = value
		self._relayout()

	@gap.decode
	def gap(self, value) -> float:
		text = str(value).strip()
		number = float(text[:-1]) / 100 if text.endswith('%') else float(text)
		if not 0 <= number < 0.5:
			raise ValueError('gap is between 0% and 50%')
		return number

	@gap.encode
	def gap(self, value) -> str:
		return f'{value * 100:g}%'

	@StateProperty(default=8.0, allowNone=False, sortOrder=64)
	def dwell(self) -> float:
		"""Step mode: seconds each stop lasts."""
		return self._dwell

	@dwell.setter
	def dwell(self, value: float):
		self._dwell = value
		self._restart()

	@dwell.decode
	def dwell(self, value) -> float:
		return parseSeconds(value, 8.0)

	@StateProperty(default=0.6, allowNone=False, sortOrder=65)
	def transition(self) -> float:
		"""Step mode: seconds one move takes. `0` jumps."""
		return self._transition

	@transition.setter
	def transition(self, value: float):
		self._transition = value

	@transition.decode
	def transition(self, value) -> float:
		return parseSeconds(value, 0.6)

	@StateProperty(default=1.0, allowNone=False, sortOrder=66)
	def step(self) -> float | str:
		"""Step mode: items per move. `page` moves a whole page (`visible` items)."""
		return 'page' if not self._stepSize else self._stepSize

	@step.setter
	def step(self, value):
		self._stepSize = value

	@step.decode
	def step(self, value):
		if isinstance(value, str) and value.strip().casefold() in ('page', 'pages'):
			return None
		number = float(value)
		if number <= 0:
			raise ValueError('step is above 0, or `page`')
		return number

	@StateProperty(default=0.25, allowNone=False, sortOrder=67)
	def speed(self) -> float:
		"""Continuous mode: items per second (`0.25` is four seconds an item). `0` stands still."""
		return self._speed

	@speed.setter
	def speed(self, value: float):
		self._speed = value
		self._restart()

	@speed.decode
	def speed(self, value) -> float:
		number = float(value)
		if number < 0:
			raise ValueError('speed is not negative; use `direction` to go the other way')
		return number

	@StateProperty(default=30.0, allowNone=False, sortOrder=68)
	def fps(self) -> float:
		"""Continuous mode: frames per second. Lower it on a slow machine."""
		return self._fps

	@fps.setter
	def fps(self, value: float):
		self._fps = value
		self._restart()

	@fps.decode
	def fps(self, value) -> float:
		number = float(value)
		if not 1 <= number <= 120:
			raise ValueError('fps is between 1 and 120')
		return number

	@StateProperty(default=True, allowNone=False, sortOrder=69)
	def cache(self) -> bool:
		"""Continuous mode: draw each item once and move the picture. Turn it off for an item that changes every frame."""
		return self._cache

	@cache.setter
	def cache(self, value: bool):
		self._cache = bool(value)
		self._restart()
