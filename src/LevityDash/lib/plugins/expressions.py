"""Value-source expressions: the parser and evaluator behind computed keys.

A value source in a ``.levity`` file is a key, a number, or an expression
over keys (see docs/tasks/value-sources.md). This module is the part that
needs neither Qt nor the wire: it parses an expression, says which inputs it
reads, gives it a stable computed key, and evaluates it against whatever
supplies those inputs (a ``Resolver``).

Parsing uses ``ast`` and checks every node against an allowlist. Nothing is
ever passed to ``eval``. Two kinds of token are not valid Python, so a
pre-pass swaps them for placeholder names before ``ast`` sees the text:

- keys, including the ``source:`` and ``#identity`` affixes (``#`` would
  otherwise start a comment)
- durations such as ``24h`` or ``3h``

Rules for missing data: an input with no value yet makes the result
``Missing``, never an exception and never ``0``. A conditional only evaluates
the branch it takes, so the other branch may be missing. Errors in the
expression itself (bad syntax, unknown function) raise ``ExpressionError``
at parse time; errors that depend on the values (a bare number added to a
measurement) raise it at evaluation time.
"""
import ast
import hashlib
import operator
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, FrozenSet, Mapping, Optional, Protocol, Sequence, Tuple

import WeatherUnits as wu

from LevityDash.lib.plugins.categories import CategoryItem

__all__ = [
	'Expression', 'ExpressionError', 'Missing', 'Window', 'SeriesInput', 'PointInput', 'Resolver',
	'COMPUTED_ROOT',
]

#: The first atom of every computed key, e.g. ``computed.x3f9a0c21b7de``.
COMPUTED_ROOT = 'computed'


class ExpressionError(ValueError):
	"""The expression is malformed, or asks for something not allowed."""


class _MissingType:
	__slots__ = ()
	_instance = None

	def __new__(cls):
		if cls._instance is None:
			cls._instance = super().__new__(cls)
		return cls._instance

	def __repr__(self):
		return 'Missing'

	def __bool__(self):
		return False

	def __reduce__(self):
		return (_MissingType, ())


#: The result of an expression whose inputs are not all present yet.
Missing = _MissingType()


@dataclass(frozen=True)
class Window:
	"""A span of time that a window function reads.

	``span=None`` is ``today``: local midnight to the next local midnight,
	so it covers observed and forecast points for the day. A duration covers
	the past, ending now: ``24h`` is the last 24 hours.
	"""
	span: Optional[timedelta] = None

	def bounds(self, now: datetime) -> Tuple[datetime, datetime]:
		if self.span is None:
			start = now.replace(hour=0, minute=0, second=0, microsecond=0)
			# Overshoot by a few hours and snap back, so the end is the next
			# calendar midnight rather than exactly 24 hours later.
			end = (start + timedelta(days=1, hours=3)).replace(hour=0)
			return start, end
		return now - abs(self.span), now

	def __str__(self):
		if self.span is None:
			return 'today'
		return _formatDuration(self.span)


@dataclass(frozen=True)
class SeriesInput:
	"""A key read over a window, for ``min``/``max``/``avg``."""
	key: CategoryItem
	window: Window


@dataclass(frozen=True)
class PointInput:
	"""A key read at one moment relative to now, for ``at``."""
	key: CategoryItem
	offset: timedelta


class Resolver(Protocol):
	"""Supplies an expression's inputs. Every method returns ``None`` when it
	has no value, which the evaluator turns into ``Missing``."""

	def current(self, key: CategoryItem) -> Any:
		...

	def series(self, key: CategoryItem, start: datetime, end: datetime) -> Optional[Sequence[Tuple[datetime, Any]]]:
		...

	def at(self, key: CategoryItem, when: datetime) -> Any:
		...


# -- tokens that are not valid Python -----------------------------------------

_KEY_PATTERN = re.compile(
	r'(?<![\w.])'
	r'(?:[A-Za-z][\w-]*:)?'          # source: affix
	r'[A-Za-z_]\w*(?:\.\w+)+'        # dotted path, at least two atoms
	r'(?:#\w+)?'                     # #identity affix
)
_DURATION_PATTERN = re.compile(r'(?<![\w.])(\d+(?:\.\d+)?)(ms|s|m|h|d|w)\b')
_DURATION_UNITS = {
	'ms': timedelta(milliseconds=1),
	's':  timedelta(seconds=1),
	'm':  timedelta(minutes=1),
	'h':  timedelta(hours=1),
	'd':  timedelta(days=1),
	'w':  timedelta(weeks=1),
}

