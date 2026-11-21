"""Aircraft near you, from a free ADS-B feed. Off by default, no account or key.

Publishes, every ``interval`` seconds, the ``slots`` aircraft nearest the ``[Location]`` in the main config
(or ``latitude``/``longitude`` below):

- ``aircraft.count``: how many are inside ``radius``, including those past the last slot.
- ``aircraft.near``: how many are inside ``trigger_radius`` (and under ``trigger_altitude``, when that is set).
- ``aircraft.active``: 1 while one is near, and for ``hold`` seconds after the last one leaves, else 0. It is what an
  item's ``when:`` reads, so a radar can stay hidden until something flies over:
  ``when: aircraft.active``. The hold keeps the radar from blinking as a plane slips in and out of the radius.
- ``aircraft.N.callsign``, ``.type`` (``B738``), ``.category`` (the ADS-B emitter category, ``A3``) and
  ``.registration`` for N = 1 to ``slots``: text. The radar draws a silhouette from the type and the category.
- ``aircraft.N.bearing``: degrees clockwise from north, from you to it.
- ``aircraft.N.distance``: nautical miles from you.
- ``aircraft.N.altitude``: feet. ``aircraft.N.speed``: knots over the ground. ``aircraft.N.climb``: feet per
  minute, negative when descending. ``aircraft.N.heading``: degrees, the way it is flying.

Slot 1 is the nearest. A panel binds to a slot and never to an aircraft, so the ranking can change under it,
as with the Host plugin's process table. A slot nobody fills has an empty callsign, which is how a display tells
an empty slot from a plane on the same bearing as the last. ``plot: radar`` of ``type: polar`` reads these.

**It is off until you turn it on.** Set this in ``<config dir>/plugins/Aircraft.ini``, then restart:

	[plugin]
	enabled = True

	[Aircraft]
	source = adsb.fi
	radius = 50
	interval = 60
	fast_interval = 5
	adaptive = True
	lookout = 0
	speed_cap = 500
	slots = 20
	trigger_radius = 10
	trigger_altitude = 0
	max_altitude = 0
	military = True
	hold = 60

``trigger_radius`` is the distance in nautical miles that counts as overhead for ``aircraft.near`` and
``aircraft.active``, ``trigger_altitude`` a ceiling in feet (0 for none) and ``hold`` the seconds ``active`` stays 1
after the last plane leaves. ``max_altitude`` (feet, 0 for none) leaves out aircraft above it, so high airliners do
not show; ``military = True`` keeps military aircraft (ADS-B ``dbFlags``) at any altitude.

**The poll rate follows what is coming.** ``interval`` is the longest wait, the idle cadence, and ``fast_interval``
the shortest, used while a plane is inside ``radius``. Each fetch reads a wider ring than ``radius`` — ``lookout``,
or by default the distance a ``speed_cap`` knot aircraft covers in one idle interval (500 knots for 60 seconds is
8.3 miles beyond the radius), so nothing can cross in between two polls. Anything in that ring is timed by
``gap / closing speed``, where the closing speed is its ground speed times the cosine of the angle between its track
and its bearing, and the next fetch is a quarter of that time away, clamped between ``fast_interval`` and
``interval``. A jet 6 miles out closing head-on is polled in seconds; a plane crossing your view changes nothing.
``aircraft.nextCheck`` publishes the wait it chose, in seconds. ``adaptive = False`` polls at ``interval`` always.

``source`` is one of the public community feeds, ``adsb.fi`` (the default), ``adsb.lol`` or ``airplanes.live``, or
the URL of your own receiver's ``aircraft.json`` (dump1090, readsb, tar1090: ``http://pi.local:8080/data/aircraft.json``).
A receiver of your own returns what it hears, so ``radius`` then only trims. The public feeds ask for a request
every second or so at most; ``interval`` is held at 5 seconds or more for them. ``ground = True`` keeps
aircraft on the ground (they are dropped otherwise). ``latitude`` and ``longitude`` stand in for the main
config's location, for a feed over somewhere else.

They do not carry the same allowance, and that is what decides which one to use. ``adsb.fi`` answers 250 nautical
miles for one request a second, under terms of personal, non-commercial use that ask for credit to adsb.fi and a
link to its home page. ``adsb.lol`` allows 500 requests a day for an address, so a radar polling every 10 seconds
spends the whole day's cap inside two hours and then reads 429 until the window resets. ``airplanes.live``
answers 403 until the project has been cleared with them by email. When a feed does answer 429, the next try waits
for the reset it names rather than ``interval``, so a capped feed recovers on its own.

The public feeds are community run and carry no promise; the plugin logs a failed fetch once and keeps trying.
A scenario that defines a key wins over it, so renders stay repeatable.
"""
import asyncio
import json
import math
import os
import time
import urllib.request
from datetime import datetime
from typing import Any, Dict, List, Optional

