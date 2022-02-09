from src import logging
from datetime import datetime

from WeatherUnits import Measurement
from WeatherUnits.defaults.WeatherFlow import *
from src.translators.units import unitDict
from src.observations.weatherFlow import unitDefinitions
from src import config

log = logging.getLogger(__name__)


class UDPMessage(dict):
	messAtlas = {'device.status.deviceSerial': 'serial_number',
	             'metadata.type':              'type',
	             'device.status.hubSerial':    'hub_sn',
	             'data':                       'data'}
	atlas = ['time.time']
	interval: Time.Minute = 1

	def __init__(self, udpData):
		message = {key: udpData[value] for key, value in self.messAtlas.items()}
		data = message.pop('data', {})
		data = {**message, **{key: value for key, value in zip(self.atlas, data)}}
		data.pop('metadata.type', None)
		# if 'data' in data.keys():
		# 	data['data'] = self.convert(self.atlas, data['data'])
		# 	t = data['data'].pop('time')
		# 	data['time'] = datetime.fromtimestamp(int(t), config.tz)
		# 	if 'interval' in data['data'].keys():
		# 		UDPMessage.interval = data['data']['interval']
		# else:
		# 	data.pop('type')
		# 	dataNew = {}
		# 	for key, value in data.items():
		# 		cls = UDPClasses[key]
		# 		if issubclass(cls, Measurement):
		# 			t = unitDefinitions[key]
		# 			measurement = cls(value, title=t['title'], key=key)
		# 		else:
		# 			measurement = cls(value)
		# 		dataNew[key] = measurement
		# 	data = dataNew
		# 	data['time'] = datetime.fromtimestamp(int(data['time']), config.tz)
		# 	data['uptime'] = data['uptime'].day
		super(UDPMessage, self).__init__(data)

	def convert(self, atlas, data):
		if isinstance(data[0], list):
			data = data[0]
		converted = {}
		for key, value in zip(self.atlas, data):
			newClass = UDPClasses[key]
			if isinstance(newClass, str):
				t = unitDefinitions[key]
				newClass, nClass, dClass = UDPClasses[newClass]
				n = nClass(value)
				d = dClass(1)
				newValue = newClass(n, d, title=t['title'], key=key)
			else:
				if issubclass(newClass, Measurement):
					t = unitDefinitions[key]
					newValue = newClass(value, title=t['title'], key=key)
				else:
					newValue = newClass(value)
			if isinstance(newValue, Measurement):
				try:
					newValue = newValue.localize
				except AttributeError:
					log.debug(f'{newValue.withUnit} could not be localized')
			converted[key] = newValue
		return converted

	def __setitem__(self, *args):
		logging.error('UDP Messages are immutable')

	def __repr__(self):
		return f'{self.name}'

	def __str__(self):
		return f'{self.name}: {dict.__str__(self)}'

	@property
	def name(self):
		return self.__class__.__name__


class RainStart(UDPMessage):

	def __init__(self, udpData):
		self.messAtlas['data'] = 'evt'
		super().__init__(udpData)


class WindMessage(UDPMessage):

	def __init__(self, udpData):
		self.messAtlas['data'] = 'ob'
		self.atlas = [*self.atlas, 'environment.wind.speed.speed', 'environment.wind.direction.direction']
		super(WindMessage, self).__init__(udpData)


class Light(UDPMessage):
	"""
	I haven't quite figured out what this message contains.
	I am confident the item at index 2 is irradiance, but the
	item a index 1 alludes me.  It could be illuminance, but I
	can not figure out what the unit is.
	"""

	def __init__(self, udpData):
		self.messAtlas['data'] = 'ob'
		self.atlas = [*self.atlas, 'environment.light.illuminance', 'environment.light.irradiance', 'zero', 'zero']
		super(Light, self).__init__(udpData)
		delattr(self, 'atlas')


