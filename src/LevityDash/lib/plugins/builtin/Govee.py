"""Govee BLE thermometers.

One ``Plugin`` instance per configured device, all sharing one BLE scanner.

**Why per-device instances.** This plugin used to be a single-device plugin
with multi-device support bolted on: individual *values* were scoped with an
identity suffix (``…temperature#bedroom``) while ``name``, ``running``, the
scanner, and the payload parser stayed singular and were fought over by
whichever device reported most recently. That shape produced a steady supply
of bugs - a plugin renamed after one device so the control plane could not
find it, log lines attributing every reading to the same sensor, one device's
config silently deciding how the other's bytes were parsed.

Home Assistant's ``govee_ble`` integration has the shape that works: the
Bluetooth platform owns one scanner, and each device gets its own coordinator
filtered to its own address. Here that is one ``Plugin`` per device
(``Govee-bedroom``, ``Govee-terrarium``), each a distinct *source*, all
subscribed to :mod:`LevityDash.lib.plugins.ble`'s shared scanner. Per-device
state lives on the instance that owns it, so there is nothing left to fight
over.

**Identity is kept, and is not redundant.** Each device is now its own source,
so ``#bedroom`` and ``Govee-bedroom`` name the same thing today. They are still
different axes: ``source`` answers "who reported this" and is *reconciled* by
``MultiSourceContainer``, while ``identity`` answers "which physical thing is
this" and is never merged. If a Zigbee sensor ever reports the same room,
``…temperature#bedroom`` stays meaningful across both plugins where a source
name cannot. Saved dashboards already rely on this - they address these
thermometers by identity alone, with no ``source:`` pin.

Configuration is documented in :mod:`LevityDash.lib.plugins.govee.config`.
"""
import platform
import re
from datetime import timedelta
from types import FunctionType
from typing import Callable, Dict, List, Optional, Type, Union

from LevityDash.lib.log import LevityPluginLog
from LevityDash.lib.plugins.ble import BLEPlugin
from LevityDash.lib.plugins.categories import CategoryItem
from LevityDash.lib.plugins.govee.config import DeviceConfig, parse_devices
from LevityDash.lib.plugins.govee.models import trim_payload
from LevityDash.lib.plugins.observation import ObservationRealtime
from LevityDash.lib.plugins.schema import LevityDatagram, Schema, SchemaSpecialKeys as tsk
from LevityDash.lib.plugins.utils import ScheduledEvent
from LevityDash.lib.utils.shared import now

pluginLog = LevityPluginLog.getChild('Govee')

__all__ = ["Govee"]


def getBadActors(string: str) -> list[str]:
	return re.findall(r"sys\.?|import\.?|path\.?|os\.|\w*\sas\s\w*|eval|exec|compile|__[a-zA-Z_][a-zA-Z0-9_]*__", string)


def parseMathString(mathString: str, functionName: str = 'mathExpression', **kwargs) -> Callable:
	if badActors := getBadActors(mathString):
		raise RuntimeError(f"The following are not allowed in the math string: {badActors}")

	if mathString.count('\n') > 1:
		raise RuntimeError("Only one line allowed")

	variables = {}
	for match in re.finditer(r"[a-zA-Z_][a-zA-Z0-9_]*", mathString):
		variables[match.group(0)] = None

	variables.update(kwargs)

	remainingVars = []
	for key, value in list(variables.items()):
		if value is None:
			variables.pop(key)
			remainingVars.append(key)
			continue
		mathString = mathString.replace(key, str(value))

	funcString = f'''def {functionName}({', '.join(remainingVars)}):\n\treturn {mathString}'''
	# exec into an explicit namespace rather than relying on locals() picking
	# up the def: PEP 667 (Python 3.13+) makes a function's locals() an
	# independent snapshot on each call, so the def made by exec() here was
	# never guaranteed to show up in a later, separate locals() call - it
	# happened to work pre-3.13 as an implementation detail, not by contract.
	namespace = {}
	exec(compile(funcString, "<string>", "exec"), namespace)
	return namespace[functionName]


