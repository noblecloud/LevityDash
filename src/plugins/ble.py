import sys
from datetime import datetime

import qasync
from functools import partial

import asyncio

from bleak import BleakScanner
import WeatherUnits as wu
from qasync import QApplication

from src.api import API, URLs
from src.observations import ObservationRealtime


class IndoorObservation(ObservationRealtime):
	subscriptionChannel = 'Govee Indoor'
	category = 'environment'
	_indoorOutdoor = True
	_translator = {
		'time.time':                      {'type': 'datetime', 'sourceUnit': 'epoch', 'title': 'Time', 'sourceKey': 'time'},
		'indoor.temperature.temperature': {'type': 'temperature', 'sourceUnit': 'c', 'title': 'Temperature', 'sourceKey': 'temperature'},
		'indoor.humidity.humidity':       {'type': 'humidity', 'sourceUnit': '%', 'title': 'Humidity', 'sourceKey': 'humidity'},
		'indoor.device.battery':          {'type': 'battery', 'sourceUnit': '%%', 'title': 'Battery', 'sourceKey': 'battery'},
	}


class BLEServices(URLs, realtime=False, forecast=False):
	base = ''
	device = '0000ec88-0000-1000-8000-00805f9b34fb'
	realtime = device


class GoveeH5101(API):
	_urls = BLEServices()
	_realtime: IndoorObservation
	name = 'Govee'

	def __init__(self):
		from src.dispatcher import endpoints
		super().__init__(mainEndpoint=endpoints)
		self.__enabled = False
		self._realtime = IndoorObservation(self)
		self._realtime._api = self
		self.endpoints.insert(self._realtime)
		self.name = "GoveeH5101BLE"
		self.scanner = BleakScanner()
		self.scanner.register_detection_callback(self.dataParse)
		self.scanner._service_uuids = ['0000ec88-0000-1000-8000-00805f9b34fb']
		self.temperature = wu.Temperature.Celsius(20)
		self.humidity = wu.Humidity(50)
		self.battery = wu.Percentage(50)

	async def run(self):
		await self.scanner.start()
		while True:
			await asyncio.sleep(0.1)
		await self.scanner.stop()

	async def enabled(self, value):
		if value:
			await self.run()
		else:
			self.scanner.clear()

	def dataParse(self, device, temperatureHumidityData):
		if "GVH" in str(temperatureHumidityData.local_name) and temperatureHumidityData.manufacturer_data:
			data = temperatureHumidityData.manufacturer_data[1].hex().upper()
			temperatureHumidityData = data[4:10]
			battery = int(data[10:12], 16)
			temperature = int(temperatureHumidityData, 16) / 10000
			humidity = int(temperatureHumidityData, 16) % 1000 / 10
			self.setData(temperature, humidity, battery)

	def setData(self, temperature: wu.Temperature.Celsius, humidity: wu.Humidity, battery: wu.Percentage):
		data = {
			'time':        datetime.now().timestamp(),
			'temperature': temperature,
			'humidity':    humidity,
			'battery':     battery
		}
		self.realtime.update(data)


async def initializeAsyncPlugin():
	t = GoveeH5101()
	await t.run()
