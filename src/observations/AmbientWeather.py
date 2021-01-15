from observations import Observation
from translators import AWTranslator, AWTranslatorIndoor, AWTranslatorOutdoor


class AWObservation(Observation):
	_translator = AWTranslator()


class AWIndoor(Observation):
	_translator = AWTranslatorIndoor()


class AWOutdoor(Observation):
	_translator = AWTranslatorOutdoor()

# def __init__(self, data: SmartDictionary, t: SmartDictionary):
# 	tz = timezone(data[t.timezone])
# 	self._dateTime = datetime.fromtimestamp(int(data[t.time]) / 1e3, tz=tz)
# 	self._temperature = Temperature(data, t)
# 	self._humidity = Humidity(data, t)
# 	if hasattr(t, 'pressureRelative'):
# 		self._pressureRelative = Pressure(data[t.pressure], data[t.pressureRelative])
# 	else:
# 		self._pressure = Pressure(data[t.pressure])
#
# @property
# def datetime(self):
# 	return self._dateTime
#
# @property
# def temperature(self):
# 	return self._temperature
#
# @property
# def humidity(self):
# 	return self._humidity
#
# @property
# def pressure(self):
# 	return self._pressure

# class AWOutdoors(AWObservation):
# 	_light: Light
# 	_wind: Wind
# 	_precipitation: Precipitation
#
# 	def __init__(self, data, t: SmartDictionary):
# 		super().__init__(data, t)
#
# 		def tr(x):
# 			return data[getattr(t, x)]
#
# 		if hasattr(t, 'irradiance') and hasattr(t, 'uvi'):
# 			self._light = Light(data[t.irradiance], data[t.uvi])
#
# 		wind = Vector(data[t.windSpeed], data[t.windDirection])
# 		gust = Vector(data[t.gustSpeed], data[t.gustDirection])
# 		self._wind = Wind(wind, gust, data[t.windMax])
# 		self._precipitation = Precipitation(data[t.precipitationRate])
#
# 	@property
# 	def light(self):
# 		return self._light
#
# 	@property
# 	def wind(self):
# 		return self._wind
#
# 	@property
# 	def precipitation(self):
# 		return self._precipitation
#
