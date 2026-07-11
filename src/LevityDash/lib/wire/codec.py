"""Wire codec: (de)serializing the value types that cross the backend/frontend
boundary to and from plain JSON-safe dicts/strings.

Versioned (schema `v`) so the wire format can evolve without breaking an
older frontend talking to a newer backend or vice versa - see WIRE_VERSION.

Two things get encoded today:
  - CategoryItem <-> its string form (already round-trips via str()/the
    constructor - see categories.py; wrapped here for a single call site).
  - WeatherUnits Measurement <-> {"value", "unit", "cls", "ts"} - value is
    the plain float (a Measurement is a float subclass), unit/cls are used
    together to resolve the exact class on decode (unit alone can be
    ambiguous - e.g. a bare "%" is shared by several dimensions).
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
	# Prefer the exact class name (unambiguous); unit is a fallback for
	# payloads from a backend that only sent a symbol, and doubles as a
	# sanity source when cls_name doesn't resolve (renamed/unknown class).
	registry = UnitRegistry
	if cls_name:
		found = registry._units_by_name.get(cls_name.lower())
		if found is not None:
			return found
	if unit:
		found = registry.get(unit)
		if found is not None:
			return found
	return None


def decode_measurement(payload: dict) -> Measurement | float:
	cls = _resolve_measurement_class(payload.get('cls'), payload.get('unit'))
	value = payload['value']
	if cls is None:
		# Unknown unit type (e.g. a frontend running behind on a WeatherUnits
		# version that hasn't registered it yet) - degrade to a plain float
		# rather than raising, so a single unrecognized measurement doesn't
		# take down an entire snapshot/update message.
		return value
	measurement = cls(value)
	ts = payload.get('ts')
	if ts and hasattr(measurement, 'timestamp'):
		try:
			measurement.timestamp = datetime.fromisoformat(ts)
		except (ValueError, AttributeError):
			pass
	return measurement


def encode_value(value: Any) -> Any:
	"""Encode a single value that might be a Measurement, a CategoryItem, or
	already JSON-safe (str/int/float/bool/None/dict/list)."""
	if isinstance(value, Measurement):
		return {'__type__': 'measurement', **encode_measurement(value)}
	if isinstance(value, CategoryItem):
		return {'__type__': 'category_item', 'value': encode_category_item(value)}
	return value


def decode_value(value: Any) -> Any:
	if isinstance(value, dict) and '__type__' in value:
		match value['__type__']:
			case 'measurement':
				return decode_measurement(value)
			case 'category_item':
				return decode_category_item(value['value'])
	return value
