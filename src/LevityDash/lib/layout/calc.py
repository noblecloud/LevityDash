"""CSS math functions for lengths: `calc()`, `min()`, `max()` and `clamp()`.

Spec: https://www.w3.org/TR/css-values-4/ section 10 (Mathematical Expressions).

Pure functions. No Qt. A length is resolved to pixels by the caller's `to_px(number, unit)`,
which is also where `%` gets its base. The result is pixels.

Rules from §10.1 and §10.2 that are kept:
- `+` and `-` need white space on both sides, so `1px -2px` is an error and `1px - 2px` is not.
- Both sides of `+` and `-` are lengths, or both are numbers.
- `*` needs at least one number side. `/` needs a number on the right, and never zero.
- A bare `(...)` groups, like `calc(...)`.
- `min()`, `max()` and `clamp(min, value, max)` take expressions of one kind. `clamp` is
  `max(min, min(value, max))`.
Not kept: a length times a length (`px` squared), and numbers on their own as a result.
"""

import re
from typing import Callable, NamedTuple

from .spec import implements

__all__ = ['is_math', 'evaluate_math', 'split_values']

_FUNCTIONS = ('calc', 'min', 'max', 'clamp')
_TOKEN = re.compile(r'\s*(?:(?P<num>\d*\.?\d+(?:[eE][-+]?\d+)?)(?P<unit>[a-zA-Z%]*)|(?P<op>[-+*/(),])|(?P<name>[a-zA-Z]+)(?=\())')


class _Value(NamedTuple):
	amount: float
	length: bool  # a length in pixels, or a plain number


def is_math(text) -> bool:
	"""True for a string that starts a math function: `calc(...)`, `min(...)`, `max(...)`, `clamp(...)`."""
	return isinstance(text, str) and re.match(r'\s*(calc|min|max|clamp)\(', text) is not None


def split_values(text: str) -> list[str]:
	"""Split a space or comma separated list at the top level, so `calc(1px + 2px) auto` is two values."""
	parts, buf, depth = [], '', 0
	for ch in text:
		depth += (ch == '(') - (ch == ')')
		if depth == 0 and (ch.isspace() or ch == ','):
			if buf:
				parts.append(buf)
			buf = ''
		else:
			buf += ch
	if depth:
		raise ValueError(f'unbalanced "(" in {text!r}')
	if buf:
		parts.append(buf)
	return parts


def _tokens(text: str) -> list[tuple[str, object, bool]]:
	"""`(kind, value, spaced)` where `spaced` is whether white space came before the token."""
	found, at = [], 0
	while at < len(text):
		if text[at:].strip() == '':
			break
		match = _TOKEN.match(text, at)
		if not match:
			raise ValueError(f'math: cannot read {text[at:].strip()[:20]!r} in {text!r}')
		spaced = text[at] .isspace()
		if match['num'] is not None:
			found.append(('num', (float(match['num']), match['unit'].lower()), spaced))
		elif match['op'] is not None:
			found.append(('op', match['op'], spaced))
		else:
			found.append(('name', match['name'].lower(), spaced))
		at = match.end()
	return found


class _Parser:
	def __init__(self, text: str, to_px: Callable[[float, str], float]):
		self.text, self.to_px = text, to_px
		self.tokens, self.at = _tokens(text), 0

	def peek(self):
		return self.tokens[self.at] if self.at < len(self.tokens) else (None, None, False)

	def take(self):
		token = self.peek()
		self.at += 1
		return token

	def expect(self, op: str):
		kind, value, _ = self.take()
		if kind != 'op' or value != op:
			raise ValueError(f'math: expected {op!r} in {self.text!r}')

	def parse(self) -> _Value:
		value = self.sum()
		if self.at != len(self.tokens):
			raise ValueError(f'math: unexpected {self.peek()[1]!r} in {self.text!r}')
		return value

	def sum(self) -> _Value:
		left = self.product()
		while True:
			kind, value, spaced = self.peek()
			if kind == 'op' and value in '+-':
				after = self.tokens[self.at + 1] if self.at + 1 < len(self.tokens) else None
				if not spaced or after is None or not after[2]:
					raise ValueError(f'math: {value!r} needs white space on both sides in {self.text!r}')
				self.take()
				right = self.product()
				if left.length != right.length:
					raise ValueError(f'math: cannot {"add" if value == "+" else "subtract"} a length and a number in {self.text!r}')
				left = _Value(left.amount + right.amount if value == '+' else left.amount - right.amount, left.length)
			else:
				return left

	def product(self) -> _Value:
		left = self.unary()
		while True:
			kind, value, _ = self.peek()
			if kind == 'op' and value in '*/':
				self.take()
				right = self.unary()
				if value == '*':
					if left.length and right.length:
						raise ValueError(f'math: a length times a length in {self.text!r}')
					left = _Value(left.amount * right.amount, left.length or right.length)
				else:
					if right.length:
						raise ValueError(f'math: cannot divide by a length in {self.text!r}')
					if right.amount == 0:
						raise ValueError(f'math: division by zero in {self.text!r}')
					left = _Value(left.amount / right.amount, left.length)
			else:
				return left

	def unary(self) -> _Value:
		kind, value, _ = self.peek()
		if kind == 'op' and value in '+-' and self.at + 1 < len(self.tokens) and not self.tokens[self.at + 1][2]:
			self.take()
			inner = self.unary()
			return _Value(inner.amount if value == '+' else -inner.amount, inner.length)
		return self.atom()

	def atom(self) -> _Value:
		kind, value, _ = self.take()
		if kind == 'num':
			number, unit = value
			return _Value(number, False) if unit == '' else _Value(float(self.to_px(number, unit)), True)
		if kind == 'op' and value == '(':
			inner = self.sum()
			self.expect(')')
			return inner
		if kind == 'name':
			if value not in _FUNCTIONS:
				raise ValueError(f'math: {value!r} is not a math function in {self.text!r}')
			self.expect('(')
			args = [self.sum()]
			while self.peek()[:2] == ('op', ','):
				self.take()
				args.append(self.sum())
			self.expect(')')
			return self.apply(value, args)
		raise ValueError(f'math: unexpected end of {self.text!r}' if kind is None else f'math: unexpected {value!r} in {self.text!r}')

	def apply(self, name: str, args: list[_Value]) -> _Value:
		if name == 'calc':
			if len(args) != 1:
				raise ValueError(f'math: calc() takes one expression in {self.text!r}')
			return args[0]
		if len({a.length for a in args}) != 1:
			raise ValueError(f'math: {name}() mixes lengths and numbers in {self.text!r}')
		kind = args[0].length
		amounts = [a.amount for a in args]
		if name == 'clamp':
			if len(args) != 3:
				raise ValueError(f'math: clamp() takes three values in {self.text!r}')
			low, mid, high = amounts
			return _Value(max(low, min(mid, high)), kind)
		return _Value(min(amounts) if name == 'min' else max(amounts), kind)


@implements('css-values-4', 'Mathematical Expressions', '10', status='done')
def evaluate_math(text: str, to_px: Callable[[float, str], float]) -> float:
	"""A math function such as `calc(100% - 2 * 12px)` as pixels.

	`to_px(number, unit)` gives the pixels of one dimension, `%` included. Raises `ValueError`
	naming the problem when the text breaks a rule in the module note, or when the result is a
	plain number and not a length.
	"""
	result = _Parser(text, to_px).parse()
	if not result.length:
		raise ValueError(f'math: {text!r} is a number, not a length')
	return result.amount
