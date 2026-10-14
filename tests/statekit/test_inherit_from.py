"""`inheritFrom=` must actually supply the inherited getter/setter.

Regression: the option was consulted only in `StateProperty.__new__`, to pick
which class the property object itself was built from. It never reached
getter/setter resolution, so a property declared with an empty body plus
`inheritFrom=` inherited nothing, `fget` came back None, and every read raised
`AttributeError("unreadable attribute")`.

The inference path cannot cover this case on its own: `ownerParentClass`
(introspect.py) deliberately skips a base literally spelled `Stateful` and falls
back to `object`, so a *direct* subclass of Stateful can never inherit a
Stateful-declared getter by inference.

Consequences in LevityDash: `StackedItem.type`
(Modules/Containers/Stacks.py) is declared exactly this way. Every stacked panel
raised on `.type`, which meant the key was silently omitted from the panel's
serialized state - so saving a dashboard dropped `type:` from every stacked
item and they reloaded as the stack's default type.

Pure Python - no Qt, no LevityDash import required.
"""
from statekit import Stateful, StateProperty


class Base(Stateful, tag='base'):
	@StateProperty(key='label')
	def label(self) -> str:
		return f'{type(self).__name__}-label'


class InheritsWithEmptyBody(Base, tag='inherits'):
	@StateProperty(key='label', inheritFrom=Base.label)
	def label(self) -> str:
		pass


class DirectStatefulSubclass(Stateful, tag='direct'):
	"""The shape that broke: the only base is literally named `Stateful`."""

	@StateProperty(key='type', inheritFrom=Stateful.type)
	def type(self) -> str:
		pass


def test_empty_body_inherits_the_getter():
	assert InheritsWithEmptyBody().label == 'InheritsWithEmptyBody-label'


def test_direct_stateful_subclass_inherits_type():
	# Reading this raised AttributeError('unreadable attribute') before the fix.
	assert DirectStatefulSubclass().type == 'direct'


def test_inherited_property_has_a_resolvable_getter():
	assert DirectStatefulSubclass.__dict__['type'].fget is not None
	assert InheritsWithEmptyBody.__dict__['label'].fget is not None


def test_inherited_key_reaches_serialized_state():
	"""The practical consequence: an unreadable property vanishes from state."""
	assert DirectStatefulSubclass().state.get('type') == 'direct'


def test_a_declared_body_wins_over_inheritFrom():
	"""A non-empty body is the getter; `inheritFrom=` only supplies one when the
	body is empty (`StateProperty.fget` falls back to `parentCls` on a PASS body).

	This used to be pinned as "the body is silently ignored". That was never the
	code's behaviour at the commit that added this file, so the pin was wrong.
	"""
	class Overrides(Base, tag='overrides'):
		@StateProperty(key='label', inheritFrom=Base.label)
		def label(self) -> str:
			return 'own'

	assert Overrides().label == 'own'
