"""Unknown StateProperty options must not be silently accepted.

`StateProperty(**kwargs)` stores every keyword into an options dict, and each
feature reads the key it cares about. A key nobody reads is therefore a
no-op - so a typo doesn't fail, it just quietly disables the behaviour it was
meant to configure.

That is not hypothetical: `dependancies=` (one letter off) appeared in 21
declarations across LevityDash - all of Gauge's, plus Panel, Realtime and
Stacks - and disabled state-ordering everywhere it appeared. Nothing said so.
"""
import pytest

from statekit.core import StateProperty, Stateful


def test_a_misspelled_option_is_rejected():
	with pytest.raises(TypeError, match='dependancies'):
		class Broken(Stateful):
			@StateProperty(dependancies={'other'})
			def value(self): return 1


def test_the_error_names_the_known_options():
	with pytest.raises(TypeError, match='dependencies'):
		class Broken(Stateful):
			@StateProperty(nonsenseOption=True)
			def value(self): return 1


def test_real_options_still_work():
	class Fine(Stateful):
		@StateProperty(key='v', dependencies={'other'}, allowNone=False, repr=True)
		def value(self): return 1

	assert Fine is not None


def test_declared_but_unimplemented_options_are_allowed():
	"""`singleForceCondition` is unread but intentional - statekit carries a
	TODO for it. Intent is not a typo; the guard must not delete it."""
	class Fine(Stateful):
		@StateProperty(singleVal=True, singleForceCondition=lambda v: not v)
		def value(self): return 1

	assert Fine is not None
