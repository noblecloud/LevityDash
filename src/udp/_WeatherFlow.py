from datetime import datetime
from units.heat import Celsius

# from units.length import Kilometer

ms = {
		"serial_number": "AR-00004049",
		"type":          "evt_strike",
		"hub_sn":        "HB-00000001",
		"evt":           [1493322445, 27, 3848]
}


class WF_UDPMessage:
	__slots__ = ['_serial', '_type', '_hub', '_time']
	_serial: str
	_type: str
	_hub: str
	_time: int

	def __init__(self, data):
		self._serial = data.pop('serial_number')
		self._type = data.pop('type')
		self._hub = data.pop('hub_sn')
		self._time = list(data.values())[-1].pop(0)

	def parse(self, data):
		pass

	@property
	def time(self) -> datetime:
		return datetime.fromtimestamp(self._time).strftime('%-H:%M:%S')


class WF_UDPRainStart(WF_UDPMessage):

	@property
	def message(self):
		return 'Rain started at {}'.format(self.time)


class WF_UDPEvent(WF_UDPMessage):

	def __init__(self, data):
		super().__init__(data)
		data = data.popitem()[1]
		names, types = zip(*self.__annotations__.items())
		for name, typeVar, value in zip(names, types, data):
			self.__setattr__(name, typeVar(value))


class WF_UDPWind(WF_UDPEvent):
	__slots__ = ['_speed', '_direction']
	_speed: str
	_direction: str

	@property
	def message(self):
		return '[{}]: Wind blowing at {} in {}'.format(self.time, self._speed, self._direction)


class WF_UDPObs_st(WF_UDPEvent):
	__slots__ = ['_lullSpeed', '_windSpeed', '_gustSpeed', '_windDirection',
	             '_windSampleInterval', '_pressure', '_temperature', '_humidity',
	             '_illuminance', '_uvi', '_irradiance', '_precipitationHourlyRaw',
	             '_precipitationType', '_lightningDistance', '_lightning',
	             '_battery', 'reportInterval']

	_lullSpeed: str
	_windSpeed: str
	_gustSpeed: str
	_windDirection: str
	_windSampleInterval: str
	_pressure: str
	_temperature: Celsius
	_humidity: str
	_illuminance: str
	_uvi: str
	_irradiance: str
	_precipitationHourlyRaw: str
	_precipitationType: str
	_lightningDistance: str
	_lightning: str
	_battery: str
	_reportInterval: str

	def __init__(self, data):
		data.pop('firmware_revision')
		WF_UDPMessage.__init__(self, data)
		data = self._time
		self._time = data.pop(0)
		names, types = zip(*self.__annotations__.items())
		for name, typeVar, value in zip(names, types, data):
			self.__setattr__(name, typeVar(value))

	@property
	def message(self):
		temperature = Celsius(self._temperature)
		return '[{}]: Currently {}º'.format(self.time.lower(), self._temperature.f)


class WF_UDPLightning(WF_UDPEvent):
	__slots__ = ['_distance', '_energy']
	_distance: int
	_energy: int


	@property
	def event(self):
		return {'distance': self._distance, 'energy': self._energy}

	@property
	def message(self):
		return 'Lightning detected {} away'.format(self._distance)


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
	BROADCAST_PORT = 37020
	sock_list = [create_broadcast_listener_socket(BROADCAST_IP, BROADCAST_PORT)]

	try:
		while True:
			sleep(.1)
			readable, writable, exceptional = select(sock_list, [], sock_list, 0)
			for s in readable:
				data, addr = s.recvfrom(4096)
				data = json.loads(data)
				if data['type'] == 'evt_precip':
					m = WF_UDPRainStart(data)
					print(m.message)
				if data['type'] == 'obs_st':
					m = WF_UDPObs_st(data)
					print(m.message)
				elif data['type'] == 'rapid_wind' and data['ob'][1]>0:
					m = WF_UDPWind(data)
					print(m.message)
				elif data['type'] not in ['hub_status', 'device_status', 'light_debug']:
					# print(data)
					pass
	except KeyboardInterrupt:
		pass
