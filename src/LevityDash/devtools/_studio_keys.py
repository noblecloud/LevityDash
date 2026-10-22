"""Dev-only: what the Studio's key browser knows, with no Qt in it.

Every key the loaded plugins publish (a running plugin's own values, and the keys a plugin that is off or still
waiting could publish, from its schema), with the source, the place, the unit, the shape and the live value of
each. A search box filters them; an expression is checked against them.

Read from the dashboard the Studio previews on (`LevityDashboard.dispatcher` and `.plugins`), so what the browser
lists is what an item written into that dashboard can read.
"""
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from LevityDash.lib.plugins import places as placeTools
from LevityDash.lib.plugins.expressions import COMPUTED_ROOT, Expression, ExpressionError
from LevityDash.lib.plugins.shapes import shapeOf

#: A source's state: it publishes a value, it is on but has none, or it is off.
LIVE, WAITING, OFF = 'live', 'waiting', 'off'
FILTER_NAMES = ('source', 'place', 'unit', 'shape', 'state')
#: The functions an expression can call, for the Insert menu.
SNIPPETS: List[Tuple[str, str]] = [
	('Average of keys', 'avg(a, b)'),
	('Highest in a window', 'max(key, 24h)'),
	('Lowest today', 'min(key, today)'),
	('Value some time ago', 'at(key, -3h)'),
	('A key at a place', 'key@place'),
	('Average over a place', 'avg(key, where=place)'),
	('Count of readings at a place', 'count(key, where=place)'),
	('Difference', 'a - b'),
	('In another unit', 'to(key, unit)'),
	('Compare', 'key > 15mph'),
]


@dataclass
class SourceInfo:
	"""One plugin's side of a key."""
	name: str
	state: str
	value: str = ''
	unit: str = ''

	@property
	def label(self) -> str:
		return {LIVE: self.value or 'no value', WAITING: 'waiting', OFF: 'off'}[self.state]


@dataclass
class KeyInfo:
	"""One key as an item writes it (`indoor.temperature.temperature#bedroom`)."""
	key: str
	path: str
	identity: str = ''
	place: str = ''
	title: str = ''
	unit: str = ''
	shape: str = 'number'
	sources: List[SourceInfo] = field(default_factory=list)

	@property
	def state(self) -> str:
		states = {s.state for s in self.sources}
		return LIVE if LIVE in states else WAITING if WAITING in states else OFF

	@property
	def value(self) -> str:
		for source in self.sources:
			if source.state == LIVE:
				return source.value
		return ''

	@property
	def sourceNames(self) -> List[str]:
		return [s.name for s in self.sources]

	def writtenFor(self, source: Optional[str]) -> str:
		"""The key as an item names it. With a source, `Source:key` pins that plugin's reading."""
		return f'{source}:{self.key}' if source else self.key


# Section: reading the dashboard

def _splitKey(key: Any) -> Tuple[str, str]:
	"""``(path, identity)`` of a key as the dispatcher holds it."""
	identity = str(getattr(key, 'identity', None) or '')
	path = str(key.withoutIdentity) if identity and hasattr(key, 'withoutIdentity') else str(key)
	return path, identity


def _unitOf(value: Any, metadata: Any) -> str:
	symbol = getattr(value, 'unit_symbol', None)
	if symbol:
		return str(symbol)
	unit = getattr(metadata, 'unit', None) or (metadata.get('sourceUnit') if hasattr(metadata, 'get') else None)
	if isinstance(unit, (list, tuple)):
		unit = '/'.join(map(str, unit))
	return str(unit or '')


def _valueOf(container: Any) -> Tuple[Any, str]:
	"""The measurement a container holds now and its text; ``(None, '')`` with no value."""
	try:
		observation = container.now
	except Exception:  # noqa: BLE001 - a container still waiting for its first reading
		return None, ''
	value = getattr(observation, 'value', observation)
	if value is None:
		return None, ''
	try:
		return value, str(value)
	except Exception:  # noqa: BLE001
		return value, ''


