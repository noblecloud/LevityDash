"""A slot that shows one of several panels.

```yaml
- type: switch
  hold: 30s        # a change must hold this long before the slot flips
  fade: 300ms
  cycle: 8s        # optional: take turns when more than one child matches
  items:
    - when: environment.precipitation.precipitation > 0
      type: group
      ...
    - type: realtime.gauge     # no `when`: always matches, so it is the default
      key: environment.light.uvi
```

Each child fills the slot. The first child whose `when` holds is shown; one with
no `when` always matches. The slot keeps its place in the stack or group that
holds it, so the space a hidden panel frees goes to its replacement, not to
blank. With `cycle`, every matching child takes a turn. A choice never rebuilds
anything: the slot only toggles visibility and opacity.

Nothing here raises. A bad `when` counts as false (and is logged by the
condition), and with no match the slot shows nothing.
"""
from typing import Any, List, Optional

from PySide6.QtCore import QTimer, QVariantAnimation
from PySide6.QtWidgets import QGraphicsItem

from LevityDash.lib.stateful import DefaultGroup, StateProperty
from LevityDash.lib.ui import UILogger as guiLog
from LevityDash.lib.ui.frontends.PySide.Modules.Panel import Panel
from LevityDash.lib.ui.frontends.PySide.Modules.condition import parseSeconds
from LevityDash.lib.ui.frontends.PySide.utils import itemLoader

__all__ = ["Switch"]

log = guiLog.getChild(__name__)