from LevityDash.lib.config import userConfig
from LevityDash.lib.log import LevityPluginLog
from LevityDash.lib.plugins.ble import LifecyclePlugin
from LevityDash.lib.plugins.builtin.Fixture import buildSchema, ENV_VAR, loadScenario
from LevityDash.lib.plugins.schema import LevityDatagram

log = LevityPluginLog.getChild('Aircraft')

#: The most slots the schema declares. ``[Aircraft] slots`` picks how many are published, up to this.
SLOTS_MAX = 40
EARTH_RADIUS_NMI = 3440.065

#: The public feeds, each a URL template with ``{lat}``, ``{lon}`` and ``{radius}``. ``adsb.fi`` answers aircraft
#: around a point; the other two share the readsb ``/v2/point/{lat}/{lon}/{radius}`` shape.
FEEDS: Dict[str, str] = {
	'adsb.fi': 'https://opendata.adsb.fi/api/v3/lat/{lat}/lon/{lon}/dist/{radius}',
	'adsb.lol': 'https://api.adsb.lol/v2/point/{lat}/{lon}/{radius}',
	'airplanes.live': 'https://api.airplanes.live/v2/point/{lat}/{lon}/{radius}',
}
#: The public feeds' radius ceiling, in nautical miles.
RADIUS_MAX = 250

AIRCRAFT_KEYS: Dict[str, dict] = {
	'aircraft.count': dict(unit='int', title='Aircraft in range'),
	'aircraft.near': dict(unit='int', title='Aircraft overhead'),
	'aircraft.active': dict(unit='int', title='Aircraft overhead (hold)'),
	'aircraft.nextCheck': dict(unit='int', title='Next check (s)'),
}
for _n in range(1, SLOTS_MAX + 1):
	AIRCRAFT_KEYS.update({
		f'aircraft.{_n}.callsign': dict(unit='str', title='Callsign'),
		f'aircraft.{_n}.type': dict(unit='str', title='Type'),
		f'aircraft.{_n}.registration': dict(unit='str', title='Registration'),
		f'aircraft.{_n}.category': dict(unit='str', title='Category'),
		f'aircraft.{_n}.bearing': dict(unit='int', title='Bearing (degrees)'),
		f'aircraft.{_n}.distance': dict(unit='int', title='Distance (nmi)'),
		f'aircraft.{_n}.altitude': dict(unit='int', title='Altitude (ft)'),
		f'aircraft.{_n}.speed': dict(unit='int', title='Ground speed (kt)'),
		f'aircraft.{_n}.climb': dict(unit='int', title='Climb (ft/min)'),
		f'aircraft.{_n}.heading': dict(unit='int', title='Heading (degrees)'),
	})


def bearingDistance(lat: float, lon: float, toLat: float, toLon: float) -> tuple[float, float]:
	"""``(degrees clockwise from north, nautical miles)`` from the first point to the second, along the great circle."""
	p1, p2 = math.radians(lat), math.radians(toLat)
	dLon = math.radians(toLon - lon)
	y = math.sin(dLon) * math.cos(p2)
	x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dLon)
	bearing = (math.degrees(math.atan2(y, x)) + 360) % 360
	a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dLon / 2) ** 2
	return bearing, 2 * EARTH_RADIUS_NMI * math.asin(min(1.0, math.sqrt(a)))


def _number(value: Any) -> Optional[float]:
	if isinstance(value, bool) or not isinstance(value, (int, float)):
		return None
	return None if value != value else float(value)


