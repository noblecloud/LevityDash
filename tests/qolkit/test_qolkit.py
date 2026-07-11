"""Pure-Python tests for qolkit - no Qt, no LevityDash import required."""
import pytest

from qolkit import (
	classproperty, clearCacheAttr, DeepChainMap, DotDict, get, guarded_cached_property, IgnoreOr, Index, Infix,
	OrderedSet, OrUnset, recursiveRemove, remove_empty_dicts, sortDict, Unset, UnsetKwarg,
)


# --- sentinels ---

def test_unset_is_falsy_and_singleton():
	assert not Unset
	assert Unset is Unset
	assert Unset != UnsetKwarg
	assert isinstance(Unset, Unset)


def test_or_unset_infix_prefers_non_sentinel():
	# Unset on the left short-circuits via IgnoreOr's own __or__ (it always
	# returns whatever it's OR'd with) before OrUnset's function ever runs -
	# so only "real_value |OrUnset| Unset" exercises _or() itself.
	assert (5 |OrUnset| Unset) == 5
	assert (3 |OrUnset| 7) == 3


def test_infix_basic_call():
	add = Infix(lambda a, b: a + b)
	assert (2 |add| 3) == 5
	assert add(2, 3) == 5


# --- mappings ---

def test_dotdict_dotted_key_access():
	# Dotted traversal only works through nesting DotDict itself builds via
	# __setitem__ (it creates child DotDicts) - a plain nested-dict literal
	# passed to __init__ is stored as-is, not recursively converted. Kept to
	# 2 levels: 3+ levels hits a separate, pre-existing bug in DotDict.key
	# (confirmed present on unmodified pre-extraction code too, out of
	# scope here) where an ancestor's own .key returns a tuple instead of a
	# string once there's a grandparent link.
	d = DotDict()
	d['a.b'] = 1
	assert d['a.b'] == 1
	assert 'a.b' in d
	assert 'a.z' not in d


def test_dotdict_dotted_key_set_creates_nesting():
	d = DotDict()
	d['x.y'] = 1
	assert d['x']['y'] == 1


def test_dotdict_get_default():
	d = DotDict({'a': 1})
	assert d.get('missing', 'fallback') == 'fallback'
	with pytest.raises(KeyError):
		d.get('missing')


def test_get_single_value():
	assert get({'a': 1}, 'a') == 1


def test_get_multiple_keys_first_match_wins():
	assert get({'b': 2}, 'a', 'b', default=None) == 2


def test_get_raises_only_when_default_is_explicitly_unset():
	# With no default given at all, get() hands back the UnsetKwarg
	# sentinel (its own parameter default) rather than raising - you must
	# opt in to the raising behavior with default=Unset.
	assert get({}, 'missing') is UnsetKwarg
	with pytest.raises(KeyError):
		get({}, 'missing', default=Unset)


def test_get_returns_default_when_missing():
	assert get({}, 'missing', default='fallback') == 'fallback'


def test_sortdict_orders_by_key():
	d = sortDict({'b': 2, 'a': 1, 'c': 3})
	assert list(d.keys()) == ['a', 'b', 'c']


def test_recursive_remove_strips_matching_nested_values():
	existing = {'a': 1, 'b': {'c': 2, 'd': 3}}
	subtracting = {'b': {'c': 2}}
	result = recursiveRemove(existing, subtracting)
	assert result == {'a': 1, 'b': {'d': 3}}


def test_remove_empty_dicts_strips_empties():
	assert remove_empty_dicts({'a': {}, 'b': 1, 'c': {'d': {}}}) == {'b': 1, 'c': {}}


def test_deepchainmap_child_overrides_parent():
	parent = DeepChainMap(origin_map={'a': 1, 'b': 2})
	child = parent.new_child(child_map={'b': 3})
	assert child['a'] == 1
	assert child['b'] == 3


def test_deepchainmap_nested_mapping_values_flatten_via_to_dict():
	parent = DeepChainMap(origin_map={'nested': {'x': 1}})
	child = parent.new_child(child_map={'nested': {'y': 2}})
	# accessing 'nested' returns a DeepChainMap wrapping both layers
	nested = child['nested']
	assert isinstance(nested, DeepChainMap)
	# to_dict() must recursively flatten it to a plain dict, not leak the
	# DeepChainMap object itself (this exact leak corrupted saved YAML once)
	flat = child.to_dict()
	assert flat == {'nested': {'x': 1, 'y': 2}}
	assert not isinstance(flat['nested'], DeepChainMap)


def test_deepchainmap_to_dict_flattens_deeply_nested_chainmaps():
	inner = DeepChainMap(origin_map={'a': {'b': {'c': 1}}})
	inner_child = inner.new_child(child_map={'a': {'b': {'d': 2}}})
	flat = inner_child.to_dict()
	assert flat == {'a': {'b': {'c': 1, 'd': 2}}}
	for v in flat.values():
		assert not isinstance(v, DeepChainMap)


# --- collections ---

def test_orderedset_add_inserts_at_iteration_start():
	# add()'s default (at_beginning=False) inserts right after the `end`
	# sentinel, which is where __iter__ starts - so each new item becomes
	# the *first* one yielded, most-recently-added-first, not appended.
	s = OrderedSet([3, 1, 2])
	assert list(s) == [2, 1, 3]
	s.add(4)
	assert list(s) == [4, 2, 1, 3]


def test_orderedset_discard_and_contains():
	s = OrderedSet([1, 2, 3])
	assert list(s) == [3, 2, 1]
	s.discard(2)
	assert 2 not in s
	assert list(s) == [3, 1]


def test_orderedset_add_at_beginning_inserts_at_iteration_end():
	# at_beginning=True inserts right before `end` (the ring's other side),
	# which __iter__ yields *last* - the flag name refers to the ring
	# position relative to `end`, not the resulting iteration order.
	s = OrderedSet([1, 2])
	s.add(0, at_beginning=True)
	assert list(s) == [2, 1, 0]


def test_index_links_form_a_ring():
	idx = Index('a')
	assert idx.previous is idx
	assert idx.next is idx


# --- descriptors ---

def test_classproperty_reads_from_class_not_instance():
	class Foo:
		@classproperty
		def bar(cls):
			return cls.__name__

	assert Foo.bar == 'Foo'
	assert Foo().bar == 'Foo'


def test_clear_cache_attr_removes_dict_entries():
	class Obj:
		pass

	o = Obj()
	o.__dict__['cached'] = 123
	clearCacheAttr(o, 'cached')
	assert 'cached' not in o.__dict__
	# missing attrs are silently ignored, not an error
	clearCacheAttr(o, 'never_set')


def test_guarded_cached_property_falls_back_when_guard_fails():
	# The default-callable branch is meant to support a callable that takes
	# `self`, gated by `'self' in get_args(defaultFunc)` - but get_args() is
	# for inspecting generic type parameters, not function signatures, so
	# it's always empty for a plain function and that branch never fires;
	# self.default() (zero args) is what actually always runs.
	class Obj:
		@guarded_cached_property(guardFunc=lambda v: v is not None, default=lambda: 'fallback')
		def value(self):
			return None

	o = Obj()
	assert o.value == 'fallback'


def test_guarded_cached_property_returns_value_when_guard_passes():
	class Obj:
		@guarded_cached_property(guardFunc=lambda v: v is not None, default='fallback')
		def value(self):
			return 'real'

	o = Obj()
	assert o.value == 'real'
