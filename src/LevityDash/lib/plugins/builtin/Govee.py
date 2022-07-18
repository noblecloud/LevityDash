import asyncio
from datetime import timedelta
from types import FunctionType
from typing import Callable, Dict, Optional, Union
from uuid import UUID
import re

from bleak import BleakScanner
from bleak.backends.device import BLEDevice

from LevityDash.lib.log import LevityPluginLog

from LevityDash.lib.plugins.plugin import Plugin
from LevityDash.lib.plugins.utils import ScheduledEvent
from LevityDash.lib.plugins.schema import LevityDatagram, Schema, SchemaSpecialKeys as tsk
from LevityDash.lib.utils.shared import getOr, now
from qasync import asyncClose

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
	exec(compile(funcString, "<string>", "exec"))
	return locals()[functionName]


class BLEPayloadParser:
	def __init__(self, field: str, startingByte: int, endingByte: int, expression: Optional[Union[str, Callable]] = None, base: int = 16):
		self.__field = field
		self.__startingByte = startingByte
		self.__endingByte = endingByte
		self.__expression = expression
		self.__base = base
		match expression:
			case FunctionType():
				self.__expression = expression
			case str():
				self.__expression = parseMathString(expression)

	def __call__(self, payload: bytes) -> dict[str, float | int]:
		payload = int(payload.hex().upper()[self.__startingByte: self.__endingByte], self.__base)
		if self.__expression is not None:
			value = self.__expression(payload)
		else:
			value = payload
		return {self.__field: value}


loop = asyncio.get_event_loop()