def parseAircraft(data: dict, lat: float, lon: float, radius: float, ground: bool = False,
		maxAltitude: float = 0, military: bool = True) -> List[Dict[str, Any]]:
	"""The aircraft in a readsb-style reply (``ac`` from the public feeds, ``aircraft`` from a receiver), nearest first.

	Bearing and distance are worked out here from the position, so a receiver's file, which has neither, reads the
	same as a public feed. An aircraft with no position, or past ``radius``, is left out; so is one on the ground,
	unless ``ground``. ``maxAltitude`` (feet, 0 for none) drops aircraft above it, except military ones (the feeds'
	``dbFlags`` bit 0) while ``military`` is true. Pure, so a test can call it.
	"""
	rows = []
	for ac in (data.get('ac') if 'ac' in data else data.get('aircraft')) or []:
		if not isinstance(ac, dict):
			continue
		acLat, acLon = _number(ac.get('lat')), _number(ac.get('lon'))
		if acLat is None or acLon is None:
			continue
		altitude = ac.get('alt_baro', ac.get('altitude'))
		onGround = altitude == 'ground'
		if onGround and not ground:
			continue
		bearing, distance = bearingDistance(lat, lon, acLat, acLon)
		if distance > radius:
			continue
		if maxAltitude > 0 and not onGround:
			isMilitary = military and bool(int(_number(ac.get('dbFlags')) or 0) & 1)
			height = _number(altitude) or _number(ac.get('alt_geom')) or 0
			if height > maxAltitude and not isMilitary:
				continue
		climb = _number(ac.get('baro_rate', ac.get('geom_rate', ac.get('vert_rate'))))
		rows.append({
			'callsign': str(ac.get('flight') or '').strip() or str(ac.get('r') or ac.get('hex') or '?').strip(),
			'type': str(ac.get('t') or '').strip(),
			'registration': str(ac.get('r') or '').strip(),
			'category': str(ac.get('category') or '').strip(),
			'bearing': round(bearing, 1),
			'distance': round(distance, 1),
			'altitude': 0 if onGround else round(_number(altitude) or _number(ac.get('alt_geom')) or 0),
			'speed': round(_number(ac.get('gs')) or 0),
			'climb': round(climb or 0),
			'heading': round(_number(ac.get('track', ac.get('true_heading'))) or 0),
		})
	rows.sort(key=lambda row: row['distance'])
	return rows


def slotValues(rows: List[Dict[str, Any]], slots: int, previous: int = 0) -> Dict[str, Any]:
	"""``{key: value}`` for ``rows``: the count, and one slot of fields for each of the first ``slots``.

	``previous`` is how many slots the last reading filled; the ones this reading leaves empty are blanked once
	(empty callsign, zeros), so a display does not keep a plane that has gone.
	"""
	slots = max(0, min(SLOTS_MAX, slots))
	out: Dict[str, Any] = {'aircraft.count': len(rows)}
	for n in range(1, max(slots, 0) + 1):
		if n <= len(rows):
			for field, value in rows[n - 1].items():
				out[f'aircraft.{n}.{field}'] = value
		elif n <= previous:
			for field in ('callsign', 'type', 'registration', 'category'):
				out[f'aircraft.{n}.{field}'] = ''
			for field in ('bearing', 'distance', 'altitude', 'speed', 'climb', 'heading'):
				out[f'aircraft.{n}.{field}'] = 0
	return out


def overhead(rows: List[Dict[str, Any]], radius: float, ceiling: float = 0) -> int:
	"""How many of ``rows`` are inside ``radius`` nautical miles and, when ``ceiling`` is above 0, below it in feet."""
	return sum(1 for row in rows if row['distance'] <= radius and (ceiling <= 0 or row['altitude'] <= ceiling))


def holdActive(near: int, now: float, lastNear: Optional[float], hold: float) -> tuple[int, Optional[float]]:
	"""``(active, last time one was near)``: active while one is near and for ``hold`` seconds after. Pure."""
	if near > 0:
		return 1, now
	if lastNear is not None and now - lastNear < hold:
		return 1, lastNear
	return 0, lastNear


def closingSpeed(row: Dict[str, Any]) -> float:
	"""Knots toward you: ground speed times the cosine of the angle between its track and its bearing, negated.

	The outgoing radial component is ``speed * cos(heading - bearing)``, so a plane flying away closes at a negative
	rate and one pointed straight at you closes at its whole ground speed. A plane crossing your view closes at zero.
	"""
	speed = _number(row.get('speed')) or 0.0
	angle = math.radians((_number(row.get('heading')) or 0.0) - (_number(row.get('bearing')) or 0.0))
	return -speed * math.cos(angle)


def lookoutRadius(radius: float, idle: float, speedCap: float = 500.0) -> float:
	"""How far out to watch so nothing can cross ``radius`` unseen between two polls at ``idle`` seconds. Pure.

	It is the distance a ``speedCap`` aircraft covers in one idle interval: 500 knots is about 0.139 nautical miles a
	second, so a 60 second idle poll watches 8.3 miles further out. The feed's own ceiling wins when it is closer.
	"""
	return min(RADIUS_MAX, max(radius, radius + speedCap * idle / 3600.0))


