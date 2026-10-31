"""Fake weather feeds for the soak test: OpenMeteo and PirateWeather over local HTTP, and two Govee sensors.

Stdlib + aiohttp only (no ``LevityDash`` import at module level), so a soak child can import it before the app.

Every value is a smooth, deterministic function of the epoch second (diurnal swing, a slow weather wave, a
sun-angle for radiation), so two fetches agree where they overlap, the data is the same on every run, and a
check can recompute what a graph *should* show. A forecast fetched at ``t`` carries a small revision error that
grows with lead time, the way a real one does, so a new fetch replaces old points with slightly different ones.

The servers read the (warped) clock through ``time.time()``, so they must run inside a process that has
``timewarp`` installed. They answer the request the real plugin sends: columns for exactly the ``hourly=`` and
``daily=`` fields it asks for (Open-Meteo), and the Dark Sky shape with ``extend=hourly`` (PirateWeather).
"""
import asyncio
import math
import sys
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

LAT, LON = 40.7128, -74.0060
_T0 = time.time()


# --- the weather ----------------------------------------------------------------------------------------------

def sunElevation(t: float, lat: float = LAT, lon: float = LON) -> float:
	"""Solar elevation in degrees at epoch ``t``."""
	dt = datetime.fromtimestamp(t, timezone.utc)
	day = dt.timetuple().tm_yday
	decl = math.radians(23.44) * math.sin(2 * math.pi * (284 + day) / 365)
	hours = dt.hour + dt.minute / 60 + dt.second / 3600
	hourAngle = math.radians(15 * (hours - 12) + lon)
	la = math.radians(lat)
	return math.degrees(math.asin(math.sin(la) * math.sin(decl) + math.cos(la) * math.cos(decl) * math.cos(hourAngle)))


def _wave(t: float, periodHours: float, phase: float) -> float:
	return math.sin(2 * math.pi * (t / 3600 / periodHours) + phase)


def truth(t: float, revision: float = 0.0, lead: float = 0.0) -> dict:
	"""The weather at epoch ``t`` in SI-ish units. ``revision`` (a fetch-time seed) and ``lead`` (hours ahead of
	that fetch) add the forecast error."""
	err = lead / 24 * _wave(revision, 29.0, t / 9000)
	elev = sunElevation(t)
	day = max(0.0, math.sin(math.radians(elev)))
	synoptic = _wave(t, 103.0, 0.4) * 5.5 + _wave(t, 41.0, 2.1) * 2.0
	diurnal = _wave(t - 9 * 3600, 24.0, 0.0) * 4.5
	temp = 13.0 + synoptic + diurnal + err * 1.5
	storm = max(0.0, _wave(t, 103.0, 3.1) * _wave(t, 29.0, 0.7))
	cloud = min(100.0, max(0.0, 45 + 40 * _wave(t, 53.0, 1.3) + 80 * storm + err * 8))
	rain = max(0.0, (storm - 0.35) * 14) if storm > 0.35 else 0.0
	humidity = min(99.0, max(22.0, 62 - 2.2 * diurnal + 0.35 * cloud + 6 * _wave(t, 37.0, 0.2) + err * 3))
	dew = temp - (100 - humidity) / 5
	wind = max(0.4, 12 + 9 * _wave(t, 31.0, 0.9) + 8 * storm + err * 2)
	return {
		'temp': temp, 'dew': dew, 'humidity': humidity,
		'feels': temp - 0.07 * wind + 0.02 * (humidity - 50),
		'pressure': 1014 + 9 * _wave(t, 103.0, 1.9) - 7 * storm + err * 1.2,
		'cloud': cloud, 'rain': rain, 'wind': wind, 'gust': wind * 1.6 + 3, 'bearing': (200 + 90 * _wave(t, 61.0, 0.5)) % 360,
		'elev': elev, 'day': day, 'swr': 880 * day * (1 - 0.75 * cloud / 100), 'uvi': 5.5 * day * (1 - 0.7 * cloud / 100),
		'visibility': max(1.0, 16 - 0.1 * humidity + 4 * (1 - cloud / 100) - 6 * min(1, rain)),
	}


def wmoCode(w: dict) -> int:
	if w['rain'] > 6:
		return 65
	if w['rain'] > 2:
		return 63
	if w['rain'] > 0.1:
		return 61
	return 0 if w['cloud'] < 20 else 1 if w['cloud'] < 50 else 2 if w['cloud'] < 80 else 3


