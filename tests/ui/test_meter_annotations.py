"""Every StateProperty in the meter package must be able to resolve its annotations.

Not a style rule. `StateProperty.returns` calls `typing.get_type_hints` on the
property's getter and factory at runtime (the `returns` cached property in
statekit/core.py) to answer "what type does this hold". A quoted annotation like
`-> 'GaugeTickTextGroup'` is resolved against the module the function was
*defined* in, so when a class moves to another module, every annotation still
naming a class left behind turns into a NameError at first use - and it surfaces
as the property's own failure, nowhere near the move.

Moving `Graduations` into meter/elements.py did exactly this: its `labels`
annotation still named `GaugeTickTextGroup`, which was still in Gauge.py, so the
gauge would not build at all. This test is the guard for the rest of the split.
"""
import importlib
import typing

from LevityDash.lib.stateful import StateProperty

MODULES = (
	'LevityDash.lib.ui.frontends.PySide.Modules.Displays.meter.scale',
	'LevityDash.lib.ui.frontends.PySide.Modules.Displays.meter.track',
	'LevityDash.lib.ui.frontends.PySide.Modules.Displays.meter.elements',
	'LevityDash.lib.ui.frontends.PySide.Modules.Displays.meter.meter',
)

PROPERTY_TYPES = (StateProperty,)


def _classes(module):
	"""Classes defined in this module (not imported ones)."""
	for name, obj in vars(module).items():
		if isinstance(obj, type) and getattr(obj, '__module__', None) == module.__name__:
			yield f'{name}', obj


def _state_properties(cls):
	for klass in cls.__mro__:
		for name, attr in vars(klass).items():
			if isinstance(attr, PROPERTY_TYPES):
				yield name, attr


def test_every_state_property_resolves_its_returns():
	problems = []
	for module_name in MODULES:
		module = importlib.import_module(module_name)
		for cls_name, cls in _classes(module):
			for prop_name, prop in _state_properties(cls):
				try:
					prop.returns
				except NameError as e:
					problems.append(f'{cls_name}.{prop_name}: {e}')
	assert not problems, (
		'a StateProperty cannot resolve the annotations the state layer reads at runtime '
		'(a moved class whose annotation still names something left behind?):\n  ' + '\n  '.join(problems)
	)


def test_every_class_annotation_resolves():
	"""`Text.surface` calls `get_type_hints(type(self))` at layout time.

	So a *class-level* annotation that names something its module cannot see is a
	NameError in the middle of laying a label out - which is exactly how
	`GaugeUnit.surface: Gauge` failed when GaugeUnit moved. The display classes are
	handed to meter/elements.py at the foot of Gauge.py for this reason.
	"""
	problems = []
	for module_name in MODULES:
		module = importlib.import_module(module_name)
		for cls_name, cls in _classes(module):
			try:
				typing.get_type_hints(cls)
			except NameError as e:
				problems.append(f'{cls_name}: {e}')
	assert not problems, 'a class annotation cannot be resolved by its own module:\n  ' + '\n  '.join(problems)


def test_the_walk_finds_the_properties_it_is_supposed_to():
	"""A guard on the guard: if the walk finds nothing, the test above proves nothing."""
	module = importlib.import_module('LevityDash.lib.ui.frontends.PySide.Modules.Displays.meter.elements')
	found = [
		(cls_name, attr_name, prop.key)
		for cls_name, cls in _classes(module) for attr_name, prop in _state_properties(cls)
	]
	assert len(found) > 40, f'only found {len(found)} state properties: {found}'
	assert any(cls_name == 'Graduations' for cls_name, _, _ in found), 'the moved classes are not being walked'
