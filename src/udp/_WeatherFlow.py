from datetime import datetime

from units.length import Kilometer

ms = {
	  "serial_number": "AR-00004049",
	  "type":"evt_strike",
	  "hub_sn": "HB-00000001",
	  "evt":[1493322445,27,3848]
	}


class WF_UDPMessage:
	__slots__ = ['_serial', '_type', '_hub', '_time']
	_serial: str
	_type: str
	_hub: str
	_time: datetime


	def __init__(self, data):
		self._serial = data.pop('serial_number')
		self._type = data.pop('type')
		self._hub = data.pop('hub_sn')
		self._time = list(data.values())[-1].pop(0)

	def parse(self, data):
		pass

	@property
	def time(self) -> datetime:
		return datetime.strptime(self._time)


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


class WF_UDPLightning(WF_UDPEvent):
	__slots__ = ['_distance', '_energy']
	_distance: Kilometer
	_energy: int

	@property
	def event(self):
		return {'distance': self._distance, 'energy': self._energy}

	@property
	def message(self):
		return 'Lightning detected {} away'.format(self._distance)


if __name__ == '__main__':
	x = WF_UDPWind(ms)
