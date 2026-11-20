"""The shipped default dashboard (the OpenMeteo template), redrawn in the showcase style.

Only keys that OpenMeteo and the built-in Astronomy plugin publish, only fonts the app bundles (Nunito, Barlow
Condensed), and only theme tokens, so a theme picked from the menu recolours all of it.
"""
import math
import time
from datetime import datetime

from kit import *

FREEZE = '2026-06-21T09:20:00'
LEVITY = 'src/LevityDash/resources/example-config/templates/dashboards/OpenMeteo.levity'

T = 'environment.temperature.temperature'
P = 'environment.pressure.pressure'
PR = 'environment.precipitation.precipitation'
W = 'environment.wind'
C = 'environment.clouds.cover'
L = 'environment.light'
GLOW = {'strength': 1.2, 'reach': 2.0, 'passes': 6}
# The rooms panel: (caption, key suffix, colour). A plain `indoor.*` key is whichever Govee sensor is there; a
# `#name` suffix pins one sensor by its identity (see Govee.ini).
INDOOR = [('INDOOR', '', '$series-2')]
LABEL = 'Barlow Condensed'
CAP = 1.5
TILE = 3.6  # the detail size: every reading read up close has a value box this tall


def data(rooms=INDOOR, name='default'):
	d = Data(name, 'A wet Sunday morning in June: overcast at 9:20 am, rain from late morning into the afternoon, clearing tonight.',
	         9 + 20 / 60)
	rain = lambda t: 0.26 * bell(t, 13.5, 2.6) + 0.07 * bell(t, 17.5, 1.2)
	cloud = lambda t: min(100, 22 + 78 * bell(t, 13, 7) + 30 * bell(t, -10, 4))
	dayshift = {-1: 4.0, 0: -4.5, 1: 1.0, 2: 3.0, 3: 2.0}
	temp = d.series(lambda h, day, t: 66 + 8 * daily(h, 15.5) + dayshift.get(day, 0) * (0.5 + 0.5 * sun(h)) - 4 * bell(t, 14, 3.5),
	                noise=0.2, smooth=1)
	dew = d.series(lambda h, day, t: 56 + 2 * daily(h, 16) + 5 * bell(t, 13, 6), noise=0.2, smooth=1)
	hum = [round(min(99, max(25, 100 - (a - b) * 2.55))) for a, b in zip(temp, dew)]
	feels = [round(a + (h - 60) * 0.04, 1) for a, h in zip(temp, hum)]
	speed = d.series(lambda h, day, t: 4 + 3.5 * daily(h, 15) + 8 * bell(t, 14, 4), noise=0.5, smooth=1, lo=0.5)
	gust = [round(s * 1.6 + 1.5, 1) for s in speed]
	direction = d.series(lambda h, day, t: 170 + 30 * math.sin(t / 8) + 90 / (1 + math.exp(-(t - 16) / 3)), noise=6, smooth=1, digits=0)
	pressure = d.series(lambda h, day, t: 30.02 - 0.34 * bell(t, 15, 11) + 0.01 * math.sin(h / 12 * math.pi), digits=2)
	precipitation = d.series(lambda h, day, t: rain(t), lo=0, digits=2)
	cover = d.series(lambda h, day, t: cloud(t), digits=0)
	irradiance = d.series(lambda h, day, t: 900 * sun(h) ** 1.25 * (1 - cloud(t) / 120), lo=0, digits=0)

	d.add(T, 'f', temp)
	d.add('environment.temperature.feelsLike', 'f', feels)
	d.add('environment.temperature.dewpoint', 'f', dew)
	today = slice(24, 48)
	d.add('environment.temperature.high', 'f', value=round(max(temp[today])))
	d.add('environment.temperature.low', 'f', value=round(min(temp[today])))
	d.add('environment.humidity.humidity', '%', hum, digits=0)
	d.add(P, 'inHg', pressure, digits=2)
	d.add('environment.pressure.vaporPressureDeficit', 'kPa', [round(0.6108 * math.exp(17.27 * ((a - 32) / 1.8) / ((a - 32) / 1.8 + 237.3)) * (1 - h / 100), 2)
	                                                           for a, h in zip(temp, hum)], digits=2)
	d.add(f'{W}.speed.speed', WIND, speed, type='wind')
	d.add(f'{W}.speed.gust', WIND, gust, type='wind')
	d.add(f'{W}.speed.gustMax', WIND, value=round(max(gust[today])), type='wind')
	d.add(f'{W}.direction.direction', 'º', direction, type='direction', digits=0)
	d.add(PR, ['in', 'hr'], precipitation, type='precipitationHourly', digits=2)
	d.add('environment.precipitation.rainDaily', ['in', 'day'], value=round(sum(precipitation[today]), 2), type='precipitationDaily')
	d.add(f'{C}.cover', '%c', cover, type='cloudcover', digits=0)
	d.add(f'{C}.low', '%c', d.series(lambda h, day, t: min(100, 85 * bell(t, 13.5, 5)), digits=0), type='cloudcover', digits=0)
	d.add(f'{C}.mid', '%c', d.series(lambda h, day, t: min(100, 15 + 70 * bell(t, 12, 7)), digits=0), type='cloudcover', digits=0)
	d.add(f'{C}.high', '%c', d.series(lambda h, day, t: min(100, 30 + 40 * bell(t, 8, 8)), digits=0), type='cloudcover', digits=0)
	d.add(f'{L}.irradiance.irradiance', 'W/m^2', irradiance, digits=0)
	# Light split into what comes straight from the sun and what the cloud scatters.
	d.add(f'{L}.irradiance.direct', 'W/m^2', [round(v * (1 - c / 110)) for v, c in zip(irradiance, cover)], digits=0)
	d.add(f'{L}.irradiance.diffuse', 'W/m^2', [round(v * c / 110) for v, c in zip(irradiance, cover)], digits=0)
	d.add(f'{L}.irradiance.daily', 'MJ/m^2', value=round(sum(irradiance[today]) * 0.0036, 1), type='radiation')
	# Soil: the surface follows the air, a deeper layer follows it slower and flatter; the rain wets the top first.
	for depth, (lag, damp) in {'temperature': (1, 1.0), '6cm': (3, 0.7), '18cm': (6, 0.4), '54cm': (12, 0.12)}.items():
		d.add(f'environment.soil.temperature.{depth}', 'f', d.series(lambda h, day, t, lag=lag, damp=damp: 63 + damp * 9 * daily(h - lag, 15.5), smooth=1),
		      type='soil')
	wet = lambda t, k: 0.24 + k * 0.12 / (1 + math.exp(-(t - 12) / 1.5)) * math.exp(-max(0, t - 18) / 30)
	for depth, k in (('moisture', 1.0), ('1-3cm', 0.85), ('3-9cm', 0.6), ('9-27cm', 0.3), ('27-81cm', 0.1)):
		d.add(f'environment.soil.moisture.{depth}', '%', d.series(lambda h, day, t, k=k: 100 * wet(t, k), digits=0), type='soil', digits=0)
	d.add('environment.condition.condition', None, value=3, type='WeatherCode')
	for key, at in (('sunrise', '05:26'), ('sunset', '20:31')):
		# The render clock runs in UTC while the seed's place does not: four hours make up the difference.
		moment = datetime.fromisoformat(f'2026-06-21T{at}:00')
		d.add(f'{L}.{key}', 'epoch', value=int(time.mktime(moment.timetuple())) + 4 * 3600, type='datetime')
	d.add('astronomy.sun.hour', 'int', value=round(d.now, 3), title='Hour of day')
	d.add('astronomy.sun.remaining', 'int', value=671, title='Daylight left (minutes)')
	d.add('astronomy.sun.elevation', 'float', value=38.0, title='Sun elevation (degrees)')
	# No planes near by, so the last card shows the day's clock (home.py brings some over).
	d.add('aircraft.count', 'int', value=0, title='Aircraft in range')
	d.add('aircraft.active', 'int', value=0, title='A plane is near')
	d.add('aircraft.1.callsign', 'str', value='', title='Nearest flight')
	d.add('aircraft.1.distance', 'int', value=0, title='Nearest distance')
	d.add('aircraft.1.altitude', 'int', value=0, title='Nearest altitude')
	# Indoors: a house that holds near 70 °F, and a terrarium that is warm and wet under its lamp from 8 to 20.
	shapes = {'': (70.5, 1.2, 46, 4), '#bedroom': (68.5, 1.6, 50, 4), '#terrarium': (79, 4.5, 84, -8)}
	for _, sfx, _ in rooms:
		mid, swing, rh, rhSwing = shapes[sfx]
		lamp = (lambda h: 1 / (1 + math.exp(-(h - 8) * 2)) - 1 / (1 + math.exp(-(h - 20) * 2))) if sfx == '#terrarium' else (lambda h: daily(h, 17))
		temp = d.series(lambda h, day, t: mid + swing * lamp(h) + 0.6 * daily(h, 16), noise=0.15, smooth=1)
		hum = d.series(lambda h, day, t: rh + rhSwing * lamp(h) + 3 * bell(t, 14, 6), noise=0.6, smooth=1, digits=0)
		d.add(f'indoor.temperature.temperature{sfx}', 'f', temp)
		d.add(f'indoor.humidity.humidity{sfx}', '%', hum, digits=0)
		d.add(f'indoor.temperature.dewpoint{sfx}', 'f', [round(a - (100 - h) / 2.55, 1) for a, h in zip(temp, hum)])
		d.add(f'indoor.battery.battery{sfx}', '%', value={'': 91, '#bedroom': 87, '#terrarium': 64}[sfx], type='battery', digits=0)
		d.add(f'indoor.temperature.heatIndex{sfx}', 'f', [round(a + max(0, h - 40) * 0.05, 1) for a, h in zip(temp, hum)])
	return d


