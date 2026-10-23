"""A condition on a panel: `when:` takes a key, an expression, a plain bool, or a size condition.

A mapping is a size condition (`lib/sizequery.py`): it follows the window or the parent's size, read here in the
frontend, and may add a data condition with `and:`.

`PanelCondition` is the value-source half of `when:`. It holds no widgets, so
`Panel` can own one without an import cycle. A missing value counts as false, a
bad expression logs once and counts as false, and nothing here raises.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Optional

from LevityDash.lib.log import LevityPluginLog
from LevityDash.lib.sizequery import SizeQuery, isSizeQuery
from LevityDash.lib.stateful import Binding
from LevityDash.lib.valuesource import openValueSource

__all__ = ["PanelCondition", "parseSeconds"]

log = LevityPluginLog.getChild("Condition")

_UNITS = {'ms': 0.001, 's': 1.0, 'm': 60.0, 'h': 3600.0}
_DURATION = re.compile(r'^\s*(\d+(?:\.\d+)?)\s*(ms|s|m|h)?\s*$')


def parseSeconds(value: Any, default: float = 0.0) -> float:
	"""A duration as seconds: `30`, `30s`, `500ms`, `2m`, `1h`. Bad input gives `default`, with a log."""
	if isinstance(value, bool) or value is None:
		return default
	if isinstance(value, (int, float)):
		return max(0.0, float(value))
	if isinstance(value, str) and (match := _DURATION.match(value)):
		return float(match.group(1)) * _UNITS[match.group(2) or 's']
	log.warning(f'duration {value!r} must be a number or a number with ms, s, m or h; using {default}s')
	return default


def _truthy(value: Any) -> bool:
	value = getattr(value, 'value', value)
	try:
		return bool(value)
	except Exception:
		return False


class PanelCondition:
	"""`holds` is True with no spec, and follows the value source otherwise.

	The source opens only while the panel is in a scene, and closes when it
	leaves, so a dashboard reload releases every lease.
	"""

	def __init__(self, panel, onChange: Callable[[], None]):
		self._panel = panel
		self._onChange = onChange
		self._spec: Any = None
		self._holds = True
		self._binding: Optional[Binding] = None
		self._query: Optional[SizeQuery] = None
		self._sizeHolds = False
		self._dataHolds = True
		self._sizeSource: Any = None

	@property
	def spec(self) -> Any:
		return self._spec

	@spec.setter
	def spec(self, value: Any):
		if value == self._spec and (self._binding is not None or not isinstance(value, (str, dict))):
			return
		self._unbind()
		self._spec = value
		self._bind()

	@property
	def holds(self) -> bool:
		return self._holds

	def attach(self) -> None:
		"""The panel entered a scene: open the source if one is wanted and not yet open."""
		if self._binding is None and self._sizeSource is None and isinstance(self._spec, (str, dict)):
			self._bind()

	def detach(self) -> None:
		"""The panel left its scene: release the source."""
		self._unbind()

	def _set(self, value: Any) -> None:
		holds = _truthy(value)
		if self._query is not None:
			self._dataHolds = holds
			holds = self._sizeHolds and holds
		if holds != self._holds:
			self._holds = holds
			self._onChange()

	def _measure(self) -> tuple:
		"""The width and height the size condition reads: the window (the scene) or the parent item."""
		panel = self._panel
		if self._query.of == 'parent':
			if (parent := panel.parentItem()) is None:
				return 0.0, 0.0
			rect = parent.rect() if hasattr(parent, 'rect') else parent.boundingRect()
		elif (scene := panel.scene()) is not None:
			rect = scene.sceneRect()
		else:
			return 0.0, 0.0
		return rect.width(), rect.height()

	def _sizeChanged(self, *_) -> None:
		if self._query is None:
			return
		self._sizeHolds = self._query.matches(*self._measure())
		self._set(self._dataHolds)

	def _bindSize(self) -> None:
		query = self._query
		panel = self._panel
		if panel.scene() is None:
			return
		if query.of == 'parent':
			if (parent := panel.parentItem()) is not None and getattr(parent, 'signals', None) is not None:
				parent.signals.resized.connect(self._sizeChanged)
				self._sizeSource = parent.signals.resized
		else:
			panel.scene().sceneRectChanged.connect(self._sizeChanged)
			self._sizeSource = panel.scene().sceneRectChanged
		self._sizeHolds = query.matches(*self._measure())
		if query.data is not None:
			self._dataHolds = False
			if (source := openValueSource(query.data, 'when', 'the condition counts as false')) is not None:
				self._binding = Binding(source, self._set)
		else:
			self._dataHolds = True
		self._holds = self._sizeHolds and self._dataHolds

	def _bind(self) -> None:
		spec = self._spec
		if spec is None or spec == '':
			self._set_quiet(True)
		elif isinstance(spec, (bool, int, float)):
			self._set_quiet(bool(spec))
		elif isinstance(spec, str):
			self._set_quiet(False)  # no value yet is false
			if self._panel.scene() is None:
				return
			if (source := openValueSource(spec, 'when', 'the condition counts as false')) is not None:
				self._binding = Binding(source, self._set)
		elif isSizeQuery(spec):
			self._set_quiet(False)
			try:
				self._query = SizeQuery.parse(spec)
			except ValueError as e:
				log.warning(f'{e}; the condition counts as false')
				self._onChange()
				return
			self._bindSize()
		else:
			log.warning(f'when {spec!r} must be a bool, a key, an expression or a size condition; the condition counts as false')
			self._set_quiet(False)
		self._onChange()

	def _set_quiet(self, holds: bool) -> None:
		self._holds = holds

	def _unbind(self) -> None:
		if self._sizeSource is not None:
			try:
				self._sizeSource.disconnect(self._sizeChanged)
			except (RuntimeError, TypeError):
				pass
			self._sizeSource = None
		self._query = None
		if self._binding is not None:
			self._binding.unlink()
			self._binding = None
