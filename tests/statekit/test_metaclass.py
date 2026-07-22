"""Characterization tests for StatefulMetaclass (statekit/core.py).

The metaclass rewrites class construction in ways that are impossible to
predict from reading a class definition alone: bases get reordered, state-item
precedence follows its own ChainMap assembly rather than the MRO, defaults
inherit from the *last* stateful parent, and ``__exclude__`` treats Ellipsis
as an inheritance marker. These tests pin that behavior down so the backend
split (docs/roadmap.md) can refactor around it without silently changing it.

Pure Python - no Qt, no LevityDash import required.
"""
import pytest

from statekit import Stateful, StateProperty, StatefulMixin


class HoistMixin(StatefulMixin):
	@StateProperty(default=1, key='hoist_key')
	def hoist_key(self) -> int:
		return getattr(self, '_hoist', 1)

	@hoist_key.setter
	def hoist_key(self, value):
		self._hoist = value


class ShadowMixin(StatefulMixin):
	@StateProperty(default='from-mixin', key='shadow_key')
	def shadow_key(self) -> str:
		return getattr(self, '_mixin', 'from-mixin')

	@shadow_key.setter
	def shadow_key(self, value):
		self._mixin = value


# --- StateProperty construction requires a class body -----------------------------

def test_state_property_requires_class_body():
	# StateProperty.__new__ inspects the *calling frame* and reads
	# frame.f_locals["__qualname__"] to learn its owner - which only exists
	# in the locals of a class body being executed. Constructing one at
	# function scope (without the undocumented `owner=` escape hatch) crashes.
	# Pinned as-is; the KeyError is unfriendly, but it is the current contract.
	def getter(self):
		return 1

	with pytest.raises(KeyError):
		StateProperty(default=1, key='nope')(getter)


# --- Base rewriting -----------------------------------------------------------

def test_mixins_hoisted_to_front_of_bases():
	# You write `class C(Stateful, M)`; the metaclass rebuilds the bases as
	# `(*mixins, *bases)` - the mixin is silently moved to the front of the
	# MRO no matter where it was written.
	class HoistedLast(Stateful, HoistMixin, tag='mtc-hoisted-last'):
		pass

	assert HoistedLast.__bases__[0] is HoistMixin
	assert HoistedLast.__bases__[-1] is Stateful


# --- __state_items__ precedence ------------------------------------------------

def test_mixin_state_items_shadow_own_properties():
	# The metaclass inserts each mixin's state-item map at the FRONT of the
	# ChainMap - in front of the class's own properties. For a colliding key,
	# __state_items__ resolves to the mixin's descriptor, not the class's own.
	class Shadowed(ShadowMixin, Stateful, tag='mtc-shadowed'):
		@StateProperty(default='from-class', key='shadow_key')
		def shadow_key(self) -> str:
			return getattr(self, '_own', 'from-class')

		@shadow_key.setter
		def shadow_key(self, value):
			self._own = value

	assert Shadowed.__state_items__['shadow_key'] is ShadowMixin.__dict__['shadow_key']


def test_multi_parent_state_items_prefer_first_parent():
	class FirstParent(Stateful, tag='mtc-first-parent'):
		@StateProperty(default='first', key='who')
		def who(self) -> str:
			return getattr(self, '_who', 'first')

		@who.setter
		def who(self, value):
			self._who = value

	class SecondParent(Stateful, tag='mtc-second-parent'):
		@StateProperty(default='second', key='who')
		def who(self) -> str:
			return getattr(self, '_who', 'second')

		@who.setter
		def who(self, value):
			self._who = value

	class DiamondChild(FirstParent, SecondParent, tag='mtc-diamond'):
		pass

	# State items chain as (own, FirstParent..., SecondParent...) - the
	# first-listed parent wins the key collision, matching MRO intuition...
	assert DiamondChild.__state_items__['who'] is FirstParent.__state_items__['who']


