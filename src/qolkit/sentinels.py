"""Sentinel values and the infix-operator helper used to build them.

Pure Python, no dependencies beyond the stdlib.
"""


class IgnoreOr(object):

	def __init__(self, name: str):
		self.__name__ = name

	def copy(self):
		return self

	def __copy__(self):
		return self

	def __repr__(self):
		return f'<{self.__name__}>'

	def __or__(self, other):
		return other

	def __ror__(self, other):
		return other

	def __bool__(self):
		return False

	def __neg__(self):
		return self

	def __invert__(self):
		return self

	def __eq__(self, other):
		return self is other

	def __ne__(self, other):
		return self is not other

	def __hash__(self):
		return hash((self.__name__, type(self)))

	def __instancecheck__(self, instance):
		return self is instance

	def get(self, *args, **kwargs):
		return self


Unset = IgnoreOr('Unset')
UnsetKwarg = IgnoreOr('UnsetKwarg')


class Infix:
	def __init__(self, function):
		self.function = function

	def __ror__(self, other):
		return Infix(lambda x, self=self, other=other: self.function(other, x))

	def __or__(self, other):
		return self.function(other)

	def __rlshift__(self, other):
		return Infix(lambda x, self=self, other=other: self.function(other, x))

	def __rshift__(self, other):
		return self.function(other)

	def __call__(self, value1, value2):
		return self.function(value1, value2)

	def __rmatmul__(self, other):
		return Infix(lambda x, self=self, other=other: self.function(other, x))

	def __matmul__(self, other):
		return self.function(other)


def _or(a, b):
	if isinstance(a, IgnoreOr):
		return b
	elif isinstance(b, IgnoreOr):
		return a
	return a


OrUnset = Infix(_or)