_KEY_PREFIX = '__key'
_DURATION_PREFIX = '__duration'

#: Names an expression may use besides keys.
_TODAY = 'today'
_VALUE = 'value'
_RESERVED_NAMES = frozenset({_TODAY, _VALUE})

_WINDOW_FUNCTIONS = frozenset({'min', 'max', 'avg'})
_FUNCTIONS = frozenset({'min', 'max', 'avg', 'at', 'abs'})

_BINARY_OPERATORS: Dict[type, Callable] = {
	ast.Add:  operator.add,
	ast.Sub:  operator.sub,
	ast.Mult: operator.mul,
	ast.Div:  operator.truediv,
}
_COMPARISONS: Dict[type, Callable] = {
	ast.Lt:    operator.lt,
	ast.LtE:   operator.le,
	ast.Gt:    operator.gt,
	ast.GtE:   operator.ge,
	ast.Eq:    operator.eq,
	ast.NotEq: operator.ne,
}
#: Operators where a bare number next to a measurement is ambiguous: is the
#: 5 in ``temperature - 5`` Celsius or Fahrenheit? Multiplying and dividing
#: by a bare number has no such problem.
_UNIT_SENSITIVE = frozenset({ast.Add, ast.Sub, *_COMPARISONS})

_ALLOWED_NODES = (
	ast.Expression, ast.Load,
	ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare, ast.IfExp, ast.Call, ast.Name, ast.Constant,
	ast.UAdd, ast.USub, ast.Not, ast.And, ast.Or,
	*_BINARY_OPERATORS, *_COMPARISONS,
)


def _formatDuration(span: timedelta) -> str:
	seconds = span.total_seconds()
	sign = '-' if seconds < 0 else ''
	seconds = abs(seconds)
	for suffix, unit in (('w', 604800), ('d', 86400), ('h', 3600), ('m', 60), ('s', 1)):
		if seconds >= unit and seconds % unit == 0:
			return f'{sign}{int(seconds // unit)}{suffix}'
	return f'{sign}{seconds}s'


# -- parsing --------------------------------------------------------------------

class Expression:
	"""A parsed, checked expression.

	``key`` is the computed key the result is published under. It comes from
	the parsed form, not the text, so spacing and redundant brackets do not
	change it: two panels writing the same expression differently share one
	computation.

	``plainKey`` is set when the whole expression is one key. Callers should
	subscribe to that key directly instead of computing anything.
	"""
	__slots__ = ('text', 'key', 'plainKey', 'keys', 'series', 'points', 'usesValue', '_tree', '_placeholders')

	_interned: Dict[str, 'Expression'] = {}

	text: str
	key: CategoryItem
	plainKey: Optional[CategoryItem]
	#: Keys read at their current value.
	keys: FrozenSet[CategoryItem]
	series: FrozenSet[SeriesInput]
	points: FrozenSet[PointInput]
	#: True when the expression refers to ``value``, the displayed value of
	#: the item it belongs to.
	usesValue: bool

	@classmethod
	def parse(cls, text: str) -> 'Expression':
		if not isinstance(text, str):
			raise ExpressionError(f'an expression must be text, not {type(text).__name__}')
		text = text.strip()
		if (existing := cls._interned.get(text)) is not None:
			return existing
		expression = cls(text)
		cls._interned[text] = expression
		return expression

	def __init__(self, text: str):
		self.text = text
		if not text:
			raise ExpressionError('the expression is empty')
		source, placeholders = _substitute(text)
		try:
			tree = ast.parse(source, mode='eval')
		except SyntaxError as e:
			raise ExpressionError(f'cannot parse {text!r}: {e.msg}') from None
		self._tree = tree
		self._placeholders = placeholders
		_check(tree, placeholders, text)

		self.keys, self.series, self.points, self.usesValue = _inputs(tree, placeholders, text)
		body = tree.body
		if isinstance(body, ast.Name) and isinstance(placeholders.get(body.id), CategoryItem):
			self.plainKey = placeholders[body.id]
		else:
			self.plainKey = None
		digest = hashlib.sha1(_canonical(tree, placeholders).encode()).hexdigest()[:12]
		self.key = CategoryItem(f'{COMPUTED_ROOT}.x{digest}')

	def __repr__(self):
		return f'Expression({self.text!r})'

	def __eq__(self, other):
		if isinstance(other, Expression):
			return self.key == other.key
		return NotImplemented

	def __hash__(self):
		return hash(self.key)

	@property
	def inputKeys(self) -> FrozenSet[CategoryItem]:
		"""Every key this expression reads, in any form."""
		return self.keys | {i.key for i in self.series} | {i.key for i in self.points}

	def evaluate(self, resolver: Resolver, now: Optional[datetime] = None, value: Any = Missing) -> Any:
		"""Evaluate against ``resolver``. Returns ``Missing`` when an input
		the result depends on has no value."""
		if now is None:
			now = datetime.now().astimezone()
		return _Evaluator(resolver, now, value, self._placeholders, self.text).eval(self._tree.body)


