"""A condition on a panel: `when:` takes a key, an expression, or a plain bool.

`PanelCondition` is the value-source half of `when:`. It holds no widgets, so
`Panel` can own one without an import cycle. A missing value counts as false, a
bad expression logs once and counts as false, and nothing here raises.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Optional

from LevityDash.lib.log import LevityPluginLog
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

	@property
	def spec(self) -> Any:
		return self._spec

	@spec.setter
	def spec(self, value: Any):
		if value == self._spec and (self._binding is not None or not isinstance(value, str)):
			return
		self._unbind()
		self._spec = value
		self._bind()

	@property
	def holds(self) -> bool:
		return self._holds

	def attach(self) -> None:
		"""The panel entered a scene: open the source if one is wanted and not yet open."""
		if self._binding is None and isinstance(self._spec, str):
			self._bind()

	def detach(self) -> None:
		"""The panel left its scene: release the source."""
		self._unbind()

	def _set(self, value: Any) -> None:
		holds = _truthy(value)
		if holds != self._holds:
			self._holds = holds
			self._onChange()

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
		else:
			log.warning(f'when {spec!r} must be a bool, a key or an expression; the condition counts as false')
			self._set_quiet(False)
		self._onChange()

	def _set_quiet(self, holds: bool) -> None:
		self._holds = holds

	def _unbind(self) -> None:
		if self._binding is not None:
			self._binding.unlink()
			self._binding = None