def _soil(w: dict, depth: float, t: float) -> float:
	return 0.18 + 0.012 * depth ** 0.5 + 0.03 * _wave(t, 240.0, depth)


def openMeteoHourly(name: str, t: float, w: dict) -> float:
	table = {
		'temperature_2m': w['temp'], 'relativehumidity_2m': w['humidity'], 'dewpoint_2m': w['dew'],
		'apparent_temperature': w['feels'], 'pressure_msl': w['pressure'], 'surface_pressure': w['pressure'] - 1.1,
		'cloudcover': w['cloud'], 'cloudcover_low': w['cloud'] * 0.6, 'cloudcover_mid': w['cloud'] * 0.8, 'cloudcover_high': w['cloud'] * 0.5,
		'windspeed_10m': w['wind'], 'windspeed_80m': w['wind'] * 1.3, 'windspeed_120m': w['wind'] * 1.45, 'windspeed_180m': w['wind'] * 1.6,
		'winddirection_10m': w['bearing'], 'winddirection_80m': (w['bearing'] + 8) % 360, 'winddirection_120m': (w['bearing'] + 12) % 360,
		'winddirection_180m': (w['bearing'] + 17) % 360, 'windgusts_10m': w['gust'],
		'shortwave_radiation': w['swr'], 'direct_radiation': w['swr'] * 0.65, 'diffuse_radiation': w['swr'] * 0.35,
		'direct_normal_irradiance': w['swr'] * 0.9, 'precipitation': w['rain'], 'rain': w['rain'], 'showers': 0.0, 'snowfall': 0.0,
		'weathercode': wmoCode(w), 'snow_depth': 0.0, 'vapor_pressure_deficit': max(0.0, 0.6 * (1 - w['humidity'] / 100) * 2.5),
		'evapotranspiration': 0.2 * w['day'], 'freezinglevel_height': 2400 + 600 * _wave(t, 103.0, 0.0),
		'soil_temperature_0cm': w['temp'] + 1, 'soil_temperature_6cm': w['temp'] + 0.5, 'soil_temperature_18cm': w['temp'] * 0.9 + 1,
		'soil_temperature_54cm': 12 + 0.2 * w['temp'], 'soil_moisture_0_1cm': _soil(w, 0.5, t), 'soil_moisture_1_3cm': _soil(w, 2, t),
		'soil_moisture_3_9cm': _soil(w, 6, t), 'soil_moisture_9_27cm': _soil(w, 18, t), 'soil_moisture_27_81cm': _soil(w, 54, t),
	}
	return round(table.get(name, 0.0), 2)


def _riseSet(day: datetime) -> tuple[float, float]:
	"""Sunrise and sunset epoch seconds for the local calendar day starting at ``day``."""
	start = day.timestamp()
	rise = set_ = start
	previous = sunElevation(start)
	for minute in range(1, 24 * 60 + 1):
		t = start + minute * 60
		now_ = sunElevation(t)
		if previous < 0 <= now_:
			rise = t
		elif previous >= 0 > now_:
			set_ = t
		previous = now_
	return rise, set_