# Temperatures in Allo, whose weight and roundness follow the reading: hot comes out heavy and round, cold lean and
# sharp. Never under 500 at the cold end (no hairlines on the display). Allo has tabular figures, so columns still line up.
TEMP_FONT = 'Allo Variable'


def tempAxes(lo=500, hi=800, low='20°F', high='95°F', corner=True):
	"""`corner` rounds the strokes as it warms; off where there are small decimals, which it fills in."""
	axes = {'range': [low, high], 'wght': [lo, hi], 'ROND': [0, 100], 'opsz': 32}
	if corner:
		axes['corner'] = [0, 0.05]
	return {'font-axes': axes}


def cap_(s, geom, color='$faint', **kw):
	"""A label: condensed, tracked capitals."""
	kw.setdefault('tracking', 0.16)
	return cap(s, geom, color, font=LABEL, weight='SemiBold', **kw)


def num(key, geom, color='$text', weight='Regular', font='$mono', small=False, **kw):
	"""A number. Fixed-width (Roboto Mono) unless it is the one big temperature, so digits line up and do not jump."""
	item = val(key, geom, color, font=font, weight=weight, **kw)
	# No inset: the ink's left edge sits on the box's edge, so a number lines up under its caption.
	item['margins'] = {'left': 0, 'right': 0, 'top': 0, 'bottom': 0}
	item['display']['valueLabel'].setdefault('alignment', item['alignment'])
	item['display']['valueLabel']['margins'] = {'left': 0, 'right': '10%', 'top': 0, 'bottom': 0}  # a gutter to the next column
	if small:
		# The tenths drawn smaller, on the digits' baseline: 67⁷° reads as sixty-seven at a glance.
		item['display']['valueLabel'].update({'decimal-scale': 0.36, 'decimal-align': 'baseline'})
	return item


