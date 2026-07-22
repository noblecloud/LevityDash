"""Wire codec: (de)serializing the value types that cross the backend/frontend
boundary to and from plain JSON-safe dicts/strings.

Versioned (schema `v`) so the wire format can evolve without breaking an
older frontend talking to a newer backend or vice versa - see WIRE_VERSION.

Three things get encoded today:
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

Deliberately NOT handled here: anything Qt-touching (e.g. an icon-type
value's resolved `Icon`, which carries a QFont). That resolution happens
frontend-side, in lib/wire/containers.py, specifically to keep this module
free of UI imports - see RemoteObservationValue's icon_alias handling.
"""
from datetime import datetime, timezone
from typing import Any, Optional

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


def _resolve_measurement_class(cls_name: Optional[str], unit: Optional[str]):
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