class BLEPayloadParser:
	"""Reads one value out of an advertisement payload.

	A hex-character slice plus an arithmetic expression. ``signBit`` handles
	two's-complement-style negatives, which cannot live in the expression:
	``parseMathString`` turns every bare identifier into a variable, so a hex
	literal (``0x800000``) becomes a variable named ``x800000`` and a
	conditional turns ``if``/``else`` into function parameters. Sign handling
	has to be a parser feature rather than user arithmetic.
	"""

	def __init__(
		self,
		field: str,
		startingByte: int,
		endingByte: int,
		expression: Optional[Union[str, Callable]] = None,
		base: int = 16,
		signBit: Optional[int] = None,
	):
		self.__field = field
		self.__startingByte = startingByte
		self.__endingByte = endingByte
		self.__expression: Optional[Callable] = None
		self.__base = base
		self.__signBit = signBit
		match expression:
			case FunctionType():
				self.__expression = expression
			case str():
				self.__expression = parseMathString(expression)

	def __call__(self, payload: bytes) -> dict[str, float | int]:
		raw: int = int(payload.hex().upper()[self.__startingByte: self.__endingByte], self.__base)
		negative = False
		if self.__signBit is not None:
			mask = 1 << self.__signBit
			if raw & mask:
				negative = True
				raw &= mask - 1
		if self.__expression is not None:
			value = self.__expression(raw)
		else:
			value = raw
		if negative:
			value = -value
		return {self.__field: value}


def parse_device_sections(config) -> Dict[str, dict]:
	"""Configured devices as ``{alias: {settings}}``.

	The pre-rewrite shape, kept because it is the useful *read-only* view of
	the config for anything that just wants to know what is configured
	without building plugin instances (and it is what the existing tests
	assert against). :func:`parse_devices` is the richer form the plugin
	itself uses - same parsing underneath, so the two cannot disagree.
	"""
	devices: Dict[str, dict] = {}
	for device in parse_devices(config):
		settings: Dict[str, object] = {'name': device.name}
		if device.address is not None:
			settings['address'] = device.address
		if device.modelPinned:
			settings['model'] = device.preset.model
		devices[device.alias] = settings
	return devices


def resolve_device_identity(advertisedName: str, devices) -> str:
	"""Map an advertised BLE name onto the identity used in keys.

	Falls back to the advertised name when no alias is configured, so two
	thermometers work out of the box and aliasing is a readability upgrade
	rather than a requirement.

	Accepts either the ``{alias: {settings}}`` mapping this plugin used to
	build or a list of :class:`DeviceConfig`, so callers (and tests) written
	against either shape keep working.
	"""
	for entry in (devices or {}).values() if isinstance(devices, dict) else (devices or ()):
		if isinstance(entry, DeviceConfig):
			if entry.name == advertisedName:
				return entry.alias
			continue
		# dict form: {alias: {'name': ...}}
		if entry.get('name') == advertisedName:
			return next(a for a, s in devices.items() if s is entry)
	return advertisedName


def device_scoped_key(key, identity: Optional[str]) -> CategoryItem:
	"""Attach a device identity to a key: ``…temperature#bedroom``.

	Identity rather than an extra path segment so the base key keeps existing -
	a dashboard asking for ``indoor.temperature.temperature`` is not broken by
	a second sensor appearing, and identities are never merged across devices
	the way sources are reconciled.
	"""
	if not isinstance(key, CategoryItem):
		key = CategoryItem(key)
	if identity is None:
		return key
	return key.withIdentity(identity)


_on_board_banner = '[bold]Govee BLE Plugin On-Boarding[/bold]'
_plugin_description = (
	"This plugin connects to Govee BLE thermometers.  Devices are listed in "
	"the plugin's config under [devices] as 'alias = advertised name'; the "
	"model is detected from that name, so no byte-level configuration is "
	"needed for known models (the H5100 and H5072 families, including the "
	"GVH5102 and GVH5075)."
)

if platform.system() == "Darwin":
	_on_board_platform_specific = (
		"\n[yellow2][bold]macOS Note:[/bold][/yellow2] "
		"[italic]Some terminals do not have the correct entitlements for Bluetooth "
		"access and will cause an immediate crash on first connection attempt.  "
		"Information on how to fix this can be found here: "
		"https://bleak.readthedocs.io/en/latest/troubleshooting.html#macos-bugs[/italic]\n"
	)
else:
	_on_board_platform_specific = ""

_on_board_footer = "Enable Govee?"

_on_board_message = f"""{_on_board_banner}

{_plugin_description}
{_on_board_platform_specific}
{_on_board_footer}""".replace('\n', '\\n')

