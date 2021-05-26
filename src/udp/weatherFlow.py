import logging
from datetime import datetime

# from units.length import Kilometer
from src import config
from units.defaults.weatherFlow import *

classAtlas = {
		'time':                   int,
		'lullSpeed':              Wind,
		'windSpeed':              Wind,
		'gustSpeed':              Wind,
		'speed':                  Wind,
		'direction':              int,
		'windDirection':          int,

		'windSampleInterval':     Second,
		'pressure':               mmHg,
		'temperature':            Heat,
		'humidity':               Humidity,

		'illuminance':            Lux,
		'uvi':                    int,
		'irradiance':             RadiantFlux,
		'precipitationHourlyRaw': Precipitation,

		'precipitationType':      PrecipitationType,
		'distance':               Kilometer,
		'lightningDistance':      Kilometer,
		'lightning':              int,
		'energy':                 int,

		'battery':                Volts,
		'reportInterval':         Minute

}


class UDPMessage(dict):
	messAtlas = {'serial': 'serial_number',
	             'type':   'type',
	             'hub':    'hub_sn',
	             'data':   ''}
	atlas = ['time']

	def __init__(self, udpData):
		data = {key: udpData[value] for key, value in self.messAtlas.items()}
		data['data'] = self.convert(data['data'])
		data['time'] = datetime.fromtimestamp(int(data['data'].pop('time')), config.tz)

		super(UDPMessage, self).__init__(data)

	def convert(self, data):
		if isinstance(data[0], list):
			data = data[0]
		converted = {}
		for key, value in zip(self.atlas, data):
			try:
				converted[key] = classAtlas[key](value).localized
			except AttributeError:
				converted[key] = classAtlas[key](value)
		return converted

	def __setitem__(self, *args):
		logging.error('UDP Messages are immutable')


class RainStart(UDPMessage):

	def __init__(self, udpData):
		self.messAtlas['data'] = 'evt'
		super().__init__(udpData)


class Wind(UDPMessage):

	def __init__(self, udpData):
		self.messAtlas['data'] = 'ob'
		self.atlas = [*self.atlas, 'speed', 'direction']
		super(Wind, self).__init__(udpData)
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
					m = Wind(data)
					print(m.message)
				elif data['type'] not in ['hub_status', 'device_status', 'light_debug']:
					# print(data)
					pass
	except KeyboardInterrupt:
		pass
