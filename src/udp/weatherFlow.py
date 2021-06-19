import logging
from datetime import datetime
import random

from WeatherUnits.defaults.WeatherFlow import *
from src import config

classAtlas = {
		'time':                   int,
		'lullSpeed':              'Wind',
		'windSpeed':              'Wind',
		'gustSpeed':              'Wind',
		'speed':                  'Wind',
		'direction':              Direction,
		'windDirection':          Direction,

		'windSampleInterval':     Second,
		'pressure':               mmHg,
		'temperature':            Celsius,
		'humidity':               Humidity,

		'illuminance':            Lux,
		'uvi':                    UVI,
		'irradiance':             RadiantFlux,

		'precipitationHourlyRaw': 'Precipitation',
		'precipitationType':      PrecipitationType,

		'distance':               Kilometer,
		'lightningDistance':      Kilometer,
		'lightning':              Strikes,
		'energy':                 int,

		'battery':                Voltage,
		'reportInterval':         Minute,
		'Wind':                   (Wind, Meter, Second),
		'Precipitation':          (Precipitation, Millimeter, Minute)
}


class UDPMessage(dict):
	messAtlas = {'serial': 'serial_number',
	             'type':   'type',
	             'hub':    'hub_sn',
	             'data':   ''}
	atlas = ['time']
	interval: int = 6

	def __init__(self, udpData):
		data = {key: udpData[value] for key, value in self.messAtlas.items()}
		data['data'] = self.convert(data['data'])
		t = data['data'].pop('time')
		data['time'] = datetime.fromtimestamp(int(t), config.tz)
		if 'interval' in data['data'].keys():
			UDPMessage.interval = data['data']['interval']

		super(UDPMessage, self).__init__(data)

	def convert(self, data):
		if isinstance(data[0], list):
			data = data[0]
		converted = {}
		for key, value in zip(self.atlas, data):
			newClass = classAtlas[key]
			if isinstance(newClass, str):
				newClass, nClass, dClass = classAtlas[newClass]
				n = nClass(value)
				d = dClass(UDPMessage.interval)
				newValue = newClass(n, d)
			else:
				newValue = newClass(value)
			try:
				converted[key] = newValue.localized
			except AttributeError:
				converted[key] = newValue
		# print(converted)
		# if 'speed' in converted.keys():
		# 	speed = Meter(random.random() + random.randrange(0, 5, 1))
		# 	direction = random.randrange(0, 359, 1)
		# 	converted['speed'] = Wind(speed, Second(1))
		# 	converted['direction'] = Direction(direction)
		return converted

	def __setitem__(self, *args):
		logging.error('UDP Messages are immutable')


class RainStart(UDPMessage):

	def __init__(self, udpData):
		self.messAtlas['data'] = 'evt'
		super().__init__(udpData)


class WindMessage(UDPMessage):

	def __init__(self, udpData):
		self.messAtlas['data'] = 'ob'
		self.atlas = [*self.atlas, 'speed', 'direction']
		super(WindMessage, self).__init__(udpData)
		delattr(self, 'atlas')


class Light(UDPMessage):
	"""
	I haven't quite figured out what this message contains.
	I am confident the item at index 2 is irradiance, but the
	item a index 1 alludes me.  It could be illuminance, but I
	can not figure out what the unit is.
	"""

	def __init__(self, udpData):
		self.messAtlas['data'] = 'ob'
		self.atlas = [*self.atlas, 'illuminance', 'irradiance', 'zero', 'zero']
		super(Light, self).__init__(udpData)
		delattr(self, 'atlas')


class Obs_st(UDPMessage):

	def __init__(self, udpData):
		self.messAtlas['data'] = 'obs'
		self.atlas = [*self.atlas, 'lullSpeed', 'windSpeed', 'gustSpeed', 'windDirection',
		              'windSampleInterval', 'pressure', 'temperature', 'humidity',
		              'illuminance', 'uvi', 'irradiance', 'precipitationHourlyRaw',
		              'precipitationType', 'lightningDistance', 'lightning',
		              'battery', 'reportInterval']
		super(Obs_st, self).__init__(udpData)


class Lightning(UDPMessage):

	def __init__(self, udpData):
		self.messAtlas['data'] = 'evt'
		self.atlas = [*self.atlas, 'distance', 'energy']
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
					m = Obs_st(data)
					print(m.message)
				elif data['type'] == 'rapid_wind' and data['ob'][1] > 0:
					m = WindMessage(data)
					print(m.message)
				elif data['type'] not in ['hub_status', 'device_status', 'light_debug']:
					# print(data)
					pass
	except KeyboardInterrupt:
		pass
