"""A state that is one value can be written as that value and read back, even when the value is text for a decoded type.

A graph's time indicator is `enabled` and a `color`; with only the colour set it saves as the bare colour
(`indicator: $text`). The loader used to accept a bare value only when it already was the property's own type, so a
colour written as text raised "Unable to set state".

Pure Python - no Qt, no LevityDash import required.
"""
from statekit import Stateful, StateProperty


class Swatch:
	def __init__(self, name: str):
		self.name = name


class Marker(Stateful, tag='marker'):
	@StateProperty(key='enabled', default=True, singleVal=True)
	def enabled(self) -> bool:
		return getattr(self, '_enabled', True)

	@enabled.setter
	def enabled(self, value: bool):
		self._enabled = value

	@StateProperty(key='color', singleVal=True)
	def color(self) -> Swatch:
		return getattr(self, '_color', Swatch('none'))

	@color.setter
	def color(self, value: Swatch):
		self._color = value

	@color.decode
	def color(self, value: str | dict) -> Swatch:
		return Swatch(value if isinstance(value, str) else value['name'])


def test_a_bare_value_of_the_decoders_input_type_reaches_its_property():
	marker = Marker()
	marker.state = '$text'
	assert marker.color.name == '$text'


def test_a_bare_value_of_the_property_type_still_does():
	marker = Marker()
	marker.state = False
	assert marker.enabled is False


def test_a_bare_value_no_property_takes_is_still_refused():
	import pytest
	with pytest.raises(TypeError):
		Marker().state = 3.5
