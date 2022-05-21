import asyncio
from datetime import timedelta
from types import FunctionType
from typing import Callable, Dict, Optional, Union
from uuid import UUID
import re

from bleak import BleakScanner
from bleak.backends.device import BLEDevice

from LevityDash.lib.log import LevityPluginLog

from LevityDash.lib.plugins.plugin import Plugin, ScheduledEvent
from LevityDash.lib.plugins.schema import LevityDatagram, Schema, SchemaSpecialKeys as tsk
from LevityDash.lib.utils.shared import getOr, now

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


class Govee(Plugin, realtime=True, logged=True):
	name = 'Govee'
	schema: Schema = {
		'timestamp':                      {'type': 'datetime', 'sourceUnit': 'epoch', 'title': 'Time', 'sourceKey': 'timestamp', tsk.metaData: True},
		'indoor.temperature.temperature': {'type': 'temperature', 'sourceUnit': 'c', 'title': 'Temperature', 'sourceKey': 'temperature'},
		'indoor.temperature.dewpoint':    {'type': 'temperature', 'sourceUnit': 'c', 'title': 'Dewpoint', 'sourceKey': 'dewpoint'},
		'indoor.temperature.heatIndex':   {'type': 'temperature', 'sourceUnit': 'c', 'title': 'Heat Index', 'sourceKey': 'heatIndex'},
		'indoor.humidity.humidity':       {'type': 'humidity', 'sourceUnit': '%', 'title': 'Humidity', 'sourceKey': 'humidity'},
		'indoor.@deviceName.battery':     {'type': 'battery', 'sourceUnit': '%%', 'title': 'Battery', 'sourceKey': 'battery'},
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

	__device: BLEDevice

	def __init__(self):
		super().__init__()
		self.__enabled = False
		try:
			self.__readConfig()
		except Exception as e:
			raise e

	async def __init_device__(self):
		config = self.config
		deviceConfig = self.__readDeviceConfig(config)
		device = deviceConfig['id']
		match device:
			case str() if self.__varifyDeviceID(device):
				self.scanner = BleakScanner(service_uuids=(device,))
			case str() if ',' in device and (devices := tuple([i for i in device.split(',') if self.__varifyDeviceID(i)])):
				self.scanner = BleakScanner(service_uuids=devices)
			case _:
				device = None
				__scanAttempts = 0
				self.scanner = BleakScanner()

				while device is None:
					try:
						device = await self.__discoverDevice(deviceConfig)
					except NoDevice:
						__scanAttempts += 1
						if __scanAttempts > 10:
							raise NoDevice(f'No device found after {__scanAttempts} attempts')
						pluginLog.warning(f"Unable to find device matching config {deviceConfig}... Retrying in 30 seconds")
						await asyncio.sleep(30)

				self.scanner._service_uuids = tuple(device.metadata['uuids'])
				self.name = f'GoveeBLE [{device.name}]'
				self.config['device.name'] = device.name
				self.config['device.uuid'] = f"{', '.join(device.metadata['uuids'])}"
				self.config._parser.save()
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

	def __varifyDeviceID(self, deviceID: str) -> bool:
		reMac = r'((?:(\d{1,2}|[a-fA-F]{1,2}){2})(?::|-*)){6}'
		reUUID = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-5][0-9a-f]{3}-[089ab][0-9a-f]{3}-[0-9a-f]{12}'
		return bool(re.match(reMac, deviceID) or re.match(reUUID, deviceID))

	@staticmethod
	def __readDeviceConfig(config):
		deviceConfig = {}
		deviceConfig['id'] = getOr(config, 'device.id', 'device.address', 'device.uuid', 'id', 'device', expectedType=str, default=None)
		deviceConfig['model'] = getOr(config, 'model', 'device.model', 'type', 'device.type', expectedType=str, default=None)
		return {k: v for k, v in deviceConfig.items() if v is not None}

	def start(self):
		self.__enabled = True
		pluginLog.debug(f'{self.name} starting...')
		asyncio.create_task(self.run())
		pluginLog.info(f'{self.name} started!')
		self.historicalTimer = ScheduledEvent(timedelta(minutes=1), self.logValues)
		self.historicalTimer.start(False)
		self.__running = True

	async def run(self):
		try:
			await self.__init_device__()
		except Exception as e:
			pluginLog.error(f'Error initializing device: {e}')
			return
		await self.scanner.start()
		while self.__enabled:
			await asyncio.sleep(0.5)
		pluginLog.critical(f'{self.name} stopping...')
		await self.scanner.stop()

	def stop(self):
		self.__enabled = False

	async def __discoverDevice(self, deviceConfig, timeout=60) -> Optional[BLEDevice]:
		async def discover(timeout):
			devices = []
			for device in self.scanner.discover(timeout=timeout):
				devices.append(device)
			return devices

		def genFilter(by: str, value: str, contains: bool = False):
			def filter(device, _):
				return str(getattr(device, by, f'{hash(value)}')).lower() == f'{str(value).lower()}'

			def containsFilter(device, _):
				return str(getattr(device, by, f'{hash(value)}')).lower().find(f'{str(value).lower()}') != -1

			return containsFilter if contains else filter

		match deviceConfig:
			case {'id': 'closest', 'model': model}:
				devices = await discover(timeout)
				device = found[0] if (found := [device for device in devices if genFilter('name', model, contains=True)]) else None

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
		dataBytes: bytes = data.manufacturer_data[1]
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


__plugin__ = Govee


class NoDevice(Exception):
	pass