def batteryGlyph(key, geom):
	"""A battery icon, no label or number: red under 20 %, amber under 50 %, green above."""
	return {'type': 'realtime.bar', 'key': key, 'title': False, 'geometry': geom,
	        'display': {'style': 'battery', 'range': {'min': 0, 'max': 100}, 'fill': {'color': 'zone'},
	                    'zones': [{'to': 20, 'color': '$bad', 'opacity': 0}, {'from': 20, 'to': 50, 'color': '$warn', 'opacity': 0},
	                              {'from': 50, 'color': '$good', 'opacity': 0}],
	                    'value-label': {'visible': False}}}


def battery(caption, key, x, y, w, h=TILE, right=False):
	"""A caption over a battery bar: red under 20 %, amber under 50 %, green above, the number at its end."""
	side = {'align': 'BottomRight'} if right else {}
	return [cap_(caption, g(x, y, w, CAP), **side),
	        {'type': 'realtime.bar', 'key': key, 'title': False, 'geometry': g(x, y + CAP + 0.4 + h * 0.15, w, h * 0.7),
	         'display': {'style': 'battery', 'range': {'min': 0, 'max': 100}, 'fill': {'color': 'zone', 'glow': GLOW},
	                     'zones': [{'to': 20, 'color': '$bad', 'opacity': 0}, {'from': 20, 'to': 50, 'color': '$warn', 'opacity': 0},
	                               {'from': 50, 'color': '$good', 'opacity': 0}],
	                     'value-label': {'visible': False}}}]


def tile(caption, key, x, y, w, color='$text', h=TILE, group='global.detail', right=False, **kw):
	"""A caption over a number. `right` sets both flush to the right edge, for a column against the board's edge."""
	side = {'align': 'BottomRight'} if right else {}
	value = num(key, g(x, y + CAP + 0.4, w, h), color, group=group, **side, **kw)
	if right:
		value['display']['valueLabel']['margins'] = {'left': '10%', 'right': 0, 'top': 0, 'bottom': 0}  # flush to the edge
	return [cap_(caption, g(x, y, w, CAP), **side), value]


def capsules(m, width=0.6, **plot):
	"""Round the bars of a mini graph into capsules."""
	for figure in m['figures']:
		for value in figure.values():
			if isinstance(value, dict) and 'plot' in value:
				value['plot'].update(width=width, radius=0.5, **plot)
	return m


def clock():
	"""The classic LevityDash clock: the date on a line of its own, the time, the moon over am or pm."""
	return {'type': 'clock', 'name': 'clock', 'frozen': True, 'geometry': {'height': '22.2%', 'width': '36.5%', 'x': '0%', 'y': '1.6%'}, 'items': [
		{'format': '%A, %B %-d', 'alignment': 'CenterRight', 'filters': ['AddOrdinal'],
		 'geometry': {'height': '27%', 'width': '100%', 'x': '0%', 'y': '0%'}, 'margins': {'left': '10px'}},
		# Time and am/pm are both bottom-aligned in boxes that end at one edge, with descender-free hints, so they share a baseline.
		# The hint sizes the time for its widest form, so it does not grow at 1:00 and shrink at 10:00.
		{'format': '%-I:%M', 'alignment': 'BottomRight', 'format-hint': '10:00',
		 'geometry': {'height': '73%', 'width': '80%', 'x': '1.2%', 'y': '27%'}, 'margins': {'right': '10px'}},
		{'type': 'moon', 'geometry': {'height': '45%', 'width': '18.8%', 'x': '81.2%', 'y': '27%'}, 'glowStrength': 0, 'interval': {'minutes': 20}},
		{'format': '%p', 'filters': ['Lower'], 'alignment': 'BottomLeft', 'format-hint': 'am', 'geometry': {'height': '29.6%', 'width': '18.8%', 'x': '81.2%', 'y': '70.4%'}},
	]}