def openMeteo(query: dict, now: float | None = None) -> dict:
	"""The JSON body of ``/v1/forecast`` for ``query`` (the parsed query string)."""
	now = time.time() if now is None else now
	zone = ZoneInfo(query.get('timezone') or 'UTC')
	pastDays, forecastDays = int(query.get('past_days', 0)), int(query.get('forecast_days', 7))
	revision = round(now / 900)
	today = datetime.fromtimestamp(now, zone).replace(hour=0, minute=0, second=0, microsecond=0)
	first = (today - timedelta(days=pastDays)).timestamp()
	hours = (pastDays + forecastDays) * 24
	times = [first + h * 3600 for h in range(hours)]

	hourly = {'time': [datetime.fromtimestamp(t, zone).strftime('%Y-%m-%dT%H:%M') for t in times]}
	samples = [truth(t, revision, max(0.0, (t - now) / 3600)) for t in times]
	for name in filter(None, query.get('hourly', '').split(',')):
		hourly[name] = [openMeteoHourly(name, t, w) for t, w in zip(times, samples)]

	daily = {'time': []}
	rows = []
	for d in range(pastDays + forecastDays):
		day = today - timedelta(days=pastDays) + timedelta(days=d)
		day = datetime(day.year, day.month, day.day, tzinfo=zone)
		daily['time'].append(day.strftime('%Y-%m-%d'))
		idx = [i for i, t in enumerate(times) if datetime.fromtimestamp(t, zone).date() == day.date()]
		rows.append((day, idx))
	for name in filter(None, query.get('daily', '').split(',')):
		column = []
		for day, idx in rows:
			ws = [samples[i] for i in idx] or [truth(day.timestamp())]
			if name == 'sunrise':
				column.append(datetime.fromtimestamp(_riseSet(day)[0], zone).strftime('%Y-%m-%dT%H:%M'))
			elif name == 'sunset':
				column.append(datetime.fromtimestamp(_riseSet(day)[1], zone).strftime('%Y-%m-%dT%H:%M'))
			elif name == 'weathercode':
				column.append(max(wmoCode(w) for w in ws))
			elif name == 'temperature_2m_max':
				column.append(round(max(w['temp'] for w in ws), 1))
			elif name == 'temperature_2m_min':
				column.append(round(min(w['temp'] for w in ws), 1))
			elif name == 'apparent_temperature_max':
				column.append(round(max(w['feels'] for w in ws), 1))
			elif name == 'apparent_temperature_min':
				column.append(round(min(w['feels'] for w in ws), 1))
			elif name == 'precipitation_sum':
				column.append(round(sum(w['rain'] for w in ws), 1))
			elif name == 'precipitation_hours':
				column.append(float(sum(1 for w in ws if w['rain'] > 0.1)))
			elif name == 'windspeed_10m_max':
				column.append(round(max(w['wind'] for w in ws), 1))
			elif name == 'windgusts_10m_max':
				column.append(round(max(w['gust'] for w in ws), 1))
			elif name == 'winddirection_10m_dominant':
				column.append(round(sum(w['bearing'] for w in ws) / len(ws)))
			elif name == 'shortwave_radiation_sum':
				column.append(round(sum(w['swr'] for w in ws) * 3600 / 1e6, 2))
			else:
				column.append(0.0)
		daily[name] = column
	return {
		'latitude': float(query.get('latitude', LAT)), 'longitude': float(query.get('longitude', LON)), 'generationtime_ms': 0.4,
		'utc_offset_seconds': int(datetime.fromtimestamp(now, zone).utcoffset().total_seconds()), 'timezone': zone.key,
		'timezone_abbreviation': datetime.fromtimestamp(now, zone).tzname(), 'elevation': 10.0,
		'hourly_units': {'time': 'iso8601'}, 'hourly': hourly, 'daily_units': {'time': 'iso8601'}, 'daily': daily,
	}


def _icon(w: dict, night: bool) -> str:
	if w['rain'] > 0.1:
		return 'rain'
	if w['cloud'] < 25:
		return 'clear-night' if night else 'clear-day'
	if w['cloud'] < 75:
		return 'partly-cloudy-night' if night else 'partly-cloudy-day'
	return 'cloudy'


def _pirateBlock(t: float, now: float) -> dict:
	w = truth(t, round(now / 900), max(0.0, (t - now) / 3600))
	return {
		'time': int(t), 'summary': 'Rain' if w['rain'] > 0.1 else 'Clear' if w['cloud'] < 25 else 'Cloudy', 'icon': _icon(w, w['elev'] < 0),
		'precipIntensity': round(w['rain'], 3), 'precipProbability': round(min(1.0, w['rain'] / 3 + (0.4 if w['cloud'] > 80 else 0)), 2),
		'precipIntensityError': 0.1, 'temperature': round(w['temp'], 2), 'apparentTemperature': round(w['feels'], 2),
		'dewPoint': round(w['dew'], 2), 'humidity': round(w['humidity'] / 100, 3), 'pressure': round(w['pressure'], 1),
		'windSpeed': round(w['wind'] / 3.6, 2), 'windGust': round(w['gust'] / 3.6, 2), 'windBearing': round(w['bearing']),
		'cloudCover': round(w['cloud'] / 100, 2), 'uvIndex': round(w['uvi'], 1), 'visibility': round(w['visibility'], 1),
		'ozone': 310.0, 'precipType': 'rain' if w['rain'] > 0.1 else 'none', 'windGustTime': int(t), 'uvIndexTime': int(t),
		'nearestStormDistance': 0 if w['rain'] > 0.1 else 80, 'nearestStormBearing': 0,
	}


