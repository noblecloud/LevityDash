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


def test_a_declared_body_is_ignored_when_inheritFrom_is_given():
	"""Characterization, NOT an endorsement - and pre-existing, not from the
	fix above (verified by running this against both revisions).

	Writing a real body *and* passing `inheritFrom=` silently runs the
	inherited getter and discards the body. Nothing in LevityDash does this
	today - both live uses of `inheritFrom` have empty bodies - so this is
	pinned rather than fixed, because changing getter-resolution priority is a
	much broader change than the one this file exists to cover.
	"""
	class Overrides(Base, tag='overrides'):
		@StateProperty(key='label', inheritFrom=Base.label)
		def label(self) -> str:
			return 'own'

	assert Overrides().label == 'Overrides-label'  # the body is not called