def room(caption, sfx, color, x, y, w, h, i):
	"""One room: its name, the temperature over its last day, and humidity and dew point (and feels like, if tall)."""
	key = lambda name: f'indoor.{name}{sfx}'
	temp = key('temperature.temperature')
	rows = [('RH', key('humidity.humidity'), '$info', {'hint': '00%', 'unit': 'Inline'}),
	        ('DEW', key('temperature.dewpoint'), '$good', {'hint': '00°', 'unit': 'Inline'})]
	out = [cap_(caption, g(x, y, w, CAP), color)]
	# The sensor's battery as a small glyph at the end of the name's line, where the number's column ends.
	glyphX = x + (w * 0.7 if h > 25 else w * 0.6 - 0.8) - 2.4
	out.append(batteryGlyph(key('battery.battery'), g(glyphX, y + CAP * 0.15, 2.4, CAP * 0.7)))
	if h > 25:
		# Tall: the number, a day of temperature under it, and three readings in a row along the bottom.
		rows.append(('FEELS', key('temperature.heatIndex'), '$warn', {'hint': '00°', 'unit': 'Inline'}))
		body = h - CAP - 0.8 - 7.6
		out += [
			mini(temp, g(x, y + CAP + 0.8, w, body), color=color, hours=24, past=True, top='42%', bottom='0%', opacity=0.8, fill=0.3, weight=0.5,
			     glow=GLOW),
			num(temp, g(x, y + CAP + 0.8, w * 0.7, 11.5), '$text', weight='Bold', tracking=-0.02, unit='Inline', hint='00.0°', precision=1, small=True,
			    group='global.room', align='TopLeft', font=TEMP_FONT, **tempAxes(corner=False)),
		]
		quarter = w / len(rows)
		for j, (name, k, c, kw) in enumerate(rows):
			out += tile(name, k, x + j * quarter, y + h - 5.4, quarter - 0.6, c, h=TILE, group='global.detail', right=j == len(rows) - 1, **kw)
		return out
	# Short: the number over its day on the left, two readings stacked on the right.
	hh = h - CAP - 0.8
	left = w * 0.6
	out += [
		mini(temp, g(x, y + CAP + 0.8, left - 0.8, hh), color=color, hours=24, past=True, top='45%', bottom='0%', opacity=0.8, fill=0.3, weight=0.5,
		     glow=GLOW),
		num(temp, g(x, y + CAP + 0.8, left - 0.8, hh * 0.62), '$text', weight='Bold', tracking=-0.02, unit='Inline', hint='00.0°', precision=1, small=True,
		    group='global.room', align='TopLeft', font=TEMP_FONT, **tempAxes(corner=False)),
	]
	# Four readings in two columns, the outer one flush to the board's edge so the panel reaches it.
	rows = [('RH', key('humidity.humidity'), '$info', {'hint': '00%', 'unit': 'Inline'}),
	        ('24H HI', f'max({temp}, 24h)', '$bad', {'hint': '00°', 'unit': 'Inline'}),
	        ('DEW', key('temperature.dewpoint'), '$good', {'hint': '00°', 'unit': 'Inline'}),
	        ('24H LO', f'min({temp}, 24h)', '$info', {'hint': '00°', 'unit': 'Inline'})]
	col = (w - left) / 2
	for j, (name, k, c, kw) in enumerate(rows):
		r, cc = divmod(j, 2)
		out += tile(name, k, x + left + cc * col, y + r * h / 2, col - 0.3, c, h=TILE, group='global.detail', right=bool(cc), **kw)
	return out


# A light runs round a card while something is happening in it: rain falling now, a plane overhead.
# Variants rolled from Neal's creative seed, `a;ksdfv893hakljdfhy98nbaclkjcghb349afohlea89o7ty` (sha256 bytes mod 4).
BEAMS = {
	'rain': {'size': 'line', 'variant': 'ocean', 'active': PR, 'radius': 24, 'strength': 0.8},
	'today': {'size': 'md', 'variant': 'colorful', 'active': 'aircraft.active', 'radius': 24, 'glow': True},
}


# A card that only joins the band while it has something to say: the rain card while rain fell in the last day or
# is forecast in the next six hours (no data counts as no rain, so it also stays out when the key is missing).
WHEN = {'rain': f'max({PR}, 24h) > 0 or at({PR}, 6h) > 0'}