def _substitute(text: str) -> Tuple[str, Dict[str, Any]]:
	placeholders: Dict[str, Any] = {}

	def key(match: re.Match) -> str:
		# Nothing would run - a key is only ever looked up - but a dunder
		# atom is never a real key and reads like an escape attempt.
		if any(atom.startswith('__') for atom in re.split(r'[.:#]', match.group(0))):
			raise ExpressionError(f'{text!r}: {match.group(0)!r} is not a valid key')
		name = f'{_KEY_PREFIX}{len(placeholders)}'
		placeholders[name] = CategoryItem(match.group(0))
		return name

	def duration(match: re.Match) -> str:
		name = f'{_DURATION_PREFIX}{len(placeholders)}'
		placeholders[name] = float(match.group(1)) * _DURATION_UNITS[match.group(2)]
		return name

	text = _KEY_PATTERN.sub(key, text)
	text = _DURATION_PATTERN.sub(duration, text)
	return text, placeholders


def _check(tree: ast.AST, placeholders: Mapping[str, Any], text: str) -> None:
	for node in ast.walk(tree):
		if not isinstance(node, _ALLOWED_NODES):
			raise ExpressionError(f'{text!r}: {type(node).__name__} is not allowed in an expression')
		match node:
			case ast.Constant(value=value):
				if isinstance(value, bool) or not isinstance(value, (int, float)):
					raise ExpressionError(f'{text!r}: only numbers are allowed as literals, not {value!r}')
			case ast.Name(id=name):
				if name not in placeholders and name not in _RESERVED_NAMES and name not in _FUNCTIONS:
					raise ExpressionError(f'{text!r}: unknown name {name!r} (a key needs at least two parts, like a.b)')
			case ast.Call(func=func, args=args, keywords=keywords):
				if not isinstance(func, ast.Name) or func.id not in _FUNCTIONS:
					raise ExpressionError(f'{text!r}: unknown function {ast.unparse(func)!r}')
				if keywords:
					raise ExpressionError(f'{text!r}: {func.id}() takes no keyword arguments')
				_checkCall(func.id, args, placeholders, text)
	# A function name is only allowed in call position.
	called = {id(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
	for node in ast.walk(tree):
		if isinstance(node, ast.Name) and node.id in _FUNCTIONS and id(node) not in called:
			raise ExpressionError(f'{text!r}: {node.id} is a function; call it as {node.id}(...)')
	# Durations and today only make sense as a window or an offset.
	allowed = set()
	for node in ast.walk(tree):
		if isinstance(node, ast.Call) and len(node.args) == 2 and _isWindowCall(node, placeholders):
			allowed.update(id(n) for n in ast.walk(node.args[1]))
	for node in ast.walk(tree):
		if isinstance(node, ast.Name) and id(node) not in allowed:
			if node.id == _TODAY or isinstance(placeholders.get(node.id), timedelta):
				raise ExpressionError(f'{text!r}: a duration or today can only be the second argument of min, max, avg or at')


def _isKey(node: ast.AST, placeholders: Mapping[str, Any]) -> bool:
	return isinstance(node, ast.Name) and isinstance(placeholders.get(node.id), CategoryItem)


def _durationOf(node: ast.AST, placeholders: Mapping[str, Any]) -> Optional[timedelta]:
	"""The duration a node spells, allowing a leading sign, else None."""
	match node:
		case ast.Name(id=name) if isinstance(placeholders.get(name), timedelta):
			return placeholders[name]
		case ast.UnaryOp(op=ast.USub(), operand=operand):
			inner = _durationOf(operand, placeholders)
			return -inner if inner is not None else None
		case ast.UnaryOp(op=ast.UAdd(), operand=operand):
			return _durationOf(operand, placeholders)
	return None


def _windowOf(node: ast.AST, placeholders: Mapping[str, Any]) -> Optional[Window]:
	if isinstance(node, ast.Name) and node.id == _TODAY:
		return Window()
	if (span := _durationOf(node, placeholders)) is not None:
		return Window(span)
	return None


def _isWindowCall(node: ast.Call, placeholders: Mapping[str, Any]) -> bool:
	"""``min/max/avg(key, window)`` or ``at(key, offset)``."""
	name = node.func.id
	if name == 'at':
		return True
	return name in _WINDOW_FUNCTIONS and len(node.args) == 2 and _windowOf(node.args[1], placeholders) is not None


def _checkCall(name: str, args: Sequence[ast.AST], placeholders: Mapping[str, Any], text: str) -> None:
	match name:
		case 'at':
			if len(args) != 2 or not _isKey(args[0], placeholders) or _durationOf(args[1], placeholders) is None:
				raise ExpressionError(f'{text!r}: at() takes a key and an offset, like at(a.b, -3h)')
		case 'abs':
			if len(args) != 1:
				raise ExpressionError(f'{text!r}: abs() takes one argument')
		case 'avg':
			if len(args) != 2 or _windowOf(args[1], placeholders) is None:
				raise ExpressionError(f'{text!r}: avg() takes a key and a window, like avg(a.b, 24h)')
			if not _isKey(args[0], placeholders):
				raise ExpressionError(f'{text!r}: the first argument of avg() must be a key')
		case 'min' | 'max':
			if not args:
				raise ExpressionError(f'{text!r}: {name}() needs arguments')
			if len(args) == 2 and _windowOf(args[1], placeholders) is not None:
				if not _isKey(args[0], placeholders):
					raise ExpressionError(f'{text!r}: {name}() over a window needs a key as its first argument')
			elif len(args) < 2:
				raise ExpressionError(f'{text!r}: {name}() takes a key and a window, or two or more values')


def _inputs(tree: ast.AST, placeholders: Mapping[str, Any], text: str):
	keys, series, points = set(), set(), set()
	windowed = set()
	for node in ast.walk(tree):
		if isinstance(node, ast.Call) and _isWindowCall(node, placeholders):
			key = placeholders[node.args[0].id]
			windowed.add(id(node.args[0]))
			if node.func.id == 'at':
				points.add(PointInput(key, _durationOf(node.args[1], placeholders)))
			else:
				series.add(SeriesInput(key, _windowOf(node.args[1], placeholders)))
	usesValue = False
	for node in ast.walk(tree):
		if _isKey(node, placeholders) and id(node) not in windowed:
			keys.add(placeholders[node.id])
		elif isinstance(node, ast.Name) and node.id == _VALUE:
			usesValue = True
	return frozenset(keys), frozenset(series), frozenset(points), usesValue


def _canonical(tree: ast.AST, placeholders: Mapping[str, Any]) -> str:
	"""A dump of the tree with placeholders swapped back for what they stand
	for, so the computed key depends on meaning rather than numbering."""

	class Restore(ast.NodeTransformer):
		def visit_Name(self, node: ast.Name):
			match placeholders.get(node.id):
				case CategoryItem() as key:
					return ast.copy_location(ast.Constant(f'key:{key!s}'), node)
				case timedelta() as span:
					return ast.copy_location(ast.Constant(f'duration:{span.total_seconds()}'), node)
			return node

	restored = Restore().visit(ast.parse(ast.unparse(tree), mode='eval'))
	return ast.dump(restored, annotate_fields=False, include_attributes=False)


# -- evaluation -----------------------------------------------------------------

def _isMeasurement(value: Any) -> bool:
	return isinstance(value, wu.Measurement)


def _isBareNumber(value: Any) -> bool:
	return isinstance(value, (int, float)) and not isinstance(value, bool) and not _isMeasurement(value)


class _Evaluator:
	__slots__ = ('resolver', 'now', 'value', 'placeholders', 'text')

	def __init__(self, resolver: Resolver, now: datetime, value: Any, placeholders: Mapping[str, Any], text: str):
		self.resolver = resolver
		self.now = now
		self.value = value
		self.placeholders = placeholders
		self.text = text

	def eval(self, node: ast.AST) -> Any:
		match node:
			case ast.Constant(value=value):
				return value
			case ast.Name(id=name):
				return self._name(name)
			case ast.UnaryOp(op=op, operand=operand):
				return self._unary(op, self.eval(operand))
			case ast.BinOp(left=left, op=op, right=right):
				return self._binary(op, self.eval(left), self.eval(right))
			case ast.Compare(left=left, ops=ops, comparators=comparators):
				return self._compare(left, ops, comparators)
			case ast.BoolOp(op=op, values=values):
				return self._boolean(op, values)
			case ast.IfExp(test=test, body=body, orelse=orelse):
				condition = self.eval(test)
				if condition is Missing:
					return Missing
				return self.eval(body if condition else orelse)
			case ast.Call():
				return self._call(node)
		raise ExpressionError(f'{self.text!r}: cannot evaluate {type(node).__name__}')

	def _name(self, name: str) -> Any:
		if name == _VALUE:
			return self.value
		key = self.placeholders[name]
		return self._present(self.resolver.current(key))

	@staticmethod
	def _present(value: Any) -> Any:
		return Missing if value is None else value

	def _unary(self, op: ast.unaryop, operand: Any) -> Any:
		if operand is Missing:
			return Missing
		match op:
			case ast.Not():
				return not operand
			case ast.UAdd():
				return operand
			case ast.USub():
				# WeatherUnits' __neg__ returns a bare float, dropping the unit.
				return operand * -1
		raise ExpressionError(f'{self.text!r}: unknown operator {type(op).__name__}')

	def _checkUnits(self, op: ast.AST, left: Any, right: Any) -> None:
		if type(op) not in _UNIT_SENSITIVE:
			return
		if (_isMeasurement(left) and _isBareNumber(right)) or (_isBareNumber(left) and _isMeasurement(right)):
			measurement = left if _isMeasurement(left) else right
			bare = right if _isMeasurement(left) else left
			if type(op) in _COMPARISONS and bare == 0 and not isinstance(measurement, wu.Temperature):
				# Zero is the same in every unit of a measure that starts at zero, so
				# `rain > 0` is not ambiguous. Celsius and Fahrenheit zeros differ, so a
				# temperature still has to name a second key.
				return
			raise ExpressionError(
				f'{self.text!r}: a bare number next to a {type(measurement).__name__} is ambiguous, '
				f'because its unit is not known; only multiply or divide a measurement by a bare number'
			)

	def _binary(self, op: ast.operator, left: Any, right: Any) -> Any:
		if left is Missing or right is Missing:
			return Missing
		self._checkUnits(op, left, right)
		try:
			return _BINARY_OPERATORS[type(op)](left, right)
		except ZeroDivisionError:
			return Missing

	def _compare(self, left: ast.AST, ops: Sequence[ast.cmpop], comparators: Sequence[ast.AST]) -> Any:
		current = self.eval(left)
		if current is Missing:
			return Missing
		for op, comparator in zip(ops, comparators):
			following = self.eval(comparator)
			if following is Missing:
				return Missing
			self._checkUnits(op, current, following)
			if not _COMPARISONS[type(op)](current, following):
				return False
			current = following
		return True

	def _boolean(self, op: ast.boolop, values: Sequence[ast.AST]) -> Any:
		result = Missing
		for node in values:
			result = self.eval(node)
			if result is Missing:
				return Missing
			if isinstance(op, ast.And) and not result:
				return result
			if isinstance(op, ast.Or) and result:
				return result
		return result

	def _call(self, node: ast.Call) -> Any:
		name = node.func.id
		args = node.args
		if _isWindowCall(node, self.placeholders):
			key = self.placeholders[args[0].id]
			if name == 'at':
				offset = _durationOf(args[1], self.placeholders)
				return self._present(self.resolver.at(key, self.now + offset))
			start, end = _windowOf(args[1], self.placeholders).bounds(self.now)
			points = self.resolver.series(key, start, end)
			values = [v for _, v in points or () if v is not None]
			if not values:
				return Missing
			match name:
				case 'min':
					return min(values)
				case 'max':
					return max(values)
				case 'avg':
					return sum(values[1:], values[0]) / len(values)
		values = [self.eval(arg) for arg in args]
		if any(v is Missing for v in values):
			return Missing
		match name:
			case 'abs':
				return abs(values[0])
			case 'min':
				return min(values)
			case 'max':
				return max(values)
		raise ExpressionError(f'{self.text!r}: cannot call {name}()')
