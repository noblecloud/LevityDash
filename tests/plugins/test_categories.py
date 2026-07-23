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