def nextInterval(rows: List[Dict[str, Any]], radius: float, idle: float, fast: float, factor: float = 4.0) -> float:
	"""Seconds to wait before the next fetch, from what is heading your way. Pure.

	Anything inside ``radius`` gets the fastest cadence there is. Anything outside is timed by the distance it still
	has to cover at its closing speed and polled ``factor`` times before it arrives, so a jet 6 miles out and a
	trainer 6 miles out are polled in proportion to when each will actually be overhead. Nothing closing on you gets
	the idle interval. Clamped between ``fast`` and ``idle``.
	"""
	fast, idle = max(1.0, fast), max(1.0, idle)
	if idle < fast:
		fast, idle = idle, fast
	best = idle
	for row in rows:
		gap = row['distance'] - radius
		if gap <= 0:
			return fast
		approach = closingSpeed(row)
		if approach < 1.0:  # flying across, or away
			continue
		best = min(best, gap / approach * 3600.0 / max(1.0, factor))
	return max(fast, min(idle, best))


def feedUrl(source: str, lat: float, lon: float, radius: float) -> str:
	"""The URL to fetch for a ``[Aircraft] source``: a named public feed, or a receiver's own URL as written."""
	template = FEEDS.get(source.strip().lower())
	if template is None:
		if not source.strip().lower().startswith(('http://', 'https://')):
			raise ValueError(f'Aircraft source {source!r} is not one of {", ".join(FEEDS)} or an http(s) URL')
		return source.strip()
	return template.format(lat=f'{lat:.4f}', lon=f'{lon:.4f}', radius=int(min(RADIUS_MAX, max(1, math.ceil(radius)))))


def fetch(url: str, timeout: float = 10.0) -> dict:
	"""One GET of ``url`` as JSON. Blocking; the plugin runs it in a thread."""
	request = urllib.request.Request(url, headers={'User-Agent': 'LevityDash', 'Accept': 'application/json'})
	with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - an http(s) URL, checked by feedUrl
		return json.load(response)


def retryDelay(error: BaseException, default: float) -> float:
	"""Seconds to wait after a failed fetch: the feed's own ``Retry-After`` or ``x-ratelimit-reset``, else ``default``.

	The public feeds cap requests for an address, so retrying at ``interval`` after a 429 spends the cap again and
	the feed never recovers; the reset header says when it will answer. Never shorter than ``default``, never longer
	than a day. Pure, so a test can call it.
	"""
	headers = getattr(error, 'headers', None)
	if headers is not None:
		for name in ('Retry-After', 'x-ratelimit-reset'):
			value = headers.get(name)
			try:
				seconds = float(str(value).strip())
			except (TypeError, ValueError):
				continue
			return min(86400.0, max(default, seconds))
	return default