def test_multi_parent_defaults_inherit_from_last_parent():
	# ...but __defaults__ inherit from `parentCls`, which the metaclass sets
	# by iterating ALL stateful parents and keeping the last one. State-item
	# precedence and default inheritance point at OPPOSITE parents.
	class DefaultsA(Stateful, tag='mtc-defaults-a'):
		__defaults__ = {'shared': 'from-A'}

	class DefaultsB(Stateful, tag='mtc-defaults-b'):
		__defaults__ = {'shared': 'from-B'}

	class DefaultsChild(DefaultsA, DefaultsB, tag='mtc-defaults-child'):
		pass

	assert DefaultsChild.__defaults__['shared'] == 'from-B'


# --- __defaults__ dedup ---------------------------------------------------------

def test_defaults_equal_to_parent_are_deduped():
	# A child restating a parent default verbatim gets it dropped from its own
	# (front) map - the value is still reachable through the chain, but the
	# child's map only keeps genuinely different values.
	class DedupParent(Stateful, tag='mtc-dedup-parent'):
		__defaults__ = {'kept': 1, 'restated': 2}

	class DedupChild(DedupParent, tag='mtc-dedup-child'):
		__defaults__ = {'restated': 2, 'changed': 3}

	assert 'restated' not in DedupChild.__defaults__.maps[0]
	assert DedupChild.__defaults__['restated'] == 2
	assert DedupChild.__defaults__.maps[0]['changed'] == 3


# --- __exclude__ inheritance ------------------------------------------------------

def test_exclude_ellipsis_inherits_parent_excludes():
	# Ellipsis in __exclude__ is an inheritance marker: it is discarded and
	# the parents' excludes are unioned in.
	class ExcludeParent(Stateful, tag='mtc-exclude-parent'):
		__exclude__ = {'from_parent'}

	class ExcludeEllipsis(ExcludeParent, tag='mtc-exclude-ellipsis'):
		__exclude__ = {..., 'own'}

	assert ExcludeEllipsis.__exclude__ == {'from_parent', 'own'}


def test_exclude_explicit_replaces_inheritance():
	# Without Ellipsis (and non-empty), __exclude__ REPLACES the parent's set
	# entirely - inheritance is opt-in, inverted from how everything else on
	# the class behaves.
	class ExcludeParent2(Stateful, tag='mtc-exclude-parent2'):
		__exclude__ = {'from_parent'}

	class ExcludeExplicit(ExcludeParent2, tag='mtc-exclude-explicit'):
		__exclude__ = {'own_only'}

	assert ExcludeExplicit.__exclude__ == {'own_only'}


# --- generated per-class property subclass --------------------------------------

def test_per_class_state_property_subclass_generated():
	# Every Stateful SUBCLASS gets its own dynamically generated StateProperty
	# subclass named f'{name}StateProperty', chained off the parent class's -
	# but the root Stateful itself has none (the bootstrap branch skips it;
	# direct children chain off plain StateProperty via a getattr fallback).
	assert not hasattr(Stateful, '__statePropertyClass__')

	class PropOwner(Stateful, tag='mtc-prop-owner'):
		pass

	propCls = PropOwner.__statePropertyClass__
	assert propCls.__name__ == 'PropOwnerStateProperty'
	assert issubclass(propCls, StateProperty)
	assert propCls.__ownerClass__ is PropOwner

	class PropChild(PropOwner, tag='mtc-prop-child'):
		pass

	childPropCls = PropChild.__statePropertyClass__
	assert childPropCls.__name__ == 'PropChildStateProperty'
	assert issubclass(childPropCls, propCls)


# --- StatefulMixin abstract-method enforcement ------------------------------------

def test_mixin_subclass_concretizing_abstract_raises():
	# The "Invalid Usage" case from StatefulMixin's own docstring: a mixin
	# subclass that is NOT Stateful may not provide a concrete implementation
	# of a method that a parent mixin declared abstract - it must stay
	# abstract until mixed into a true Stateful class.
	from abc import abstractmethod

	class AbstractMixin(StatefulMixin):
		@abstractmethod
		def do_something(self):
			...

	with pytest.raises(TypeError):
		class ConcreteTooEarly(AbstractMixin):
			def do_something(self):
				return 'concrete'

	# The valid ending: concretizing while also becoming Stateful is fine.
	class ConcreteStateful(AbstractMixin, Stateful, tag='mtc-concrete-ok'):
		def do_something(self):
			return 'concrete'

	assert ConcreteStateful().do_something() == 'concrete'