def pirateWeather(now: float | None = None, zone: str = 'America/New_York') -> dict:
	"""The JSON body of ``/forecast/<key>/<lat>,<lon>?units=si&extend=hourly``."""
	now = time.time() if now is None else now
	tz = ZoneInfo(zone)
	currently = _pirateBlock(now, now)
	hourStart = int(now // 3600 * 3600)
	hourly = [_pirateBlock(hourStart + h * 3600, now) for h in range(168)]
	minutely = [
		{'time': int(now // 60 * 60 + m * 60), 'precipIntensity': currently['precipIntensity'], 'precipProbability': currently['precipProbability']}
		for m in range(61)
	]
	today = datetime.fromtimestamp(now, tz).replace(hour=0, minute=0, second=0, microsecond=0)
	daily = []
	for d in range(8):
		day = datetime(*(today + timedelta(days=d)).timetuple()[:3], tzinfo=tz)
		blocks = [_pirateBlock(day.timestamp() + h * 3600, now) for h in range(24)]
		temps = [b['temperature'] for b in blocks]
		apparent = [b['apparentTemperature'] for b in blocks]
		rise, set_ = _riseSet(day)
		at = lambda values, f: int(day.timestamp() + values.index(f(values)) * 3600)
		daily.append({
			'time': int(day.timestamp()), 'summary': 'Mixed', 'icon': blocks[12]['icon'],
			'sunriseTime': int(rise), 'sunsetTime': int(set_), 'moonPhase': round((day.timestamp() / 86400 / 29.53) % 1, 3),
			'precipIntensity': round(sum(b['precipIntensity'] for b in blocks) / 24, 3), 'precipProbability': 0.3,
			'precipIntensityMax': max(b['precipIntensity'] for b in blocks), 'precipIntensityMaxTime': int(day.timestamp() + 12 * 3600),
			'temperatureHigh': max(temps), 'temperatureHighTime': at(temps, max), 'temperatureLow': min(temps), 'temperatureLowTime': at(temps, min),
			'temperatureMax': max(temps), 'temperatureMaxTime': at(temps, max), 'temperatureMin': min(temps), 'temperatureMinTime': at(temps, min),
			'apparentTemperatureHigh': max(apparent), 'apparentTemperatureHighTime': at(apparent, max),
			'apparentTemperatureLow': min(apparent), 'apparentTemperatureLowTime': at(apparent, min),
			'apparentTemperatureMax': max(apparent), 'apparentTemperatureMaxTime': at(apparent, max),
			'apparentTemperatureMin': min(apparent), 'apparentTemperatureMinTime': at(apparent, min),
			'dewPoint': blocks[12]['dewPoint'], 'humidity': blocks[12]['humidity'], 'pressure': blocks[12]['pressure'],
			'windSpeed': blocks[12]['windSpeed'], 'windGust': blocks[12]['windGust'], 'windBearing': blocks[12]['windBearing'],
			'cloudCover': blocks[12]['cloudCover'], 'uvIndex': blocks[12]['uvIndex'], 'visibility': blocks[12]['visibility'], 'ozone': 310.0,
			'precipType': 'rain', 'windGustTime': int(day.timestamp()), 'uvIndexTime': int(day.timestamp() + 12 * 3600),
		})
	return {
		'latitude': LAT, 'longitude': LON, 'timezone': zone, 'offset': datetime.fromtimestamp(now, tz).utcoffset().total_seconds() / 3600,
		'currently': currently, 'minutely': {'summary': '', 'icon': currently['icon'], 'data': minutely},
		'hourly': {'summary': '', 'icon': currently['icon'], 'data': hourly}, 'daily': {'summary': '', 'icon': 'cloudy', 'data': daily},
		'flags': {'units': 'si'},
	}


# --- the HTTP server -------------------------------------------------------------------------------------------

class FeedServer:
	"""Serves both fakes on one port. ``requests`` counts hits per route; ``faultEvery`` turns every Nth request
	to a route into a 500, for exercising the plugins' error paths on purpose."""

	def __init__(self, host: str = '127.0.0.1', port: int = 0, faultEvery: int = 0):
		self.host, self.port, self.faultEvery = host, port, faultEvery
		self.requests = {'openmeteo': 0, 'pirateweather': 0}
		self._runner = None

	async def start(self) -> None:
		from aiohttp import web
		app = web.Application()
		app.router.add_get('/openmeteo/v1/forecast', self._openMeteo)
		app.router.add_get('/pirateweather/forecast/{key}/{where}', self._pirate)
		app.router.add_get('/stats', self._stats)
		self._runner = web.AppRunner(app, access_log=None)
		await self._runner.setup()
		site = web.TCPSite(self._runner, self.host, self.port)
		await site.start()
		self.port = site._server.sockets[0].getsockname()[1]

	async def stop(self) -> None:
		if self._runner is not None:
			await self._runner.cleanup()

	def _fault(self, route: str) -> bool:
		self.requests[route] += 1
		return bool(self.faultEvery) and self.requests[route] % self.faultEvery == 0

	async def _openMeteo(self, request):
		from aiohttp import web
		if self._fault('openmeteo'):
			return web.Response(status=500, text='injected fault')
		return web.json_response(openMeteo(dict(request.query)))

	async def _pirate(self, request):
		from aiohttp import web
		if self._fault('pirateweather'):
			return web.Response(status=500, text='injected fault')
		return web.json_response(pirateWeather())

	async def _stats(self, request):
		from aiohttp import web
		return web.json_response(self.requests)

	def redirects(self) -> dict:
		base = f'http://{self.host}:{self.port}'
		return {'api.open-meteo.com': f'{base}/openmeteo', 'api.pirateweather.net': f'{base}/pirateweather'}


def redirectAiohttp(redirects: dict) -> None:
	"""Send the plugins' requests for the real API hosts to the fake server."""
	import aiohttp
	original = aiohttp.ClientSession._request

	async def _request(self, method, str_or_url, **kwargs):
		url = str(str_or_url)
		for host, target in redirects.items():
			if host in url:
				url = target + url.split(host, 1)[1]
				break
		return await original(self, method, url, **kwargs)

	aiohttp.ClientSession._request = _request


# --- Govee -------------------------------------------------------------------------------------------------------

#: name -> (advertised name, address, baseline temp C, temp swing, baseline humidity %, humidity swing, battery %)
GOVEE_DEVICES = {
	'bedroom':   ('GVH5102_6736', '3A092DB0-D44A-91AC-6C1B-4C9C11A8A7A4', 21.0, 1.1, 42.0, 5.0, 83),
	'terrarium': ('GVH5102_527D', '76270FCE-FFB6-E857-54B3-48FA6B868D48', 24.5, 2.5, 78.0, 9.0, 96),
}


def goveePayload(alias: str, t: float) -> bytes:
	"""A 6 byte H5102 advertisement for ``alias`` at epoch ``t``: two flag bytes, a 3 byte big endian
	``tenthsOfDegree * 1000 + tenthsOfPercent`` and the battery percentage."""
	_, _, temp, tempSwing, hum, humSwing, battery = GOVEE_DEVICES[alias]
	temp += tempSwing * _wave(t - 8 * 3600, 24.0, 0.0) + 0.15 * _wave(t, 1.7, 0.3)
	hum += humSwing * _wave(t - 2 * 3600, 24.0, 2.0) + 0.5 * _wave(t, 2.3, 1.1)
	battery = max(5, int(battery - (t - _T0) / 86400 / 40))
	value = int(round(temp * 10)) * 1000 + int(round(hum * 10))
	return b'\x01\x01' + value.to_bytes(3, 'big') + bytes([battery])


class _FakeDevice:
	def __init__(self, name, address):
		self.name, self.address = name, address


class AdvertisementData:
	def __init__(self, name, payload):
		self.manufacturer_data = {1: payload}
		self.rssi = -60
		self.local_name = name


async def goveeFeed(periodSeconds: float = 10.0, devices=None) -> None:
	"""Dispatch an advertisement per device every ``periodSeconds`` of (warped) time, forever."""
	devices = devices or list(GOVEE_DEVICES)
	# Importing LevityDash.lib before the backend has initialised the app would build its config too early.
	while 'LevityDash.lib.plugins.ble' not in sys.modules:
		await asyncio.sleep(1)
	from LevityDash.lib.plugins.ble import shared_scanner
	while not shared_scanner.subscribers:
		await asyncio.sleep(1)
	while True:
		t = time.time()
		for alias in devices:
			name, address = GOVEE_DEVICES[alias][:2]
			shared_scanner.dispatch(_FakeDevice(name, address), AdvertisementData(name, goveePayload(alias, t)))
		await asyncio.sleep(periodSeconds)
