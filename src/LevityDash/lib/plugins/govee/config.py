"""Reading Govee's device configuration.

The format optimises for the thing users actually do - add a thermometer -
and pushes everything else into optional overrides.

.. code-block:: ini

	[plugin]
	enabled = True

	[devices]
	bedroom   = GVH5102_6736
	terrarium = GVH5102_527D

``alias = advertised name``. The alias is the identity in keys
(``…temperature#bedroom``) and the device's half of its source name
(``Govee-bedroom``); the value is what the sensor broadcasts. The model preset
is detected from that name, so the common case needs no byte-slice
configuration at all - which is the point, since hand-deriving hex offsets
from a datasheet was previously mandatory for every device.

A device needing more than a name gets a section, and only says what differs:

.. code-block:: ini

	[device:garage]
	name = GVH5075_A1B2
	model = H5075              ; pin the preset instead of detecting it
	temperature.slice = [4:10] ; override one field
	temperature.expression = val / 10000

Matching is on advertised *name*, not address: on macOS an address is a
per-machine generated UUID rather than a hardware MAC, so an address-keyed
config would silently stop matching on another machine. ``address`` is
accepted as a same-machine tiebreaker when two sensors advertise the same name.
"""
import re
from typing import Any, Dict, Iterable, List, NamedTuple, Optional

from LevityDash.lib.log import LevityPluginLog
from LevityDash.lib.plugins.govee.models import ModelPreset, preset_for

log = LevityPluginLog.getChild('Govee')

__all__ = ['DeviceConfig', 'parse_devices', 'DEVICE_SECTION_PREFIX', 'DEVICES_SECTION']

#: ``[device:bedroom]`` - a single device's overrides.
DEVICE_SECTION_PREFIX = 'device:'
#: ``[devices]`` - the short form, one line per device.
DEVICES_SECTION = 'devices'

#: Per-field settings a device may override. Anything else in a section is
#: metadata (name/model/address) or ignored.
_PARSER_FIELDS = ('temperature', 'humidity', 'battery')


class DeviceConfig(NamedTuple):
	"""One configured device, resolved from config plus its model preset."""

	alias: str
	name: str
	preset: ModelPreset
	address: Optional[str] = None
	#: Field -> BLEPayloadParser kwargs, preset defaults with overrides applied.
	fields: Dict[str, dict] = {}
	#: True when the user pinned ``model =`` rather than it being detected.
	modelPinned: bool = False

	@property
	def sourceName(self) -> str:
		"""This device's plugin name, e.g. ``Govee-bedroom``.

		Hyphen because ``:`` is ``CategoryItem``'s source separator and ``.``
		is its path separator - either would nest ambiguously inside a key
		string whose source half already does not round-trip.
		"""
		return f'Govee-{self.alias}'


def _parse_slice(value: str) -> Optional[tuple]:
	"""``'[4:10]'`` -> ``(4, 10)``. Tolerant of ``4:10`` and ``4, 10``."""
	found = re.findall(r'\d+', str(value))
	if len(found) != 2:
		return None
	return int(found[0]), int(found[1])


def _field_settings(preset: ModelPreset, overrides: Dict[str, Any]) -> Dict[str, dict]:
	"""Preset field settings with any per-field config overrides applied.

	Overrides are merged per-key, not per-field: overriding an expression
	keeps the preset's slice, which is what someone tweaking one value means.
	"""
	fields = {field: dict(settings) for field, settings in preset.fields.items()}

	for field in _PARSER_FIELDS:
		params = fields.setdefault(field, {}) if field in fields else None
		if (rawSlice := overrides.get(f'{field}.slice')) is not None:
			if (parsed := _parse_slice(rawSlice)) is None:
				log.warning(f'Govee: could not read {field}.slice={rawSlice!r}; keeping preset value')
			else:
				params = fields.setdefault(field, {})
				params['startingByte'], params['endingByte'] = parsed
		if (expression := overrides.get(f'{field}.expression')) is not None:
			params = fields.setdefault(field, {})
			params['expression'] = str(expression)
		if (base := overrides.get(f'{field}.base')) is not None:
			params = fields.setdefault(field, {})
			try:
				params['base'] = int(base)
			except (TypeError, ValueError):
				log.warning(f'Govee: could not read {field}.base={base!r}; keeping preset value')

	# A field with no slice cannot be parsed - drop it rather than construct a
	# parser that reads position 0 to 0 and reports a constant.
	return {
		field: params for field, params in fields.items()
		if 'startingByte' in params and 'endingByte' in params
	}


def _sections(config) -> List[str]:
	try:
		return [str(s) for s in config.sections()]
	except (AttributeError, TypeError):
		return []


def _section(config, name: str) -> Dict[str, Any]:
	try:
		return {str(k): v for k, v in dict(config[name]).items()}
	except (KeyError, TypeError, ValueError):
		return {}


def parse_devices(config) -> List[DeviceConfig]:
	"""Read every configured device, in a stable order.

	Sources, in precedence order - a device declared twice is configured once:

	1. ``[device:alias]`` sections (full control)
	2. ``[devices]`` one-liners (the common case)
	3. a legacy flat ``device.name`` under ``[plugin]``, used *only* when the
	   two above found nothing. It fires on old single-device configs, and
	   letting it also fire alongside a real declaration would double-register
	   the same physical sensor under two aliases.
	"""
	devices: Dict[str, DeviceConfig] = {}

	def add(alias: str, name: str, settings: Dict[str, Any]) -> None:
		alias = str(alias).strip()
		if not alias or alias in devices:
			if alias in devices:
				log.warning(f'Govee: device {alias!r} declared more than once; keeping the first')
			return
		if not name:
			log.warning(f'Govee: device {alias!r} has no advertised name; skipping')
			return
		model = settings.get('model') or settings.get('device.model')
		preset = preset_for(model=model, advertisedName=name)
		devices[alias] = DeviceConfig(
			alias=alias,
			name=str(name),
			preset=preset,
			address=settings.get('address') or settings.get('device.address'),
			fields=_field_settings(preset, settings),
			modelPinned=bool(model),
		)

	# 1. Explicit sections.
	for section in _sections(config):
		if not section.startswith(DEVICE_SECTION_PREFIX):
			continue
		settings = _section(config, section)
		alias = section[len(DEVICE_SECTION_PREFIX):].strip()
		add(alias, settings.get('name', ''), settings)

	# 2. The short form.
	for alias, name in _section(config, DEVICES_SECTION).items():
		add(alias, str(name).strip(), {})

	# 3. Legacy fallback, only when nothing else declared a device.
	if not devices:
		legacy = _section(config, 'plugin').get('device.name')
		if legacy:
			log.info(f'Govee: using legacy [plugin] device.name={legacy!r}; consider a [devices] entry')
			add(str(legacy), str(legacy), _section(config, 'plugin'))

	return list(devices.values())