def board(rooms=INDOOR):
	B = [clock()]
	# Two reading sizes (Neal's rule): `global.room` for what is read across the room, `global.detail` for what is
	# read standing in front of it. Every number but the clock and the outdoor temperature is in one of the two.
	# ------------------------------------------------------------ outside, now
	x = 39.5
	B += [
		cap_('OUTSIDE', g(x, 2.8, 12, CAP), '$accent'),
		num(T, g(x, 4.6, 15.4, 15.6), {'scale': '$temperature', 'of': T}, unit='Inline', hint='00°', weight='Black', tracking=-0.04, font=TEMP_FONT,
		    **tempAxes(600, 900)),
		cap_('HIGH', g(x + 16.6, 2.8, 7, CAP)),
		num('environment.temperature.high', g(x + 16.6, 4.6, 8, 5.8), '$bad', hint='00', weight='Bold', group='global.room',
		    fmt={'unit_symbol': False}, font=TEMP_FONT, **tempAxes()),
		cap_('LOW', g(x + 16.6, 12.0, 7, CAP)),
		num('environment.temperature.low', g(x + 16.6, 13.8, 8, 5.8), '$info', hint='00', weight='Bold', group='global.room',
		    fmt={'unit_symbol': False}, font=TEMP_FONT, **tempAxes()),
		# The day's low to high on a 30 to 100 °F track, the temperature now as a line across it.
		bar(T, g(x, 20.9, 24.6, 2.2), 30, 100, track={'weight': '42%', 'color': '$rule'},
		    fill={'from': 'environment.temperature.low', 'to': 'environment.temperature.high', 'gradient': '$temperature', 'weight': '42%',
		          'glow': GLOW},
		    pointer={'type': 'line', 'color': '$accent', 'size': '100%'}),
		{'type': 'realtime.text', 'key': 'environment.condition.condition', 'title': False, 'alignment': 'CenterLeft', 'geometry': g(x, 23.6, 10, 2.4),
		 'display': {'valueLabel': {'color': '$muted', 'font': '$body', 'weight': 'Light', 'italic': True, 'matchingGroup': {'group': 'global.detail', 'matchAll': True}}}},
		text('feels', g(x + 10.2, 23.6, 3.6, 2.4), font='$body', weight='Light', italic=True, color='$faint', align='CenterRight', group='global.detail'),
		num('environment.temperature.feelsLike', g(x + 14.2, 23.6, 4, 2.4), unit='Inline', hint='00°', weight='SemiBold', align='CenterLeft', group='global.detail'),
		# Humidity and dew point beside the high and low, at the detail size, in the gap before the sun.
		*tile('RH', 'environment.humidity.humidity', x + 23.4, 2.8, 4.6, '$info', hint='00%', unit='Inline'),
		*tile('DEW', 'environment.temperature.dewpoint', x + 23.4, 12.0, 4.6, '$good', hint='00°', unit='Inline'),
	]
	# ------------------------------------------------------------ the sun
	x = 68.5
	B += [
		cap_('DAYLIGHT LEFT', g(x, 2.8, 16, CAP), '$warn'),
		mini(f'{L}.irradiance.irradiance', g(x, 7, 18, 13.6), color='$warn', hours=24, past=True, lo=0, hi=1000, top='25%', bottom='0%', opacity=0.75,
		     fill=0.35, weight=0.5, glow=GLOW),
		num('astronomy.sun.remaining', g(x, 4.6, 18, 9), '$text', fmt='duration', hint='00h 00m', weight='Light', tracking=-0.04, group='global.room'),
		# One cell for each hour of daylight still to come, lit from warm to the evening colour.
		bar('astronomy.sun.remaining', g(x, 21.2, 18, 2.2), 0, 960, track={'weight': '100%', 'color': '$rule', 'segments': 16, 'gap': '18%'},
		    fill={'gradient': {0: '$accent', 1: '$warn'}, 'segments': 16, 'gap': '18%', 'weight': '100%', 'glow': GLOW}),
		*tile('SUNRISE', f'{L}.sunrise', x + 19.8, 2.8, 9.6, '$warn', fmt='%-I:%M', hint='0:00', right=True),
		*tile('SUNSET', f'{L}.sunset', x + 19.8, 10.4, 9.6, '$accent', fmt='%-I:%M', hint='0:00', right=True),
		*tile('SUN · W/M²', f'{L}.irradiance.irradiance', x + 19.8, 18.0, 9.6, '$warn', hint='000', right=True),
	]
	# ------------------------------------------------------------ the days ahead
	B.append({
		'type': 'graph', 'name': 'forecast', 'geometry': g(1.5, 28.5, 69.5, 37),
		'timeframe': {'days': 2, 'hours': 18, 'offset': {'hours': -6}},
		'annotations': {'dayLabels': {'position': 'Center', 'alignment': 'Center', 'opacity': '12%', 'height': '38%'},
		                'hourLabels': {'alignment': 'BottomCenter', 'spacingIntervals': '6, 12', 'height': '4%'},
		                'lines': {'spacing': '12 mm', 'weight': 0.4}},
		'figures': [
			{'figure': 'sky', 'margins': {'top': '3%', 'bottom': '87%'},
			 'environment.temperature.dewpoint': {'plot': {'type': 'strip', 'pins': {
				 'key': PR, 'size': 30, 'at': 0.5, 'color': '$info', 'spacing': 3.2,
				 'steps': [[0, 'wi:day-cloudy'], [0.02, 'wi:sprinkle'], [0.1, 'wi:showers'], [0.2, 'wi:rain']]}}}},
			{'figure': 'arrows', 'margins': {'top': '13%', 'bottom': '80%'},
			 'environment.temperature.dewpoint': {'plot': {'type': 'strip', 'pins': {
				 'key': f'{W}.direction.direction', 'glyph': 'wi:direction-up', 'rotate': 180, 'size': 24, 'at': 0.5, 'spacing': 3.4, 'color': '$faint'}}}},
			{'figure': 'temperature', 'margins': {'top': '28%', 'bottom': '30%'},
			 T: {'labels': {'enabled': True},
			     'plot': {'type': 'plot', 'gradient': 'TemperatureGradient', 'weight': 1.0, 'glow': GLOW, 'fill': {'opacity': 0.35, 'fade': True}}, 'resolution': 2},
			 'environment.temperature.feelsLike': {'plot': {'type': 'plot', 'gradient': 'TemperatureGradient', 'weight': 0.3, 'opacity': 0.6}},
			 'environment.temperature.dewpoint': {'plot': {'type': 'plot', 'color': '$good', 'dashPattern': '5, 5', 'weight': 0.35, 'cap': 'square'}}},
			{'figure': 'clouds', 'margins': {'top': '72%', 'bottom': '9%'}, 'min': 0, 'max': 1,
			 f'{C}.cover': {'plot': {'type': 'plot', 'color': '$faint', 'weight': 0.3, 'opacity': 0.6, 'fill': {'opacity': 0.12, 'fade': True}}}},
			{'figure': 'rain', 'margins': {'top': '70%', 'bottom': '9%'}, 'min': 0, 'max': 0.4,
			 PR: {'plot': {'type': 'bar', 'color': '$info', 'width': 0.62, 'radius': 0.5, 'glow': GLOW}, 'smooth': False}},
		]})
	# ------------------------------------------------------------ indoors
	top, height, gap = 28.5, 37, 2.2
	each = (height - gap * (len(rooms) - 1)) / len(rooms)
	for i, (caption, sfx, color) in enumerate(rooms):
		B += room(caption, sfx, color, 74.5, top + i * (each + gap), 23.5, each, i)
	# ------------------------------------------------------------ five cards
	# Each card: a caption, the hero at room size, a picture of its last or next day, and six readings at detail size.
	Y, H, CW, GAP = 68.5, 29.5, 18.24, 1.2
	X = [2 + i * (CW + GAP) for i in range(5)]
	px, py = 1.2, 1.8
	iw = CW - 2 * px
	HERO = 9
	top = Y + py + CAP + 0.6
	hero = lambda key, x, w, color, **kw: num(key, g(x, top, w, HERO), color, weight='Bold', tracking=-0.03, group='global.room', **kw)
	pic = Y + 13.3
	rows = (Y + 17.8, Y + 23.4)
	cell = (iw - 1.0) / 3

	def six(x, entries, start=0):
		"""Readings in rows of three under the picture: (caption, key, colour, settings)."""
		out = []
		for n, (caption, key, color, kw) in enumerate(entries):
			r, c = divmod(n + start, 3)
			out += tile(caption, key, x + c * (cell + 0.5), rows[r], cell, color, **kw)
		return out

	cards = {}
	x = X[0] + px
	cards['wind'] = [
		cap_('WIND · MPH', g(x, Y + py, iw, CAP), '$series-6'),
		hero(f'{W}.speed.speed', x, 7.8, '$series-6', hint='00'),
		{'type': 'polar', 'name': 'rose', 'plot': 'rose', 'direction': f'{W}.direction.direction', 'speed': f'{W}.speed.speed', 'window': '24h',
		 'legend': False, 'rings': 3, 'compass': 4, 'gradient': 'WindSpeedGradient', 'geometry': g(x + 7.8, Y + 0.6, 8.6, 12.6)},
		mini(f'{W}.speed.gust', g(x, pic, iw, 4), color='$warn', hours=24, past=True, lo=0, top='8%', bottom='0%', opacity=0.5, fill=0.15, weight=0.35),
		mini(f'{W}.speed.speed', g(x, pic, iw, 4), color='$series-6', hours=24, past=True, lo=0, top='8%', bottom='0%', glow=GLOW),
		# Detail captions say what, the card's caption says the unit; a window or offset is 24 h unless it says.
		*six(x, [('GUST', f'{W}.speed.gust', '$warn', {'hint': '00'}),
		         ('PEAK', f'max({W}.speed.gust, today)', '$bad', {'hint': '00'}),
		         ('FROM', f'{W}.direction.direction', '$info', {'hint': 'SSW'}),
		         ('AVG', f'avg({W}.speed.speed, 24h)', '$series-6', {'hint': '00'}),
		         ('MAX', f'max({W}.speed.gust, 24h)', '$warn', {'hint': '00'}),
		         ('+6 H', f'at({W}.speed.speed, 6h)', '$muted', {'hint': '00'})]),
	]
	x = X[1] + px
	cards['rain'] = [
		cap_('RAIN · INCHES', g(x, Y + py, iw, CAP), '$info'),
		hero('environment.precipitation.rainDaily', x, 9.6, '$info', precision=2, hint='0.00'),
		text('today', g(x + 9.8, top + 5.4, 6, 2.6), font='$body', weight='Light', italic=True, color='$faint', align='BottomLeft'),
		capsules(mini(PR, g(x, pic, iw, 4), color='$info', hours=24, lo=0, hi=0.4, kind='bar', top='4%', bottom='0%', opacity=1, glow=GLOW,
		              smooth=False)),
		*six(x, [('NOW', PR, '$info', {'precision': 2, 'hint': '0.00'}),
		         ('PEAK', f'max({PR}, today)', '$series-4', {'precision': 2, 'hint': '0.00'}),
		         ('+3 H', f'at({PR}, 3h)', '$muted', {'precision': 2, 'hint': '0.00'}),
		         ('+6 H', f'at({PR}, 6h)', '$muted', {'precision': 2, 'hint': '0.00'}),
		         ('+12 H', f'at({PR}, 12h)', '$muted', {'precision': 2, 'hint': '0.00'}),
		         ('LOW CLD', f'{C}.low', '$faint', {'hint': '000', 'fmt': {'unit_symbol': False}})]),
	]
	x = X[2] + px
	trend = lambda s, color, when=None: {**text(s, g(0, 0, 100, 100), font=LABEL, weight='SemiBold', color=color, tracking=0.2, align='CenterLeft'),
	                                     **({'when': when} if when else {})}
	cards['pressure'] = [
		cap_('PRESSURE · INHG', g(x, Y + py, iw, CAP), '$series-4'),
		mini(P, g(x, top, iw, HERO), color='$series-4', hours=24, past=True, top='30%', opacity=0.8, fill=0.3, weight=0.6, glow=GLOW),
		hero(P, x, iw, '$text', precision=2, hint='00.00'),
		{'type': 'switch', 'name': 'tendency', 'hold': '10m', 'fade': '0.4s', 'geometry': g(x, pic + 0.6, iw, 2.8), 'items': [
			trend('RISING ▲', '$good', f'{P} - at({P}, -3h) > 0.02 inHg'),
			trend('FALLING ▼', '$bad', f'at({P}, -3h) - {P} > 0.02 inHg'),
			trend('STEADY', '$faint')]},
		*six(x, [('−3 H', f'{P} - at({P}, -3h)', '$info', {'precision': 2, 'hint': '-0.00'}),
		         ('−24 H', f'{P} - at({P}, -24h)', '$info', {'precision': 2, 'hint': '-0.00'}),
		         ('+12 H', f'at({P}, 12h)', '$series-4', {'precision': 2, 'hint': '00.00'}),
		         ('HIGH', f'max({P}, 24h)', '$muted', {'precision': 2, 'hint': '00.00'}),
		         ('LOW', f'min({P}, 24h)', '$muted', {'precision': 2, 'hint': '00.00'}),
		         ('+24 H', f'at({P}, 24h)', '$series-4', {'precision': 2, 'hint': '00.00'})]),
	]
	x = X[3] + px
	cards['sky'] = [
		cap_('CLOUD COVER · %', g(x, Y + py, iw, CAP), '$muted'),
		hero(f'{C}.cover', x, 8.4, '$text', hint='000', fmt={'unit_symbol': False}),
	]
	# The three layers as standing pills, filled to their cover.
	for i, (name, layer) in enumerate((('LOW', 'low'), ('MID', 'mid'), ('HIGH', 'high'))):
		px_ = x + 9.4 + i * 2.4
		cards['sky'] += [
			bar(f'{C}.{layer}', g(px_, top, 1.8, HERO - 2), 0, 1, color='$muted', orientation='vertical', track={'weight': '100%', 'color': '$rule'},
			    fill={'weight': '100%'}),
			cap_(name[0], g(px_ - 0.3, top + HERO - 1.6, 2.4, CAP), group='global.layer', align='Center', tracking=0, **{'format-hint': 'M'}),
		]
	cards['sky'] += [
		mini(f'{C}.cover', g(x, pic, iw, 4), color='$muted', hours=24, lo=0, hi=1, top='6%', bottom='0%', opacity=0.7, fill=0.25, weight=0.35),
		*six(x, [('RH', 'environment.humidity.humidity', '$info', {'hint': '00%', 'unit': 'Inline'}),
		         ('DEW', 'environment.temperature.dewpoint', '$good', {'hint': '00°', 'unit': 'Inline'}),
		         ('VPD', 'environment.pressure.vaporPressureDeficit', '$good', {'precision': 2, 'hint': '0.00', 'fmt': {'unit_symbol': False}}),
		         ('+6 H', f'at({C}.cover, 6h)', '$muted', {'hint': '000', 'fmt': {'unit_symbol': False}}),
		         ('HI CLD', f'{C}.high', '$faint', {'hint': '000', 'fmt': {'unit_symbol': False}}),
		         ('MIN RH', 'min(environment.humidity.humidity, 24h)', '$info', {'hint': '00%', 'unit': 'Inline'})]),
	]
	# Two more cards that only the band has room for: the ground under the plants, and the light that reaches them.
	x = X[0] + px
	S = 'environment.soil'
	depths = [('1', 'moisture'), ('3', '1-3cm'), ('9', '3-9cm'), ('27', '9-27cm'), ('81', '27-81cm')]
	rowH = (pic + 4 - Y - py) / len(depths)
	cards['soil'] = [
		cap_('SOIL · °F', g(x, Y + py, 7.6, CAP), '$good'),
		hero(f'{S}.temperature.temperature', x, 7.6, '$good', unit='Inline', hint='00°'),
		mini(f'{S}.temperature.temperature', g(x, pic, 7.2, 4), color='$good', hours=24, past=True, top='10%', bottom='0%', fill=0.3, weight=0.5,
		     glow=GLOW),
		# Wetness by depth, top to bottom, like a core pulled out of the bed.
		*[item for n, (cm, k) in enumerate(depths) for item in (
			text(cm, g(x + 8.2, Y + py + n * rowH, 1.6, rowH), font='$mono', color='$faint', align='CenterRight', group='global.depth'),
			bar(f'{S}.moisture.{k}', g(x + 10.2, Y + py + n * rowH + rowH * 0.25, iw - 10.2, rowH * 0.5), 0, 0.5, color='$info', glow=GLOW,
			    track={'weight': '100%', 'color': '$rule'}, fill={'weight': '100%'}))],
		*six(x, [('6 CM', f'{S}.temperature.6cm', '$good', {'hint': '00°', 'unit': 'Inline'}),
		         ('18 CM', f'{S}.temperature.18cm', '$good', {'hint': '00°', 'unit': 'Inline'}),
		         ('54 CM', f'{S}.temperature.54cm', '$muted', {'hint': '00°', 'unit': 'Inline'}),
		         ('WET', f'{S}.moisture.moisture', '$info', {'hint': '00%', 'unit': 'Inline'}),
		         ('DEEP', f'{S}.moisture.27-81cm', '$info', {'hint': '00%', 'unit': 'Inline'}),
		         ('+6 H', f'at({S}.temperature.temperature, 6h)', '$muted', {'hint': '00°', 'unit': 'Inline'})]),
	]
	cards['light'] = [
		cap_('LIGHT · W/M²', g(x, Y + py, iw, CAP), '$warn'),
		hero(f'{L}.irradiance.irradiance', x, 9, '$warn', hint='000'),
		ring(f'{L}.irradiance.irradiance', g(x + iw - 6.4, Y + 1.2, 6.4, 10.4), 0, 1000, '$warn', weight='12%', glow=GLOW),
		mini(f'{L}.irradiance.diffuse', g(x, pic, iw, 4), color='$muted', hours=24, past=True, lo=0, hi=1000, top='8%', bottom='0%', opacity=0.6,
		     fill=0.2, weight=0.35),
		mini(f'{L}.irradiance.direct', g(x, pic, iw, 4), color='$warn', hours=24, past=True, lo=0, hi=1000, top='8%', bottom='0%', fill=0.3, weight=0.5,
		     glow=GLOW),
		*six(x, [('DIRECT', f'{L}.irradiance.direct', '$warn', {'hint': '000'}),
		         ('DIFFUSE', f'{L}.irradiance.diffuse', '$muted', {'hint': '000'}),
		         ('DAY MJ', f'{L}.irradiance.daily', '$accent', {'precision': 1, 'hint': '00.0'}),
		         ('PEAK', f'max({L}.irradiance.irradiance, 24h)', '$warn', {'hint': '000'}),
		         ('+3 H', f'at({L}.irradiance.irradiance, 3h)', '$muted', {'hint': '000'}),
		         ('+6 H', f'at({L}.irradiance.irradiance, 6h)', '$muted', {'hint': '000'})]),
	]
	x = X[4] + px
	# Planes near by take the card over (`aircraft.active`, from the Aircraft plugin, off until Aircraft.ini enables it);
	# otherwise the day's clock. Either way three readings sit under the picture.
	body = g(x - 0.4, top, iw + 0.8, rows[1] - top - 0.4)
	whole = (x, Y + py, iw, H - 2 * py)
	cards['today'] = [{'type': 'switch', 'name': 'skyOrClock', 'hold': '2m', 'fade': '0.4s', 'geometry': g(*whole), 'items': [
		nest('planes', whole, [
			cap_('OVERHEAD · NM', g(x, Y + py, iw * 0.6, CAP), '$info'),
			num('aircraft.count', g(x + iw * 0.6, Y + py - 0.4, iw * 0.4, CAP + 0.8), '$info', weight='Bold', align='TopRight', hint='00'),
			{'type': 'polar', 'name': 'radar', 'plot': 'radar', 'prefix': 'aircraft', 'slots': 15, 'max': 30, 'labels': 4, 'sweep': True,
			 'rings': 3, 'accent': '$info', 'gradient': [{'at': 0, 'color': '$bad'}, {'at': 8000, 'color': '$warn'}, {'at': 40000, 'color': '$info'}],
			 'geometry': body},
			*six(x, [('FLIGHT', 'aircraft.1.callsign', '$text', {'hint': 'AAL000', 'group': 'global.callsign'}),
			         ('NM', 'aircraft.1.distance', '$info', {'precision': 1, 'hint': '00.0'}),
			         ('FT', 'aircraft.1.altitude', '$warn', {'hint': '00000'})], start=3)], fill=None, when='aircraft.active') | {'geometry': g(0, 0, 100, 100)},
		nest('dayClock', whole, [
			cap_('TODAY ROUND THE CLOCK', g(x, Y + py, iw, CAP), '$accent'),
			{'type': 'polar', 'name': 'dayClock', 'plot': 'clock', 'key': T, 'window': 'today', 'gradient': '$temperature', 'marks': False,
			 'geometry': body},
			*six(x, [('−24 H', f'at({T}, -24h)', '$muted', {'hint': '00°', 'unit': 'Inline'}),
			         ('AVG', f'avg({T}, 24h)', '$muted', {'hint': '00°', 'unit': 'Inline'}),
			         ('+24 H', f'at({T}, 24h)', '$muted', {'hint': '00°', 'unit': 'Inline'})], start=3)], fill=None) | {'geometry': g(0, 0, 100, 100)}]}]
	# Each card is glass over the sky: the surface washed with its own colour, so each reads as its own thing at a glance.
	tint = {'wind': '$series-6', 'rain': '$info', 'pressure': '$series-4', 'sky': '$muted', 'soil': '$good', 'light': '$warn', 'today': '$accent'}
	origin = {'wind': X[0], 'rain': X[1], 'pressure': X[2], 'sky': X[3], 'soil': X[0], 'light': X[0], 'today': X[4]}

	def card(name):
		fill = {'color': {'color': '$surface', 'mix': {'with': tint[name], 'by': 0.14}}, 'alpha': 0.62}
		extra = ({'beam': BEAMS[name]} if name in BEAMS else {}) | ({'when': WHEN[name]} if name in WHEN else {})
		return nest(f'{name}Card', (origin[name], Y, CW, H), cards.pop(name), fill=fill, **extra)

	# The last card stays put (a plane overhead must not scroll away); the rest take turns in a band, four in view.
	today = card('today')
	slots = [card(name) for name in list(cards)]
	for slot in slots:
		del slot['geometry']
	length = X[3] + CW - X[0]
	B.append({'type': 'band', 'name': 'cards', 'mode': 'step', 'visible': 4, 'gap': f'{GAP / length * 100:.3f}%', 'dwell': '12s',
	          'transition': '900ms', 'step': 1, 'geometry': g(X[0], Y, length, H), 'items': slots})
	B.append(today)
	# The ground follows the sun: navy at night, purple and orange near the horizon, blue by day, greyed by cloud.
	# The ground follows the sun and is greyed by cloud; at night the real sky (bright-star catalogue and planets, placed
	# for the configured location and time) comes out, thinned by cloud.
	sky = {'sky': True, 'haze': f'{C}.cover', 'stars': True}
	return {'background': sky, 'theme': {'extends': 'default', 'colors': {'moon-shade': {'color': '#000000', 'alpha': 0.2}}}, 'items': [{'type': 'group', 'name': 'board', 'items': B}]}


HEADER = """
The default dashboard for OpenMeteo, the forecast LevityDash starts with.

Top: the clock (the date on its own line, the time, the moon over am or pm), the temperature with the day's high and
low, and the daylight left over today's sunlight. Middle: two and a half days ahead, and indoors (a Govee sensor's
temperature over its last day, humidity, dew point, feels like). Bottom: wind, rain, pressure, the sky, and today's
temperature round a 24 hour clock.

Every outdoor key comes from OpenMeteo or the built-in Astronomy plugin; the indoor ones need a Govee sensor and stay
empty without one. Fonts are the bundled Nunito, Roboto Mono (the numbers) and Barlow Condensed (the labels). Colours
are theme tokens: pick a theme from Dashboard > Theme to recolour it.
"""

if __name__ == '__main__':
	write('default', HEADER, board(), data(), FREEZE, levity=LEVITY)
