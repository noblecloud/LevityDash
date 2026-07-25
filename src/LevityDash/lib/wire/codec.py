"""Wire codec: (de)serializing the value types that cross the backend/frontend
boundary to and from plain JSON-safe dicts/strings.

Versioned (schema `v`) so the wire format can evolve without breaking an
older frontend talking to a newer backend or vice versa - see WIRE_VERSION.

Four things get encoded today:
  - CategoryItem <-> its string form. Round-trips correctly for anonymous
    keys (no `.source` set) - the only kind MultiSourceContainer/dispatcher
    keys are today. NOT yet correct for a CategoryItem with `.source` set:
    CategoryItem.__str__ emits a `source:path` prefix, but the single-string
    constructor's tokenizing regex (categories.py `__new__`, word-chars only)
    doesn't treat `:` as a delimiter - it's simply outside the matched
    character class, so `findall` splits on it exactly like `.`, silently
    folding the source into the path atoms instead of restoring `.source`.
    Fixing this is Phase 3.5's job (the `@source`/`#identity` addressing
    model, which has to design canonical ordering + escaping anyway) - not
    patched here to avoid a narrow, easily-desynced fix landing ahead of
    that design.
  - WeatherUnits Measurement <-> {"value", "unit", "cls", "ts"} - value is
    the plain float (a Measurement is a float subclass), unit/cls are used
    together to resolve the exact class on decode (unit alone can be
    ambiguous - e.g. a bare "%" is shared by several dimensions).
  - datetime <-> an ISO 8601 string. Not every timestamp-typed observation
    value is wrapped in a Measurement (e.g. a raw "last lightning strike"
    reading) - those cross the wire as plain datetimes, not Measurement's
    optional per-value `.timestamp` metadata (which piggybacks on the
    measurement envelope above).
  - A full timeseries <-> columnar `{"unit", "cls", "timestamps", "values"}`
    arrays (encode_timeseries_values/decode_timeseries_values). Unlike a
    single Measurement, unit/cls are resolved once for the whole batch
    instead of once per point - a series is homogeneous, so repeating that
    metadata (and paying a registry lookup) per point would be pure waste.

Deliberately NOT handled here: anything Qt-touching (e.g. an icon-type
value's resolved `Icon`, which carries a QFont). That resolution happens
frontend-side, in lib/wire/containers.py, specifically to keep this module
free of UI imports - see RemoteObservationValue's icon_alias handling.
"""
import re
from datetime import datetime, timezone
from typing import Any, List, Optional, Sequence, Tuple

from WeatherUnits import Measurement
from WeatherUnits.base.Registry import UnitRegistry

from LevityDash.lib.plugins.categories import CategoryItem

WIRE_VERSION = 1


def encode_category_item(item: CategoryItem) -> str:
	return str(item)


def decode_category_item(value: str) -> CategoryItem:
	return CategoryItem(value)


def encode_measurement(value: Measurement) -> dict:
	payload = {
		'value': float(value),
		'unit': getattr(value, 'unit', None),
		'cls': type(value).__name__,
	}
	timestamp = getattr(value, 'timestamp', None)
	if isinstance(timestamp, datetime):
		payload['ts'] = timestamp.astimezone(timezone.utc).isoformat()
	return payload


_PARAMETRIZED_CLS = re.compile(r'^(?P<base>\w+)\[(?P<numerator>[^/\]]+)/(?P<denominator>[^/\]]+)\]$')


def _resolve_parametrized_class(cls_name: Optional[str]):
	"""Resolve a dynamically-parametrized derived unit, e.g.
	``PrecipitationRate[mm/hr]``.

	Derived units (Length/Time and friends) get a class generated per
	numerator/denominator pair. That generated name is NOT in the registry,
	and its composed unit symbol ('mm/hr') isn't a registered symbol either,
	so both lookups in ``_resolve_measurement_class`` miss and the value
	degrades to a bare float - losing precision/max/unit and rendering raw
	float64 digits (a precipitation rate showed up on the dashboard as
	'0.041649606299212590').

	The GENERIC *is* registered, under a spaced lowercase name
	('precipitation rate'), and re-parametrizing it with the two unit symbols
	yields a class that accepts a plain number - which is exactly what the
	wire carries.

	Note this only reaches units whose generic is registered; anything else
	still degrades to float as before.
	"""
	match = _PARAMETRIZED_CLS.match(cls_name or '')
	if match is None:
		return None
	# 'PrecipitationRate' -> 'precipitation rate'
	base = re.sub(r'(?<!^)(?=[A-Z])', ' ', match['base']).lower()
	generic = UnitRegistry._units_by_name.get(base)
	if generic is None:
		return None
	try:
		return generic[match['numerator']:match['denominator']]
	except Exception:
		return None


def _resolve_measurement_class(cls_name: Optional[str], unit: Optional[str]):
	# A bracketed name is an unambiguous parametrized derived unit; neither
	# lookup below can reach it, so try reconstruction first.
	if (parametrized := _resolve_parametrized_class(cls_name)) is not None:
		return parametrized
	# Two resolution paths: exact class name (unambiguous - the right call
	# for symbols several dimensions share, like a bare '%'), and unit
	# symbol. But a name hit can still be wrong for RECONSTRUCTION: derived/
	# rate units (Wind = Distance/Time) register their GENERIC class under
	# 'wind', and the generic constructor wants numerator/denominator
	# measurements, not a bare number - while the symbol ('mph') resolves
	# the SPECIALIZED class (MilesPerHour), which builds fine. So prefer a
	# non-generic candidate, name first, symbol second.
	registry = UnitRegistry
	by_name = registry._units_by_name.get(cls_name.lower()) if cls_name else None
	if by_name is not None and not getattr(by_name, 'isGeneric', False):
		return by_name
	if unit:
		# by-symbol can return the parametrized GENERIC form of a derived
		# unit (can't build from a bare number) - scan for the specialized
		# class carrying that symbol instead.
		by_symbol = next((u for u in registry._all_units if getattr(u, '_unit', None) and u._unit.lower() == unit.lower() and not getattr(u, 'isGeneric', False)), None)
		if by_symbol is not None:
			return by_symbol
	if by_name is not None:
		return by_name
	return registry.get(unit) if unit else None


