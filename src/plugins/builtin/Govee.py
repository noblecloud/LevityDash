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