class Switch(Panel, tag='switch'):
	_active: Optional[Panel] = None
	_hold: float = 30.0
	_fade: float = 0.3
	_cycle: float = 0.0

	def __init__(self, *args, **kwargs):
		self._pending: Optional[Panel] = None
		self._holdTimer = QTimer()
		self._holdTimer.setSingleShot(True)
		self._holdTimer.timeout.connect(self._holdElapsed)
		self._cycleTimer = QTimer()
		self._cycleTimer.timeout.connect(self._advance)
		self._animations: dict = {}
		self._baseOpacity: dict = {}
		super().__init__(*args, **kwargs)

	# section choosing

	@property
	def choices(self) -> List[Panel]:
		return [child for child in self.childItems() if isinstance(child, Panel) and hasattr(child, 'condition')]

	@property
	def active(self) -> Optional[Panel]:
		return self._active

	def _matches(self) -> List[Panel]:
		return [child for child in self.choices if child.condition.holds]

	def _target(self, matches: List[Panel]) -> Optional[Panel]:
		if not matches:
			return None
		if self._cycle > 0 and self._active in matches:
			return self._active
		return matches[0]

	def childConditionChanged(self, child: Panel) -> None:
		self._evaluate()

	def _evaluate(self, settled: bool = False) -> None:
		"""Pick what to show. A change waits `hold` seconds, unless nothing is shown yet or `settled`."""
		try:
			matches = self._matches()
			target = self._target(matches)
			self._syncCycle(matches)
			if target is self._active and (target is not None or self._active is None):
				self._cancelHold()
				self._applyVisibility()
				return
			if settled or self._active is None or self._hold <= 0:
				self._cancelHold()
				self._show(target)
				return
			if target is self._pending and self._holdTimer.isActive():
				return
			self._pending = target
			self._holdTimer.start(int(self._hold * 1000))
		except Exception:
			log.exception('switch could not choose a child; leaving it as it is')

	def _holdElapsed(self) -> None:
		self._pending = None
		self._evaluate(settled=True)

	def _cancelHold(self) -> None:
		self._pending = None
		self._holdTimer.stop()

	def _syncCycle(self, matches: List[Panel]) -> None:
		wanted = self._cycle > 0 and len(matches) > 1
		if wanted and not self._cycleTimer.isActive():
			self._cycleTimer.start(int(self._cycle * 1000))
		elif not wanted and self._cycleTimer.isActive():
			self._cycleTimer.stop()

	def _advance(self) -> None:
		matches = self._matches()
		if len(matches) < 2:
			self._cycleTimer.stop()
			return
		try:
			index = (matches.index(self._active) + 1) % len(matches) if self._active in matches else 0
		except ValueError:
			index = 0
		self._cancelHold()
		self._show(matches[index])

	# section showing

	def _show(self, target: Optional[Panel]) -> None:
		previous = self._active
		self._active = target
		if previous is target:
			self._applyVisibility()
			return
		for child in self.choices:
			if child is target or child is previous:
				continue
			self._stopFade(child)
			child.setVisible(False)
		if previous is not None and previous.scene() is not None:
			self._fadeOut(previous)
		if target is not None:
			self._fadeIn(target, fromNothing=previous is None)

	def _applyVisibility(self) -> None:
		for child in self.choices:
			if child is not self._active and child not in self._animations:
				child.setVisible(False)
		if self._active is not None and self._active not in self._animations:
			self._active.setVisible(True)

	def _base(self, child: Panel) -> float:
		return self._baseOpacity.setdefault(child, child.opacity())

	def _stopFade(self, child: Panel) -> None:
		if (animation := self._animations.pop(child, None)) is not None:
			animation.stop()
			child.setOpacity(self._baseOpacity.get(child, 1.0))

	def _fadeIn(self, child: Panel, fromNothing: bool) -> None:
		self._stopFade(child)
		base = self._base(child)
		child.setVisible(True)
		if self._fade <= 0 or fromNothing:
			child.setOpacity(base)
			return
		self._animate(child, 0.0, base, hideAtEnd=False)

	def _fadeOut(self, child: Panel) -> None:
		self._stopFade(child)
		base = self._base(child)
		if self._fade <= 0:
			child.setVisible(False)
			child.setOpacity(base)
			return
		self._animate(child, base, 0.0, hideAtEnd=True)

	def _animate(self, child: Panel, start: float, end: float, hideAtEnd: bool) -> None:
		animation = QVariantAnimation()
		animation.setStartValue(float(start))
		animation.setEndValue(float(end))
		animation.setDuration(int(self._fade * 1000))
		animation.valueChanged.connect(lambda value, c=child: c.setOpacity(float(value)))

		def done(c=child):
			if self._animations.get(c) is animation:
				del self._animations[c]
			if hideAtEnd:
				c.setVisible(False)
				c.setOpacity(self._baseOpacity.get(c, 1.0))
		animation.finished.connect(done)
		self._animations[child] = animation
		animation.start()

	# section items

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
		for item in value:
			if isinstance(item, dict) and 'geometry' not in item:
				item['geometry'] = {'fillParent': True}
		self.geometry.updateSurface()
		itemLoader(self, value, existing=self.choices)
		for child in tuple(self._animations):
			self._stopFade(child)
		self._baseOpacity.clear()
		self._active = None
		self._evaluate()

	@items.condition(method='get')
	def items(owner: 'Switch') -> bool:
		return owner.hasChildren

	@items.condition(method={'get', 'set'})
	def items(value: List[Panel]) -> bool:
		return hasattr(value, '__len__') and len(value) > 0

	@StateProperty(default=30.0, allowNone=False, sortOrder=60)
	def hold(self) -> float:
		"""Seconds a change must last before the slot flips, so a value hovering at a threshold does not flap. The first pick is instant."""
		return self._hold

	@hold.setter
	def hold(self, value: float):
		self._hold = value

	@hold.decode
	def hold(self, value) -> float:
		return parseSeconds(value, 30.0)

	@StateProperty(default=0.3, allowNone=False, sortOrder=61)
	def fade(self) -> float:
		"""Seconds the old child fades out and the new one fades in. `0` swaps at once."""
		return self._fade

	@fade.setter
	def fade(self, value: float):
		self._fade = value

	@fade.decode
	def fade(self, value) -> float:
		return parseSeconds(value, 0.3)

	@StateProperty(default=0.0, allowNone=False, sortOrder=62)
	def cycle(self) -> float:
		"""Seconds each matching child stays up before the next takes over. `0` (the default) never rotates."""
		return self._cycle

	@cycle.setter
	def cycle(self, value: float):
		self._cycle = value
		self._evaluate()

	@cycle.decode
	def cycle(self, value) -> float:
		return parseSeconds(value, 0.0)

	def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: Any) -> Any:
		if change == QGraphicsItem.GraphicsItemChange.ItemSceneChange and value is None:
			# Leaving the scene (deleted, or the dashboard reloaded): stop every clock.
			self._holdTimer.stop()
			self._cycleTimer.stop()
			for animation in tuple(self._animations.values()):
				animation.stop()
			self._animations.clear()
		return super().itemChange(change, value)