class TempestObservation(UDPMessage):

	def __init__(self, udpData):
		self.messAtlas['data'] = 'obs'
		self.atlas = [*self.atlas, 'environment.wind.speed.lull', 'environment.wind.speed.speed', 'environment.wind.speed.gust', 'environment.wind.direction.direction',
		              'device.sampleInterval.wind', 'environment.pressure.pressure', 'environment.temperature.temperature', 'environment.humidity.humidity',
		              'environment.light.illuminance', 'environment.light.uvi', 'environment.light.irradiance', 'environment.precipitation.precipitation',
		              'environment.precipitation.type', 'environment.lightning.distance', 'environment.lightning.lightning',
		              'device.status.battery', 'device.sampleInterval.report']
		udpData['obs'] = udpData['obs'][0]
		super(TempestObservation, self).__init__(udpData)


class DeviceStatus(UDPMessage):
	messAtlas = {
		'device.status.deviceSerial': 'serial_number',
		'metadata.type':              'type',
		'device.status.hubSerial':    'hub_sn',
		'time.time':                  'timestamp',
		'device.status.uptime':       'uptime',
		'device.status.battery':      'voltage',
		'device.status.firmware':     'firmware_revision',
		'device.status.deviceRSSI':   'rssi',
		'device.status.hubRSSI':      'hub_rssi',
		'device.status.sensorStatus': 'sensor_status',
		'device.status.debug':        'debug'
	}

	def __init__(self, udpData):
		self.atlas = []
		super(DeviceStatus, self).__init__(udpData)


class HubStatus(UDPMessage):
	messAtlas = {'device.status.hubSerial':  'serial_number',
	             'metadata.type':            'type',
	             'time.time':                'timestamp',
	             'device.status.uptime':     'uptime',
	             'device.status.firmware':   'firmware_revision',
	             'device.status.hubRSSI':    'rssi',
	             'device.status.resetFlags': 'reset_flags'
	             }

	def __init__(self, udpData):
		self.atlas = []
		super(HubStatus, self).__init__(udpData)


class Lightning(UDPMessage):

	def __init__(self, udpData):
		self.messAtlas['data'] = 'evt'
		self.atlas = [*self.atlas, 'environment.lightning.distance', 'environment.lightning.energy']
		super(Lightning, self).__init__(udpData)
		delattr(self, 'atlas')


if __name__ == '__main__':

	import struct
	import json
	from time import sleep
	from select import select
	from socket import AF_INET, INADDR_ANY, inet_aton, IP_ADD_MEMBERSHIP, IPPROTO_UDP, IPPROTO_IP, SOCK_DGRAM, SOL_SOCKET, SO_REUSEADDR, socket


	# create broadcast listener socket
	def create_broadcast_listener_socket(broadcast_ip, broadcast_port):

		b_sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP)
		b_sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)

		b_sock.bind(('', broadcast_port))

		mreq = struct.pack("4sl", inet_aton(broadcast_ip), INADDR_ANY)
		b_sock.setsockopt(IPPROTO_IP, IP_ADD_MEMBERSHIP, mreq)

		return b_sock


	BROADCAST_IP = '239.255.255.250'
	BROADCAST_PORT = 50222
	sock_list = [create_broadcast_listener_socket(BROADCAST_IP, BROADCAST_PORT)]

	try:
		while True:
			sleep(.1)
			readable, writable, exceptional = select(sock_list, [], sock_list, 0)
			for s in readable:
				data, addr = s.recvfrom(4096)
				data = json.loads(data)
				if data['type'] == 'evt_precip':
					m = RainStart(data)
					print(m.message)
				if data['type'] == 'obs_st':
					m = TempestObservation(data)
					print(m.message)
				elif data['type'] == 'rapid_wind' and data['ob'][1] > 0:
					m = WindMessage(data)
					print(m.message)
				elif data['type'] not in ['hub_status', 'device_status', 'light_debug']:
					# print(data)
					pass
	except KeyboardInterrupt:
		pass
