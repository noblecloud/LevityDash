from datetime import datetime, timedelta
import asyncio

from bleak import BleakScanner
import WeatherUnits as wu

from src.plugins.translator import LevityDatagram, TranslatorSpecialKeys as tsk
from src.plugins.plugin import ScheduledEvent
from src.plugins.web.rest import REST
from src import config

# from src.plugins import Plugins

__all__ = ["Govee"]


class Govee(REST, realtime=True, logged=True):
	name = 'Govee'
	translator = {
		'timestamp':                      {'type': 'datetime', 'sourceUnit': 'epoch', 'title': 'Time', 'sourceKey': 'timestamp', tsk.metaData: True},
		'indoor.temperature.temperature': {'type': 'temperature', 'sourceUnit': 'c', 'title': 'Temperature', 'sourceKey': 'temperature'},
		'indoor.temperature.dewpoint':    {'type': 'temperature', 'sourceUnit': 'c', 'title': 'Dew Point', 'sourceKey': 'dewPoint'},
		'indoor.temperature.heatIndex':   {'type': 'temperature', 'sourceUnit': 'c', 'title': 'Heat Index', 'sourceKey': 'heatIndex'},
		'indoor.humidity.humidity':       {'type': 'humidity', 'sourceUnit': '%', 'title': 'Humidity', 'sourceKey': 'humidity'},
		'indoor.device.battery':          {'type': 'battery', 'sourceUnit': '%%', 'title': 'Battery', 'sourceKey': 'battery'},
		'@type':                          {'sourceKey': 'type', tsk.metaData: True},
		'@timezone':                      {'default': {'value': config.tz}, tsk.metaData: True},

		'dataMaps':                       {
			'ble': {
				'realtime': ()
			}
		}
	}

	def __init__(self):
		super().__init__()
		self.__enabled = False
		self.name = "GoveeH5101BLE"
		self.scanner = BleakScanner()
		self.scanner.register_detection_callback(self.dataParse)
		self.scanner._service_uuids = [self.getConfig()['device']]
		self.temperature = wu.Temperature.Celsius(20)
		self.humidity = wu.Humidity(50)
		self.battery = wu.Percentage(50)

	def start(self):
		asyncio.create_task(self.run())
		self.historicalTimer = ScheduledEvent(timedelta(minutes=1), self.logValues)
		self.historicalTimer.start(False)

	async def run(self):
		await self.scanner.start()
		while True:
			await asyncio.sleep(0.1)
		await self.scanner.stop()

	def dataParse(self, device, temperatureHumidityData):
		if "GVH" in str(temperatureHumidityData.local_name) and temperatureHumidityData.manufacturer_data:
			data = temperatureHumidityData.manufacturer_data[1].hex().upper()
			temperatureHumidityData = data[4:10]
			battery = int(data[10:12], 16)
			temperature = int(temperatureHumidityData, 16)/10000
			humidity = int(temperatureHumidityData, 16)%1000/10
			self.setData(temperature, humidity, battery)

	def setData(self, temperature: wu.Temperature.Celsius, humidity: wu.Humidity, battery: wu.Percentage):
		data = {
			'timestamp':   datetime.now().timestamp(),
			'type':        'ble',
			'temperature': temperature,
			'humidity':    humidity,
			'battery':     battery
		}
		data = LevityDatagram(data, translator=self.translator, dataMaps=self.translator.dataMaps, sourceData={'@source': 'ble'}, metaData={'@type': 'ble'})
		self.realtime.update(data)


__plugin__ = Govee