_defaultConfig = f"""
[plugin] ; All independent configs must have a Config section
enabled = @ask(bool:False).message({_on_board_message})

; One line per thermometer: alias = the name it advertises.
; The alias names the device everywhere it appears - in keys
; (indoor.temperature.temperature#bedroom) and as a source (Govee-bedroom).
; The model is detected from the advertised name; no byte slices needed.
[devices]
;bedroom = GVH5102_6736
;terrarium = GVH5102_527D

; Only needed for an unrecognised model or a hand-tuned field:
;[device:garage]
;name = GVH5075_A1B2
;model = H5075
;temperature.slice = [4:10]
;temperature.expression = val / 10000
"""


class Govee(BLEPlugin, realtime=True, logged=True):
	"""One Govee thermometer.

	Instantiated once per configured device by :meth:`__instances__`; there is
	no "the Govee plugin" object at runtime, only ``Govee-bedroom`` and its
	siblings.
	"""

	requirements = {'bluetooth'}

	schema: Schema = {
		'timestamp': {'type': 'datetime', 'sourceUnit': 'epoch', 'title': 'Time', 'sourceKey': 'timestamp', tsk.metaData: True},
		'indoor.temperature.temperature': {'type': 'temperature', 'sourceUnit': 'c', 'title': 'Temperature', 'sourceKey': 'temperature'},
		'indoor.temperature.dewpoint': {'type': 'temperature', 'sourceUnit': 'c', 'title': 'Dew Point', 'sourceKey': 'dewpoint'},
		'indoor.temperature.heatIndex': {'type': 'temperature', 'sourceUnit': 'c', 'title': 'Heat Index', 'sourceKey': 'heatIndex'},
		'indoor.humidity.humidity': {'type': 'humidity', 'sourceUnit': '%h', 'title': 'Humidity', 'sourceKey': 'humidity'},
		'indoor.battery.battery': {'type': 'battery', 'sourceUnit': '%bat', 'title': 'Battery', 'sourceKey': 'battery'},
		'indoor.rssi.rssi': {'type': 'rssi', 'sourceUnit': 'rssi', 'title': 'Signal', 'sourceKey': 'rssi'},
		'@type': {'sourceKey': 'type', tsk.metaData: True, tsk.sourceData: True},
		'@deviceName': {'sourceKey': 'deviceName', tsk.metaData: True, tsk.sourceData: True},
		'@deviceIdentity': {'sourceKey': 'deviceIdentity', tsk.metaData: True, tsk.sourceData: True},
		'@deviceAddress': {'sourceKey': 'deviceAddress', tsk.metaData: True, tsk.sourceData: True},

		# Scopes value keys to the device that produced them. Each device is
		# now its own source too, so this is belt *and* braces for Govee - but
		# identity survives cross-source reconciliation where a source name
		# does not, and saved dashboards address these sensors by identity
		# alone. See the module docstring.
		'identityKey': '@deviceIdentity',

		'dataMaps': {
			'BLEAdvertisementData': {
				'realtime': ()
			}
		}
	}

	__defaultConfig__ = _defaultConfig

	#: This instance's device. Set before ``Plugin.__init__`` runs, because
	#: ``name`` is read during base initialisation.
	device: Optional[DeviceConfig] = None

	#: Class-level fallback so ``name`` is answerable on an instance that has
	#: not run ``__init__`` - ``__instances__`` builds one such probe to read
	#: the config, and ``PluginConfig.__getitem__`` asks for ``plugin.name``
	#: on every section miss. Without this, reading config raised
	#: AttributeError before any device could be discovered.
	__name = 'Govee'

	def __init__(self, device: Optional[DeviceConfig] = None):
		self.device = device
		if device is not None:
			self.__name = device.sourceName
		super().__init__()
		self.lastDatagram: Optional[LevityDatagram] = None
		self.historicalTimer: ScheduledEvent | None = None
		self.__parsers: Dict[str, BLEPayloadParser] = {}
		if device is not None:
			self.__buildParsers()

	# -- construction --------------------------------------------------------

	@classmethod
	def __instances__(cls) -> List['Govee']:
		"""One instance per configured device.

		The loader hook (``PluginsLoader._instantiate``). Config is read once
		here rather than per instance: every device shares one ``Govee.ini``,
		because ``Plugin.getConfig`` keys off the class.
		"""
		# A bare probe, only to read the config: getConfig wants a plugin, but
		# no device is known yet. It answers `name` from the class-level
		# fallback above, which PluginConfig.__getitem__ needs on every
		# section miss.
		probe = object.__new__(cls)
		try:
			config = cls.getConfig(probe)
		except Exception as e:
			pluginLog.error(f'Govee: unable to read config: {e}')
			return []

		devices = parse_devices(getattr(config, 'parser', config))
		if not devices:
			pluginLog.info(
				'Govee: no devices configured - add entries under [devices] in Govee.ini '
				'(alias = advertised name)'
			)
			return []

		instances = []
		for device in devices:
			try:
				instances.append(cls(device))
			except Exception as e:
				pluginLog.error(f'Govee: failed to set up device {device.alias!r}: {e}')
				pluginLog.exception(e)
		if instances:
			pluginLog.info(
				f'Govee: {len(instances)} device(s): '
				+ ', '.join(f'{i.device.alias} ({i.device.preset.model})' for i in instances)
			)
		return instances

	def __buildParsers(self) -> None:
		for field, params in self.device.fields.items():
			try:
				self.__parsers[field] = BLEPayloadParser(field=field, **params)
			except Exception as e:
				pluginLog.error(f'{self.name}: could not build the {field} parser: {e}')

	@property
	def name(self) -> str:
		return self.__name

	@classmethod
	def _validateConfig(cls, cfg) -> bool:
		return bool('enabled' in cfg and cfg['enabled'])

	# -- BLE routing ---------------------------------------------------------

	def wants(self, device, data) -> bool:
		"""Claim only this instance's device.

		Address is checked first when configured - it is exact - then the
		advertised name, which is what config keys on (macOS randomises
		addresses per machine, so a name is the portable identifier).
		"""
		if self.device is None:
			return False
		if (address := self.device.address) is not None:
			if str(getattr(device, 'address', '')).lower() == str(address).lower():
				return True
		return getattr(device, 'name', None) == self.device.name

	def handleAdvertisement(self, device, data) -> None:
		self.__dataParse(device, data)

	# -- lifecycle -----------------------------------------------------------

	async def onStart(self) -> None:
		await super().onStart()
		if self.historicalTimer is None:
			self.historicalTimer = ScheduledEvent(timedelta(seconds=15), self.logValues, loop=self.loop).schedule()
		else:
			self.historicalTimer.schedule()

	async def onStop(self) -> None:
		await super().onStop()
		if self.historicalTimer is not None and self.historicalTimer.running:
			self.historicalTimer.stop()

	async def close(self):
		await self.asyncStop()

	# -- data ----------------------------------------------------------------

	def get_device_observation(self, device: str):
		RealtimeClass: Type[ObservationRealtime] = self.classes['Realtime']
		return RealtimeClass(self, device)

	def __dataParse(self, device, data):
		advertisedName = getattr(device, 'name', None)
		if advertisedName is None:
			return

		try:
			dataBytes: bytes = data.manufacturer_data[1]
		except (KeyError, AttributeError, TypeError):
			pluginLog.error(f'{self.name}: invalid data: {data!r}')
			return

		# Some firmware glues an INTELLI_ROCKS beacon onto the payload; both of
		# the repo's real captures carry it. Upstream strips it before parsing.
		dataBytes = trim_payload(dataBytes)

		identity = self.device.alias if self.device is not None else advertisedName

		results = {
			'timestamp': now().timestamp(),
			'type': f'BLE{str(type(data).__name__)}',
			'rssi': int(getattr(data, 'rssi', 0)),
			'deviceName': str(advertisedName),
			'deviceAddress': str(getattr(device, 'address', '')),
			# Consumed by the schema's identityKey.
			'deviceIdentity': identity,
		}
		for field, parser in self.__parsers.items():
			try:
				results.update(parser(dataBytes))
			except Exception as e:
				pluginLog.error(f'{self.name}: could not read {field} from {dataBytes.hex()}: {e}')

		# Pass the identity explicitly rather than letting the datagram
		# discover it: we know exactly which device this came from, and
		# discovery was picking up the *previous* device's value.
		datagram = LevityDatagram(
			results, schema=self.schema, dataMaps=self.schema.dataMaps,
			identity=identity,
		)
		# Never let the diagnostic break delivery: this line used to index
		# datagram['realtime'] directly, so a datagram without that group
		# raised KeyError *before* the update below ever ran - a log statement
		# silently costing the device all of its data.
		if 'realtime' in datagram:
			pluginLog.verbose(f'{self.name} received: {datagram["realtime"]}', verbosity=5)
		else:
			pluginLog.warning(f'{self.name}: datagram carries no realtime group; keys: {sorted(map(str, datagram))}')
		self.realtime.update(datagram)
		self.lastDatagram = datagram


__plugin__ = Govee


class NoDevice(Exception):
	pass