class Govee(Plugin, realtime=True, logged=True):
	name = 'Govee'
	schema: Schema = {
		'timestamp':                      {'type': 'datetime', 'sourceUnit': 'epoch', 'title': 'Time', 'sourceKey': 'timestamp', tsk.metaData: True},
		'indoor.temperature.temperature': {'type': 'temperature', 'sourceUnit': 'c', 'title': 'Temperature', 'sourceKey': 'temperature'},
		'indoor.temperature.dewpoint':    {'type': 'temperature', 'sourceUnit': 'c', 'title': 'Dew Point', 'sourceKey': 'dewpoint'},
		'indoor.temperature.heatIndex':   {'type': 'temperature', 'sourceUnit': 'c', 'title': 'Heat Index', 'sourceKey': 'heatIndex'},
		'indoor.humidity.humidity':       {'type': 'humidity', 'sourceUnit': '%h', 'title': 'Humidity', 'sourceKey': 'humidity'},
		'indoor.@deviceName.battery':     {'type': 'battery', 'sourceUnit': '%bat', 'title': 'Battery', 'sourceKey': 'battery'},
		'indoor.@deviceName.rssi':        {'type': 'rssi', 'sourceUnit': 'rssi', 'title': 'Signal', 'sourceKey': 'rssi'},
		'@type':                          {'sourceKey': 'type', tsk.metaData: True, tsk.sourceData: True},
		'@deviceName':                    {'sourceKey': 'deviceName', tsk.metaData: True, tsk.sourceData: True},
		'@deviceAddress':                 {'sourceKey': 'deviceAddress', tsk.metaData: True, tsk.sourceData: True},
		# '@timezone':                      {'default': {'value': config.tz}, tsk.metaData: True},

		'dataMaps':                       {
			'BLEAdvertisementData': {
				'realtime': ()
			}
		}
	}

	def __init__(self):
		super().__init__()
		self.__running = False
		self.lastDatagram: Optional[LevityDatagram] = None
		self.historicalTimer: ScheduledEvent | None = None
		self.scannerTask = None
		try:
			self.__readConfig()
		except Exception as e:
			raise e

	async def __init_device__(self):
		config = self.config
		deviceConfig = self.__readDeviceConfig(config)
		device = deviceConfig['id']
		match device:
			case str() if self._varifyDeviceID(device):
				self.scanner = BleakScanner(service_uuids=(device,))
			case str() if ',' in device and (devices := tuple([i for i in device.split(',') if self._varifyDeviceID(i)])):
				self.scanner = BleakScanner(service_uuids=devices)
			case _:
				device = None
				__scanAttempts = 0
				self.scanner = BleakScanner()

				while device is None:
					scanTime = min(5*max(__scanAttempts, 1), 60)
					try:
						pluginLog.info(f"Scanning for Govee devices for {scanTime} seconds")
						device = await self.__discoverDevice(deviceConfig, timeout=scanTime)
					except NoDevice:
						__scanAttempts += 1
						if __scanAttempts > 10:
							raise NoDevice(f'No device found after scanning for {scanTime} and {__scanAttempts} attempts')
						pluginLog.warning(f"Unable to find device matching config {deviceConfig} after scanning for {scanTime}...")
					except RuntimeError:
						__scanAttempts += 1
						if __scanAttempts > 10:
							raise NoDevice(f'No device found after scanning for {scanTime} and {__scanAttempts} attempts')
						pluginLog.warning(f"Unable to find device matching config {deviceConfig} after scanning for {scanTime}...")

				try:
					self.scanner.register_detection_callback(None)
					await self.scanner.stop()
					delattr(self, 'scanner')
				except Exception as e:
					pass
				self.scanner = BleakScanner(service_uuids=tuple(device.metadata['uuids']))
				name = f'GoveeBLE [{device.name}]'
				self.name = name
				self.config[name]['device.name'] = str(device.name)
				self.config[name]['device.uuid'] = f"{', '.join(device.metadata['uuids'])}"
				self.config[name]['device.address'] = str(device.address)
				self.config.defaults().pop('device.id', None)
				self.config.defaults().pop('device.mac', None)
				self.config.defaults().pop('device.model', None)
				self.config.save()
		self.scanner.register_detection_callback(self.__dataParse)
		pluginLog.info(f'{self.name} initialized for device {device}')

	@classmethod
	def _validateConfig(cls, cfg) -> bool:
		results = dict()
		results['enabled'] = 'enabled' in cfg and cfg['enabled']
		expectedIDStrings = ('uuid', 'id', 'mac', 'address', 'name')
		expectedIDStrings = {*expectedIDStrings, *[f'device.{i}' for i in expectedIDStrings]}
		availableIDKeys = expectedIDStrings & cfg.keys()
		results['device'] = any(cfg[i] for i in availableIDKeys)
		return all(results.values())

	def __readConfig(self):
		pluginConfig = self.config

		def getValues(key) -> Dict[str, Union[str, int, float, Callable]]:
			params = {'field': key}
			if f'{key}.slice' in pluginConfig:
				params['startingByte'], params['endingByte'] = [int(i) for i in re.findall(r'\d+', pluginConfig[f'{key}.slice'])]
			if f'{key}.expression' in pluginConfig:
				params['expression'] = pluginConfig[f'{key}.expression']
			if f'{key}.base' in pluginConfig:
				params['base'] = int(pluginConfig[f'{key}.base'])
			return params

		self.__temperatureParse = BLEPayloadParser(**getValues('temperature'))
		self.__humidityParse = BLEPayloadParser(**getValues('humidity'))
		self.__batteryParse = BLEPayloadParser(**getValues('battery'))

		return pluginConfig

	@staticmethod
	def _varifyDeviceID(deviceID: str) -> bool:
		reMac = r'((?:(\d{1,2}|[a-fA-F]{1,2}){2})(?::|-*)){6}'
		reUUID = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-5][0-9a-f]{3}-[089ab][0-9a-f]{3}-[0-9a-f]{12}'
		return bool(re.match(reMac, deviceID) or re.match(reUUID, deviceID))

	@staticmethod
	def __readDeviceConfig(config):
		deviceConfig = {
			"id":    getOr(config, "device.id", "device.uuid", "device.address", "id", "device", expectedType=str, default=None),
			"model": getOr(config, "model", "device.model", "type", "device.type", expectedType=str, default=None),
		}
		return {k: v for k, v in deviceConfig.items() if v is not None}

	def start(self):
		asyncio.create_task(self.asyncStart())

	async def asyncStart(self):
		pluginLog.info(f'{self.name} starting...')
		await self.run()

		if self.historicalTimer is None:
			self.historicalTimer = ScheduledEvent(timedelta(seconds=15), self.logValues).schedule()
		else:
			self.historicalTimer.schedule()

	@property
	def running(self) -> bool:
		return self.__running

	async def run(self):
		try:
			await self.__init_device__()
		except Exception as e:
			pluginLog.error(f'Error initializing device: {e}')
			return
		await self.scanner.start()
		pluginLog.info(f'{self.name} started!')
		self.__running = True

	def stop(self):
		if self.running:
			asyncio.create_task(self.asyncStop())

	async def asyncStop(self):
		pluginLog.info(f'{self.name} stopping...')
		self.__running = False
		try:
			self.scanner.register_detection_callback(None)
			await self.scanner.stop()
		except AttributeError:
			pass
		except Exception as e:
			pluginLog.error(f'Error stopping scanner: {e}')
		if self.historicalTimer is not None and self.historicalTimer.running:
			self.historicalTimer.stop()
		pluginLog.info(f'{self.name} stopped!')

	@asyncClose
	async def close(self):
		await self.asyncStop()

	def enabled(self) -> bool:
		return self.config['enabled']

	async def __discoverDevice(self, deviceConfig, timeout=15) -> Optional[BLEDevice]:
		async def discover(timeout):
			devices = await self.scanner.discover(timeout=timeout) or []
			return devices

		def genFilter(by: str, value: str, contains: bool = False):
			def filter(device, *_):
				return str(getattr(device, by, f'{hash(value)}')).lower() == f'{str(value).lower()}'

			def containsFilter(device, *_):
				return str(getattr(device, by, f'{hash(value)}')).lower().find(f'{str(value).lower()}') != -1

			return containsFilter if contains else filter

		match deviceConfig:
			case {'id': 'closest', 'model': model}:
				devices = await discover(timeout)
				filterFunc = genFilter('name', model, contains=True)
				device = found[0] if (found := sorted([device for device in devices if filterFunc(device)], key=lambda x: -x.rssi)) else None

			case {'id': 'first', 'model': str(model)} | {'model': str(model)}:
				device = await self.scanner.find_device_by_filter(genFilter('name', model, contains=True), timeout=timeout) or None

			case {'id': UUID(_id)}:
				device = await self.scanner.find_device_by_filter(genFilter('address', _id), timeout=timeout) or None

			case {'id': str(address)} if re.match("[0-9a-f]{2}([-:]?)[0-9a-f]{2}(\\1[0-9a-f]{2}){4}$", address.lower()):
				device = await self.scanner.find_device_by_filter(genFilter('address', address), timeout=timeout) or None

			case {'id': str(_id)}:
				device = await self.scanner.find_device_by_filter(lambda d, _: _id.lower() in str(d.name).lower(), timeout=timeout) or None

			case _:
				device = await self.scanner.find_device_by_filter(lambda d, _: 'gvh' in str(d.name).lower(), timeout=timeout) or None

		if device:
			pluginLog.info(f'Found device {device.name}')
			return device
		else:
			raise NoDevice(f'No device found for {deviceConfig}')

	def __dataParse(self, device, data):
		try:
			dataBytes: bytes = data.manufacturer_data[1]
		except KeyError:
			pluginLog.error(f'Invalid data: {data!r}')
		results = {
			'timestamp':     now().timestamp(),
			'type':          f'BLE{str(type(data).__name__)}',
			'rssi':          int(device.rssi),
			'deviceName':    str(device.name),
			'deviceAddress': str(device.address),
			**self.__temperatureParse(dataBytes),
			**self.__humidityParse(dataBytes),
			**self.__batteryParse(dataBytes),
		}
		data = LevityDatagram(results, schema=self.schema, dataMaps=self.schema.dataMaps)
		pluginLog.debug(f'{self.__class__.__name__} received: {data["realtime"]}')
		self.realtime.update(data)
		self.lastDatagram = data


__plugin__ = Govee


class NoDevice(Exception):
	pass
