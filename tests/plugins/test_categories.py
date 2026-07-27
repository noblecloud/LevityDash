"""Regression test for CategoryDict.__getitem__'s wildcard-matching fallback
(lib/plugins/categories.py, `if len(item) == 1: ...` branch).

That branch references `TimeAwareValue` (lib/plugins/observation.py) but the
name was never imported anywhere in categories.py, so any code path reaching
it raised `NameError: name 'TimeAwareValue' is not defined` instead of doing
its wildcard-match/lookup.

Found while writing golden-fixture tests for OpenMeteo's schema
(docs/tasks/schema-golden-fixture-tests.md): a real `Schema` instance's
`aliases` are popped out into a plain attribute during construction
(`Schema.__init__`, `self.aliases = source.pop('aliases', {})`), so
dict-style access (`schema['aliases']`) - as opposed to the correct
`schema.aliases` - can't find it via the normal `_source`/`_dict` paths and
falls through to this exact branch, which is the most realistic way to
reach it without hand-constructing `CategoryDict`'s internal caching state
from scratch.
"""
import copy

from LevityDash.lib.plugins.categories import CategoryItem
from LevityDash.lib.plugins.builtin.OpenMeteo import schema as raw_schema
from LevityDash.lib.plugins.schema import Schema


class FakePlugin:
	name = 'OpenMeteo'

	def __hash__(self):
		return hash(self.name)

	def __contains__(self, item):
		return False


def test_getitem_wildcard_fallback_does_not_raise_nameerror():
	# Regression guard: this used to raise NameError unconditionally (the
	# name lookup fails before any isinstance check can even run), regardless
	# of what's actually in the dict being searched.
	schema = Schema(plugin=FakePlugin(), source=copy.deepcopy(raw_schema))
	result = schema['aliases']  # not schema.aliases - see module docstring
	assert isinstance(result, dict)


# --- #identity --------------------------------------------------------------
# `identity` names *which* value a key refers to (bedroom vs terrarium sensor).
# It is the opposite of `source` in intent: several sources for one key are
# reconciled into a single value, whereas two identities are never merged.
# See docs/tasks/govee-multi-device.md.

class TestIdentity:

	def test_parsed_from_string_form_and_not_absorbed_as_an_atom(self):
		key = CategoryItem('indoor.temperature.temperature#bedroom')
		assert key.identity == 'bedroom'
		assert key.hasIdentity
		# '#' is outside the atom character class, so a naive parse would drop
		# the separator and leave 'bedroom' as a fourth path segment.
		assert tuple(str(a) for a in key) == ('indoor', 'temperature', 'temperature')

	def test_round_trips_through_str(self):
		key = CategoryItem('indoor.temperature.temperature#bedroom')
		assert str(key) == 'indoor.temperature.temperature#bedroom'
		assert CategoryItem(str(key)) == key
		assert CategoryItem(str(key)).identity == 'bedroom'

	def test_different_identities_are_different_keys(self):
		bedroom = CategoryItem('indoor.temperature.temperature#bedroom')
		terrarium = CategoryItem('indoor.temperature.temperature#terrarium')
		assert bedroom != terrarium
		assert hash(bedroom) != hash(terrarium)
		# CategoryItem interns instances in __existing__; if identity were left
		# out of that cache key, these would be the *same object*.
		assert bedroom is not terrarium

	def test_unqualified_key_is_not_a_stand_in_for_a_qualified_one(self):
		assert CategoryItem('indoor.temperature.temperature') != CategoryItem('indoor.temperature.temperature#bedroom')

	def test_all_three_survive_as_distinct_dict_keys(self):
		keys = {
			CategoryItem('indoor.temperature.temperature'): 'any',
			CategoryItem('indoor.temperature.temperature#bedroom'): 'bed',
			CategoryItem('indoor.temperature.temperature#terrarium'): 'ter',
		}
		assert len(keys) == 3
		assert keys[CategoryItem('indoor.temperature.temperature#bedroom')] == 'bed'

	def test_with_and_without_identity(self):
		bare = CategoryItem('indoor.temperature.temperature')
		scoped = bare.withIdentity('garage')
		assert str(scoped) == 'indoor.temperature.temperature#garage'
		assert scoped.withoutIdentity == bare
		assert bare.withoutIdentity is bare

	def test_identity_survives_a_rebuild(self):
		# anonymous() and replaceVar() reconstruct the key; both must carry
		# identity through rather than silently dropping it.
		key = CategoryItem('indoor.temperature.temperature#bedroom', source=['Govee'])
		assert key.anonymous.identity == 'bedroom'
		assert CategoryItem('indoor.@deviceName.battery#bedroom').replaceVar(**{'@deviceName': 'x'}).identity == 'bedroom'

	def test_keys_without_identity_are_unaffected(self):
		key = CategoryItem('environment.temperature.temperature')
		assert key.identity is None
		assert not key.hasIdentity
		assert str(key) == 'environment.temperature.temperature'


class TestInequalityMirrorsEquality:
	"""`!=` used to bypass __eq__ entirely.

	CategoryItem subclasses tuple, and tuple supplies its own __ne__. Python
	only auto-derives __ne__ from __eq__ when the base class doesn't provide
	one, so overriding __eq__ alone left `!=` doing an element-wise tuple
	comparison - ignoring both source and identity. `a == b` and `a != b`
	could both be False at once.
	"""

	def test_differing_identity(self):
		a = CategoryItem('a.b#bedroom')
		b = CategoryItem('a.b#terrarium')
		assert (a == b) is False
		assert (a != b) is True

	def test_differing_source(self):
		# Predates identity - the same hole applied to sourced keys.
		a = CategoryItem('a.b', source=['Govee'])
		b = CategoryItem('a.b', source=['WeatherFlow'])
		assert (a == b) is False
		assert (a != b) is True

	def test_equal_keys_still_compare_equal(self):
		a = CategoryItem('a.b.c')
		b = CategoryItem('a.b.c')
		assert (a == b) is True
		assert (a != b) is False