class Aircraft(LifecyclePlugin, realtime=True, hourly=False, logged=False):
	"""Publishes ``AIRCRAFT_KEYS``. See the module docstring."""

	name = 'Aircraft'

	__defaultConfig__ = """
	[plugin]
	enabled = False

	[Aircraft]
	source = adsb.fi
	radius = 50
	interval = 60
	fast_interval = 5
	adaptive = True
	lookout = 0
	speed_cap = 500
	slots = 20
	ground = False
	trigger_radius = 10
	trigger_altitude = 0
	max_altitude = 0
	military = True
	hold = 60
	latitude =
	longitude =
	"""

	def __init__(self):
		self.schema, self._sourceKeys = buildSchema({'keys': {k: dict(v) for k, v in AIRCRAFT_KEYS.items()}}, epoch=True)
		super().__init__()
		self._previous = 0
		self._lastNear: Optional[float] = None
		self._next: Optional[float] = None
		self._failed: Optional[str] = None
		self._scenarioKeys = set()
		if os.environ.get(ENV_VAR, '').strip():
			try:
				self._scenarioKeys = {key.partition('#')[0] for key in loadScenario(os.environ[ENV_VAR].strip())['keys']}
			except Exception as e:  # noqa: BLE001 - the Fixture reports a bad scenario
				log.debug(f'Aircraft: no scenario keys to skip: {e}')

	def _get(self, name: str, default: str) -> str:
		try:
			return str(self.config.getOrSet('Aircraft', name, default)).strip()
		except Exception:
			return default

	@property
	def source(self) -> str:
		return self._get('source', 'adsb.fi') or 'adsb.fi'

	@property
	def radius(self) -> float:
		try:
			return max(1.0, float(self._get('radius', '50')))
		except ValueError:
			return 50.0

	@property
	def slots(self) -> int:
		try:
			return max(1, min(SLOTS_MAX, int(self._get('slots', '20'))))
		except ValueError:
			return 20

	@property
	def interval(self) -> float:
		"""The longest wait between fetches: the idle cadence when nothing is heading in."""
		try:
			value = float(self._get('interval', '60'))
		except ValueError:
			value = 60.0
		return max(1.0 if self.source.lower().startswith('http') else 5.0, value)

	@property
	def fastInterval(self) -> float:
		"""The shortest wait between fetches, used while something is inside ``radius``."""
		floor = 1.0 if self.source.lower().startswith('http') else 5.0
		try:
			value = float(self._get('fast_interval', '5'))
		except ValueError:
			value = 5.0
		return max(floor, min(self.interval, value))

	@property
	def adaptive(self) -> bool:
		return self._get('adaptive', 'True').lower() in ('1', 'true', 'yes', 'on')

	@property
	def speedCap(self) -> float:
		"""The fastest ground speed a poll has to plan for, in knots."""
		return self._number('speed_cap', 500) or 500.0

	@property
	def lookout(self) -> float:
		"""The distance actually watched: ``lookout`` when set above ``radius``, else the distance anything can cross
		in one idle interval at ``speed_cap``."""
		configured = self._number('lookout', 0)
		if configured > self.radius:
			return min(RADIUS_MAX, configured)
		return lookoutRadius(self.radius, self.interval, self.speedCap)

	@property
	def ground(self) -> bool:
		return self._get('ground', 'False').lower() in ('1', 'true', 'yes', 'on')

	@property
	def location(self) -> tuple[float, float]:
		try:
			return float(self._get('latitude', '')), float(self._get('longitude', ''))
		except ValueError:
			return float(userConfig.lat), float(userConfig.lon)

	def _number(self, name: str, default: float) -> float:
		try:
			return max(0.0, float(self._get(name, str(default))))
		except ValueError:
			return default

	def publishRows(self, rows: Optional[List[Dict[str, Any]]]) -> None:
		"""Publish a reading. ``None`` is a failed fetch: the slots stay as they were and only ``active`` is brought up to date."""
		now = time.monotonic()
		near = overhead(rows or [], self._number('trigger_radius', 10), self._number('trigger_altitude', 0))
		active, self._lastNear = holdActive(near, now, self._lastNear, self._number('hold', 60))
		values = {'aircraft.near': near, 'aircraft.active': active} if rows is None else {
			**slotValues(rows, self.slots, self._previous), 'aircraft.near': near, 'aircraft.active': active}
		values['aircraft.nextCheck'] = round(self._next if self._next is not None else self.interval)
		if rows is not None:
			self._previous = min(len(rows), self.slots)
		realtime = {'time': int(datetime.now().timestamp())}
		for key, value in values.items():
			if key not in self._scenarioKeys:
				realtime[self._sourceKeys[key]] = value
		datagram = LevityDatagram(realtime, schema=self.schema, dataMap=self.schema.dataMaps['realtime'], static=False)
		self.realtime.update(datagram)

	async def publish(self) -> None:
		lat, lon = self.location
		watch = max(self.radius, self.lookout)
		url = feedUrl(self.source, lat, lon, watch)
		data = await asyncio.to_thread(fetch, url)
		seen = parseAircraft(data, lat, lon, watch, self.ground,
			self._number('max_altitude', 0), self._get('military', 'True').lower() in ('1', 'true', 'yes', 'on'))
		# The watch ring decides the cadence; only what is inside `radius` is published, so the radar stays yours.
		if self.adaptive:
			self._next = nextInterval(seen, self.radius, self.interval, self.fastInterval)
		self.publishRows([row for row in seen if row['distance'] <= self.radius])
		if self._failed:
			log.info('Aircraft: the feed is back')
			self._failed = None

	async def onStart(self) -> None:
		self._ticker = asyncio.ensure_future(self._tick())

	async def _tick(self) -> None:
		while True:
			delay = self._next if self._next is not None else self.interval
			try:
				await self.publish()
				delay = self._next if self._next is not None else self.interval
			except asyncio.CancelledError:
				raise
			except Exception as e:
				if self._failed != str(e):  # say it once, not every interval
					self._failed = str(e)
					log.error(f'Aircraft: fetch failed: {e}')
				delay = retryDelay(e, delay)  # a capped feed names its own reset
				self.publishRows(None)  # a dead feed must not leave `active` stuck on
			await asyncio.sleep(delay)

	async def onStop(self) -> None:
		ticker = getattr(self, '_ticker', None)
		if ticker is not None:
			ticker.cancel()


__plugin__ = Aircraft