def _shapeOf(metadata: Any, value: Any) -> str:
	try:
		if metadata is not None:
			return shapeOf(metadata)
	except Exception:  # noqa: BLE001
		pass
	return 'number' if value is not None and hasattr(value, 'unit') else 'text'


def _leaf(schemaKey: Any, entry: Any) -> bool:
	"""A schema entry that names a value, not a branch (`environment`) or the `timestamp` bookkeeping."""
	if str(schemaKey) == 'timestamp' or not hasattr(entry, 'get'):
		return False
	return any(entry.get(name) for name in ('sourceUnit', 'type', 'title'))


def collectKeys(dispatcher: Any, plugins: Iterable[Any]) -> List[KeyInfo]:
	"""Every key there is to read, sorted by key. A key several plugins publish is one row with a source for each."""
	plugins = [p for p in plugins if getattr(p, 'name', None)]
	byIdentity = placeTools.placesOf(plugins)
	found: Dict[str, KeyInfo] = {}

	def row(key: Any) -> KeyInfo:
		text = str(key)
		if (info := found.get(text)) is None:
			path, identity = _splitKey(key)
			info = found[text] = KeyInfo(key=text, path=path, identity=identity, place=byIdentity.get(identity, identity))
		return info

	def add(info: KeyInfo, source: SourceInfo, metadata: Any = None, value: Any = None):
		if not any(s.name == source.name for s in info.sources):
			info.sources.append(source)
		title = metadata.get('title') if hasattr(metadata, 'get') else getattr(metadata, 'title', None)
		info.title = info.title or str(title or '')
		info.unit = info.unit or source.unit
		if info.sources[0] is source or not info.shape or info.shape == 'number':
			info.shape = _shapeOf(metadata, value)

	try:
		items = list(dispatcher.items())
	except Exception:  # noqa: BLE001 - a dispatcher with nothing yet
		items = []
	for key, multi in items:
		if str(key).startswith(f'{COMPUTED_ROOT}.'):
			continue  # a calculation a dashboard registered, not a key a plugin publishes
		try:
			containers = list(multi.items())
		except Exception:  # noqa: BLE001
			continue
		for name, container in containers:
			metadata = getattr(container, 'metadata', None)
			value, text = _valueOf(container)
			state = LIVE if value is not None else WAITING
			add(row(key), SourceInfo(str(name), state, text, _unitOf(value, metadata)), metadata, value)

	for plugin in plugins:
		try:
			schema = plugin.schema.flatDict
		except Exception:  # noqa: BLE001 - a plugin whose schema failed to load
			continue
		state = WAITING if getattr(plugin, 'enabled', False) else OFF
		for schemaKey, entry in schema.items():
			if not _leaf(schemaKey, entry):
				continue
			info = row(schemaKey)
			if any(s.name == plugin.name for s in info.sources):
				continue
			add(info, SourceInfo(plugin.name, state, '', _unitOf(None, entry)), entry)
	return sorted(found.values(), key=lambda i: i.key)


# Section: search

_TOKEN = re.compile(r'(\w+):(\S*)')


def parseQuery(text: str) -> Tuple[List[str], Dict[str, str]]:
	"""``(words, filters)``: ``temp source:Govee place:upstairs`` is the word ``temp`` and two filters."""
	filters: Dict[str, str] = {}

	def take(match: re.Match) -> str:
		name = match.group(1).lower()
		if name in FILTER_NAMES:
			filters[name] = match.group(2).lower()
			return ' '
		return match.group(0)

	rest = _TOKEN.sub(take, text)
	return [w for w in rest.lower().split() if w], filters