def decode_measurement(payload: dict) -> Measurement | float:
	cls = _resolve_measurement_class(payload.get('cls'), payload.get('unit'))
	value = payload['value']
	if cls is None:
		# Unknown unit type (e.g. a frontend running behind on a WeatherUnits
		# version that hasn't registered it yet) - degrade to a plain float
		# rather than raising, so a single unrecognized measurement doesn't
		# take down an entire snapshot/update message.
		return value
	try:
		measurement = cls(value)
	except Exception:
		# The class resolved but can't be built from a bare number: derived/
		# rate units (e.g. Wind = Distance/Time) resolve to their GENERIC
		# class, whose constructor wants numerator/denominator measurements -
		# the wire's {unit, cls} pair can't identify the specialized subclass
		# yet. Honor the same degrade-to-float contract as above; proper
		# derived-unit reconstruction over the wire is a known follow-up
		# (surfaced by mode=remote - loopback had been silently skipping
		# these keys via its per-key relay guard all along).
		return value
	ts = payload.get('ts')
	if ts and hasattr(measurement, 'timestamp'):
		# Measurement.timestamp is a read-only property backed by
		# `_timestamp` (WeatherUnits base/_Measurement.py) - assigning
		# `.timestamp` directly always raises AttributeError, so this has to
		# go through the backing attribute instead.
		try:
			measurement._timestamp = datetime.fromisoformat(ts)
		except ValueError:
			pass
	return measurement


def encode_timeseries_values(items: Sequence[Any]) -> Optional[dict]:
	"""Encode a full timeseries as columnar arrays (timestamps chosen, values
	chosen) with `unit`/`cls` resolved ONCE from the first item, not repeated
	per point like encode_measurement would - a series is homogeneous, and
	that's the entire point of this shape over reusing encode_measurement per
	item. `items` is any sequence of objects exposing `.value`/`.timestamp`
	(TimeSeriesItem duck-typing - this module doesn't import observation.py,
	same layering as everything else here)."""
	if not items:
		return None
	first_value = items[0].value
	is_measurement = isinstance(first_value, Measurement)
	timestamps = []
	values = []
	for item in items:
		timestamps.append(item.timestamp.astimezone(timezone.utc).timestamp())
		values.append(float(item.value))
	return {
		'v': WIRE_VERSION,
		'unit': getattr(first_value, 'unit', None) if is_measurement else None,
		'cls': type(first_value).__name__ if is_measurement else None,
		'timestamps': timestamps,
		'values': values,
	}


def decode_timeseries_values(payload: Optional[dict]) -> List[Tuple[datetime, Any]]:
	"""Decode a columnar timeseries payload back into (timestamp, value)
	pairs. Resolves the measurement class ONCE for the whole batch (the
	expensive part - a registry scan), then constructs each point directly.
	A single point's construction failure degrades just that point to a
	plain float, matching decode_measurement's per-value resilience - don't
	move class resolution back inside the loop even though it would look
	similar to decode_measurement's shape, that would undo the compactness/
	perf win columnar encoding exists for."""
	if payload is None:
		return []
	cls = _resolve_measurement_class(payload.get('cls'), payload.get('unit'))
	timestamps = payload.get('timestamps') or []
	values = payload.get('values') or []
	result: List[Tuple[datetime, Any]] = []
	for ts, v in zip(timestamps, values):
		timestamp = datetime.fromtimestamp(ts, tz=timezone.utc)
		if cls is None:
			result.append((timestamp, v))
			continue
		try:
			result.append((timestamp, cls(v)))
		except Exception:
			result.append((timestamp, v))
	return result


def encode_datetime(value: datetime) -> str:
	if value.tzinfo is None:
		value = value.astimezone()
	return value.astimezone(timezone.utc).isoformat()


def decode_datetime(value: str) -> datetime:
	return datetime.fromisoformat(value)


def encode_value(value: Any) -> Any:
	"""Encode a single value that might be a Measurement, a CategoryItem, a
	datetime, or already JSON-safe (str/int/float/bool/None/dict/list)."""
	# isinstance(value, Measurement) before datetime: Measurement is a float
	# subclass, not a datetime subclass, so there's no ordering hazard - but
	# WeatherUnits' own Time measurements wrap durations, not calendar
	# dates, so datetime is checked as its own branch, not folded into it.
	if isinstance(value, Measurement):
		return {'__type__': 'measurement', **encode_measurement(value)}
	if isinstance(value, CategoryItem):
		return {'__type__': 'category_item', 'value': encode_category_item(value)}
	if isinstance(value, datetime):
		return {'__type__': 'datetime', 'value': encode_datetime(value)}
	return value


def decode_value(value: Any) -> Any:
	if isinstance(value, dict) and '__type__' in value:
		match value['__type__']:
			case 'measurement':
				return decode_measurement(value)
			case 'category_item':
				return decode_category_item(value['value'])
			case 'datetime':
				return decode_datetime(value['value'])
	return value