def matches(info: KeyInfo, text: str) -> bool:
	"""Every word is somewhere in the key or its title; every filter holds."""
	words, filters = parseQuery(text)
	haystack = f'{info.key} {info.title}'.lower()
	if any(w not in haystack for w in words):
		return False
	for name, want in filters.items():
		if name == 'source':
			ok = any(want in s.name.lower() for s in info.sources)
		elif name == 'place':
			ok = bool(info.place) and (info.place == want or info.place.startswith(want + '.') or want in info.place)
		elif name == 'unit':
			ok = want in {info.unit.lower(), *(s.unit.lower() for s in info.sources)}
		elif name == 'shape':
			ok = info.shape == want
		else:
			ok = info.state == want
		if not ok:
			return False
	return True


# Section: expressions

@dataclass
class Report:
	"""What checking an expression found. ``problem`` is the parse error, if any."""
	problem: str = ''
	kind: str = ''
	keys: List[str] = field(default_factory=list)
	unknown: List[str] = field(default_factory=list)
	places: List[str] = field(default_factory=list)
	waiting: List[str] = field(default_factory=list)

	@property
	def ok(self) -> bool:
		return not self.problem


def _bare(key: Any) -> str:
	"""A key as the browser lists it: no source prefix."""
	return str(key.withoutSource) if hasattr(key, 'withoutSource') else str(key)


def checkExpression(text: str, known: Sequence[KeyInfo]) -> Report:
	"""Parse ``text`` (a key, or maths over keys) and say which of the keys it reads nothing publishes."""
	text = (text or '').strip()
	if not text:
		return Report(problem='No key: nothing is drawn.')
	try:
		expression = Expression.parse(text)
	except ExpressionError as error:
		return Report(problem=str(error))
	except Exception as error:  # noqa: BLE001 - the parser's own failure is a message, not a crash
		return Report(problem=f'{type(error).__name__}: {error}')
	table = {info.key: info for info in known}
	paths = {info.path for info in known}
	report = Report(kind='a key' if expression.plainKey is not None else 'an expression')
	for key in sorted(expression.inputKeys, key=str):
		name = str(key)
		report.keys.append(name)
		info = table.get(name)
		if info is None and str(getattr(key, 'identity', None) or '') == '':
			info = table.get(_bare(key))
		if info is None:
			# A key without an identity is readable when some device publishes it.
			if name not in paths and not any(i.path == name for i in known):
				report.unknown.append(name)
		elif info.state != LIVE:
			report.waiting.append(name)
	report.places = sorted({placed.place for placed in expression.places})
	return report


def describe(report: Report) -> str:
	if not report.ok:
		return report.problem
	count = len(report.keys)
	text = f'{report.kind} reading {count} key{"" if count == 1 else "s"}'
	if report.keys:
		text += ': ' + ', '.join(report.keys)
	if report.places:
		text += f'\nat {", ".join(report.places)}'
	if report.unknown:
		text += f'\nNo loaded plugin has {", ".join(report.unknown)}.'
	elif report.waiting:
		text += f'\nNo value yet from {", ".join(report.waiting)}.'
	return text


def preview(text: str) -> str:
	"""What ``text`` works out to now on the previewed dashboard's data, or why it cannot. Publishes nothing."""
	try:
		expression = Expression.parse(text)
		if expression.usesValue:
			return '`value` only means something in a display property.'
		from LevityDash.lib.plugins.computed import computedEngine
		result, used = computedEngine().peek(expression)
	except ExpressionError as error:
		return str(error)
	except Exception as error:  # noqa: BLE001 - a preview must never take the Studio down
		return f'{type(error).__name__}: {error}'
	from LevityDash.lib.plugins.expressions import Missing
	if result is Missing or result is None:
		return 'no value yet'
	note = f' from {used} reading{"" if used == 1 else "s"}' if expression.places else ''
	return f'= {result}{note}'


def isExpression(text: str) -> bool:
	"""True when ``text`` is maths over keys, not one key."""
	try:
		return Expression.parse(text).plainKey is None
	except Exception:  # noqa: BLE001
		return False
