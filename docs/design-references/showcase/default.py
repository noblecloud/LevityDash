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
TILE = 5.2


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
	d.add('environment.precipitation.daily', ['in', 'day'], value=round(sum(precipitation[today]), 2), type='precipitationDaily')
	d.add(f'{C}.cover', '%c', cover, type='cloudcover', digits=0)
	d.add(f'{C}.low', '%c', d.series(lambda h, day, t: min(100, 85 * bell(t, 13.5, 5)), digits=0), type='cloudcover', digits=0)
	d.add(f'{C}.mid', '%c', d.series(lambda h, day, t: min(100, 15 + 70 * bell(t, 12, 7)), digits=0), type='cloudcover', digits=0)
	d.add(f'{C}.high', '%c', d.series(lambda h, day, t: min(100, 30 + 40 * bell(t, 8, 8)), digits=0), type='cloudcover', digits=0)
	d.add(f'{L}.irradiance.irradiance', 'W/m^2', irradiance, digits=0)
	d.add('environment.condition.condition', None, value=3, type='WeatherCode')
	for key, at in (('sunrise', '05:26'), ('sunset', '20:31')):
		# The render clock runs in UTC while the seed's place does not: four hours make up the difference.
		moment = datetime.fromisoformat(f'2026-06-21T{at}:00')
		d.add(f'{L}.{key}', 'epoch', value=int(time.mktime(moment.timetuple())) + 4 * 3600, type='datetime')
	d.add('astronomy.sun.hour', 'int', value=round(d.now, 3), title='Hour of day')
	d.add('astronomy.sun.remaining', 'int', value=671, title='Daylight left (minutes)')
	# No planes near by, so the last card shows the day's clock (home.py brings some over).
	d.add('aircraft.count', 'int', value=0, title='Aircraft in range')
	d.add('aircraft.active', 'int', value=0, title='A plane is near')
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
		d.add(f'indoor.temperature.heatIndex{sfx}', 'f', [round(a + max(0, h - 40) * 0.05, 1) for a, h in zip(temp, hum)])
	return d


def cap_(s, geom, color='$faint', **kw):
	"""A label: condensed, tracked capitals."""
	kw.setdefault('tracking', 0.16)
	return cap(s, geom, color, font=LABEL, weight='SemiBold', **kw)


def num(key, geom, color='$text', weight='Regular', font='$mono', **kw):
	"""A number. Fixed-width (Roboto Mono) unless it is the one big temperature, so digits line up and do not jump."""
	return val(key, geom, color, font=font, weight=weight, **kw)


def tile(caption, key, x, y, w, color='$text', h=TILE, group='global.detail', **kw):
	return [cap_(caption, g(x, y, w, CAP)), num(key, g(x, y + CAP + 0.4, w, h), color, group=group, **kw)]


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
		# The hint sizes the time for its widest form, so it does not grow at 1:00 and shrink at 10:00.
		{'format': '%-I:%M', 'alignment': 'CenterRight', 'format-hint': '10:00',
		 'geometry': {'height': '73%', 'width': '80%', 'x': '1.2%', 'y': '27%'}, 'margins': {'right': '10px'}},
		{'type': 'moon', 'geometry': {'height': '45%', 'width': '18.8%', 'x': '81.2%', 'y': '27%'}, 'glowStrength': 2, 'interval': {'minutes': 20}},
		{'format': '%p', 'filters': ['Lower'], 'geometry': {'height': '29.6%', 'width': '18.8%', 'x': '81.2%', 'y': '70.4%'}},
	]}


def room(caption, sfx, color, x, y, w, h, i):
	"""One room: its name, the temperature over its last day, and humidity and dew point (and feels like, if tall)."""
	key = lambda name: f'indoor.{name}{sfx}'
	temp = key('temperature.temperature')
	rows = [('HUMIDITY', key('humidity.humidity'), '$info', {'hint': '00%', 'unit': 'Inline'}),
	        ('DEW POINT', key('temperature.dewpoint'), '$good', {'hint': '00°', 'unit': 'Inline'})]
	out = [cap_(caption, g(x, y, w, CAP), color)]
	if h > 25:
		# Tall: the number, a day of temperature under it, and three readings in a row along the bottom.
		rows.append(('FEELS LIKE', key('temperature.heatIndex'), '$warn', {'hint': '00°', 'unit': 'Inline'}))
		body = h - CAP - 0.8 - 7.6
		out += [
			mini(temp, g(x, y + CAP + 0.8, w, body), color=color, hours=24, past=True, top='42%', bottom='0%', opacity=0.8, fill=0.3, weight=0.5,
			     glow=GLOW),
			num(temp, g(x, y + CAP + 0.8, w * 0.7, 11.5), '$text', weight='Bold', tracking=-0.06, unit='Inline', hint='00.0°', precision=1,
			    group='global.room', align='TopLeft'),
		]
		third = w / 3
		for j, (name, k, c, kw) in enumerate(rows):
			out += tile(name, k, x + j * third, y + h - 6.8, third - 0.6, c, h=4.4, group='global.detail', **kw)
		return out
	# Short: the number over its day on the left, two readings stacked on the right.
	hh = h - CAP - 0.8
	left = w * 0.6
	step = hh / len(rows)
	out += [
		mini(temp, g(x, y + CAP + 0.8, left - 0.8, hh), color=color, hours=24, past=True, top='45%', bottom='0%', opacity=0.8, fill=0.3, weight=0.5,
		     glow=GLOW),
		num(temp, g(x, y + CAP + 0.8, left - 0.8, hh * 0.62), '$text', weight='Bold', tracking=-0.06, unit='Inline', hint='00.0°', precision=1,
		    group='global.room', align='TopLeft'),
	]
	for j, (name, k, c, kw) in enumerate(rows):
		out += tile(name, k, x + left, y + CAP + 0.8 + j * step, w - left, c, h=step - CAP - 1.6, group='global.detail', **kw)
	return out


def board(rooms=INDOOR):
	B = [clock()]
	# Two reading sizes (Neal's rule): `global.room` for what is read across the room, `global.detail` for what is
	# read standing in front of it. Every number but the clock and the outdoor temperature is in one of the two.
	# ------------------------------------------------------------ outside, now
	x = 39.5
	B += [
		cap_('OUTSIDE', g(x, 2.8, 12, CAP), '$accent'),
		num(T, g(x - 0.4, 4.6, 16, 15.6), {'scale': '$temperature', 'of': T}, unit='Inline', hint='00°', weight='Black', tracking=-0.04, font='$body'),
		cap_('HIGH', g(x + 16.6, 4.8, 7, CAP)),
		num('environment.temperature.high', g(x + 16.6, 6.8, 8, 5.8), '$bad', hint='00', weight='Bold', group='global.room',
		    fmt={'unit_symbol': False}),
		cap_('LOW', g(x + 16.6, 13.4, 7, CAP)),
		num('environment.temperature.low', g(x + 16.6, 15.4, 8, 5.8), '$info', hint='00', weight='Bold', group='global.room',
		    fmt={'unit_symbol': False}),
		# The day's low to high on a 30 to 100 °F track, the temperature now as a line across it.
		bar(T, g(x, 20.9, 24.6, 2.2), 30, 100, track={'weight': '42%', 'color': '$rule'},
		    fill={'from': 'environment.temperature.low', 'to': 'environment.temperature.high', 'gradient': '$temperature', 'weight': '42%',
		          'glow': GLOW},
		    pointer={'type': 'line', 'color': '$accent', 'size': '100%'}),
		{'type': 'realtime.text', 'key': 'environment.condition.condition', 'title': False, 'alignment': 'CenterLeft', 'geometry': g(x, 23.6, 10, 2.4),
		 'display': {'valueLabel': {'color': '$muted', 'font': '$body', 'weight': 'Light', 'italic': True, 'matchingGroup': {'group': 'global.detail', 'matchAll': True}}}},
		text('feels', g(x + 10.2, 23.6, 3.6, 2.4), font='$body', weight='Light', italic=True, color='$faint', align='CenterRight', group='global.detail'),
		num('environment.temperature.feelsLike', g(x + 14.2, 23.6, 4, 2.4), unit='Inline', hint='00°', weight='SemiBold', align='CenterLeft', group='global.detail'),
		text('dew', g(x + 18.2, 23.6, 2.8, 2.4), font='$body', weight='Light', italic=True, color='$faint', align='CenterRight', group='global.detail'),
		num('environment.temperature.dewpoint', g(x + 21.4, 23.6, 4, 2.4), '$good', unit='Inline', hint='00°', weight='SemiBold', align='CenterLeft',
		    group='global.detail'),
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
		*tile('SUNRISE', f'{L}.sunrise', x + 19.8, 4.6, 9.6, '$warn', fmt='%-I:%M', hint='0:00'),
		*tile('SUNSET', f'{L}.sunset', x + 19.8, 12.2, 9.6, '$accent', fmt='%-I:%M', hint='0:00'),
		*tile('SUN · W/M²', f'{L}.irradiance.irradiance', x + 19.8, 19.8, 9.6, '$warn', hint='000', h=4.4),
	]
	# ------------------------------------------------------------ the days ahead
	B.append({
		'type': 'graph', 'name': 'forecast', 'geometry': g(1.5, 28.5, 69.5, 23.5),
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
	# ------------------------------------------------------------ the next sixteen hours, as numbers
	hours = list(range(2, 17, 2))
	at = lambda key, h: f'at({key}, {h}h)'
	readings = [('TEMP', T, '°F', 0, '$text'), ('RAIN', PR, 'in/h', 2, '$info'), ('WIND', f'{W}.speed.speed', 'mph', 0, '$series-6'), ('CLOUD', f'{C}.cover', '%', 0, '$muted'),
	            ('HUMID', 'environment.humidity.humidity', '%', 0, '$info')]
	B.append({'preset': 'table', 'name': 'hours', 'geometry': g(2, 52.6, 68.5, 13.4), 'props': {
		'columns': [{'head': f'+{h} H'} for h in hours],
		'rows': [{'label': f'{name} {unit}', 'color': color, 'precision': p, 'keys': [at(key, h) for h in hours]} for name, key, unit, p, color in readings],
		'labelWidth': '11%', 'headHeight': '15%', 'rowGap': '0px', 'font': '$mono', 'labelFont': LABEL, 'alignment': 'Right',
		'titleGroup': 'global.hoursHead', 'valueGroup': 'global.detail'}})
	# ------------------------------------------------------------ indoors
	top, height, gap = 28.5, 37, 2.2
	each = (height - gap * (len(rooms) - 1)) / len(rooms)
	for i, (caption, sfx, color) in enumerate(rooms):
		B += room(caption, sfx, color, 74.5, top + i * (each + gap), 23.5, each, i)
	# ------------------------------------------------------------ five cards
	Y, H, CW, GAP = 68.5, 29.5, 18.24, 1.2
	X = [2 + i * (CW + GAP) for i in range(5)]
	px, py = 1.2, 1.8
	iw = CW - 2 * px
	HERO = 10
	hero = lambda key, x, w, color, **kw: num(key, g(x, Y + py + CAP + 0.6, w, HERO), color, weight='Bold', tracking=-0.03, group='global.room', **kw)
	low = Y + 19.6
	cards = {}

	x = X[0] + px
	cards['wind'] = [
		cap_('WIND · MPH', g(x, Y + py, iw, CAP), '$series-6'),
		mini(f'{W}.speed.speed', g(x, Y + py + CAP + 0.6, 7.8, HERO), color='$series-6', lo=0, glow=GLOW),
		hero(f'{W}.speed.speed', x, 7.8, '$series-6', hint='00'),
		{'type': 'polar', 'name': 'rose', 'plot': 'rose', 'direction': f'{W}.direction.direction', 'speed': f'{W}.speed.speed', 'window': '24h',
		 'legend': False, 'rings': 3, 'compass': 4, 'gradient': 'WindSpeedGradient', 'geometry': g(x + 7.4, Y + 0.8, 9, 16.4)},
		*tile('GUST', f'{W}.speed.gust', x, low, 5, '$warn', hint='00'),
		*tile('PEAK', f'{W}.speed.gustMax', x + 5.4, low, 5.4, '$bad', hint='00'),
		*tile('FROM', f'{W}.direction.direction', x + 11.2, low, 4.6, '$info', hint='SSW'),
	]
	x = X[1] + px
	cards['rain'] = [
		cap_('RAIN · INCHES', g(x, Y + py, iw, CAP), '$info'),
		hero('environment.precipitation.daily', x, 9.6, '$info', precision=2, hint='0.00'),
		text('today', g(x + 9.8, Y + py + CAP + 6.8, 6, 2.6), font='$body', weight='Light', italic=True, color='$faint', align='BottomLeft'),
		capsules(mini(PR, g(x, Y + 14.4, iw, 4.6), color='$info', hours=24, lo=0, hi=0.4, kind='bar', top='4%', bottom='2%', opacity=1, glow=GLOW,
		              smooth=False)),
		*tile('NOW', PR, x, low, 5.2, '$info', precision=2, hint='0.00', h=4.4),
		*tile('PEAK', f'max({PR}, today)', x + 5.6, low, 5.2, '$series-4', precision=2, hint='0.00', h=4.4),
		*tile('+12 H', f'at({PR}, 12h)', x + 11.2, low, 4.6, '$faint', precision=2, hint='0.00', h=4.4),
	]
	x = X[2] + px
	trend = lambda s, color, when=None: {**text(s, g(0, 0, 100, 100), font=LABEL, weight='SemiBold', color=color, tracking=0.2),
	                                     **({'when': when} if when else {})}
	cards['pressure'] = [
		cap_('PRESSURE · INHG', g(x, Y + py, iw, CAP), '$series-4'),
		mini(P, g(x, Y + py + CAP + 0.6, iw, HERO + 1.5), color='$series-4', hours=24, past=True, top='30%', opacity=0.8, fill=0.3, weight=0.6, glow=GLOW),
		hero(P, x, iw, '$text', precision=2, hint='00.00'),
		{'type': 'switch', 'name': 'tendency', 'hold': '10m', 'fade': '0.4s', 'geometry': g(x, Y + 15, iw, 2.8), 'items': [
			trend('RISING ▲', '$good', f'{P} - at({P}, -3h) > 0.02 inHg'),
			trend('FALLING ▼', '$bad', f'at({P}, -3h) - {P} > 0.02 inHg'),
			trend('STEADY', '$faint')]},
		*tile('−3 H', f'{P} - at({P}, -3h)', x, low, 5, '$info', precision=2, hint='-0.00', h=4.4),
		*tile('−24 H', f'{P} - at({P}, -24h)', x + 5.4, low, 5, '$info', precision=2, hint='-0.00', h=4.4),
		*tile('+12 H', f'at({P}, 12h)', x + 10.8, low, 5, '$series-4', precision=2, hint='00.00', h=4.4),
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
			bar(f'{C}.{layer}', g(px_, Y + 4.2, 1.8, 8.6), 0, 1, color='$muted', orientation='vertical', track={'weight': '100%', 'color': '$rule'},
			    fill={'weight': '100%'}),
			cap_(name[0], g(px_ - 0.3, Y + 13.1, 2.4, CAP), group='global.layer', align='Center', tracking=0, **{'format-hint': 'M'}),
		]
	cards['sky'] += [
		mini(f'{C}.cover', g(x, Y + 14.6, iw, 4.4), color='$muted', hours=24, lo=0, hi=1, top='6%', bottom='2%', opacity=0.7, fill=0.25, weight=0.35),
		*tile('HUMIDITY %', 'environment.humidity.humidity', x, low, 7.6, '$info', hint='000', h=4.4, fmt={'unit_symbol': False}),
		*tile('VPD KPA', 'environment.pressure.vaporPressureDeficit', x + 8.2, low, 7.6, '$good', precision=2, hint='0.00', h=4.4,
		      fmt={'unit_symbol': False}),
	]
	x = X[4] + px
	# Planes near by take the card over (`aircraft.active`, from the Aircraft plugin, off until Aircraft.ini enables it);
	# otherwise the day's clock.
	body = g(x - 0.4, Y + py + CAP + 0.4, iw + 0.8, H - 2 * py - CAP - 0.4)
	cards['today'] = [{'type': 'switch', 'name': 'skyOrClock', 'hold': '2m', 'fade': '0.4s', 'geometry': g(x, Y + py, iw, H - 2 * py), 'items': [
		nest('planes', (x, Y + py, iw, H - 2 * py), [
			cap_('OVERHEAD · NM', g(x, Y + py, iw * 0.6, CAP), '$info'),
			num('aircraft.count', g(x + iw * 0.6, Y + py - 0.4, iw * 0.4, CAP + 0.8), '$info', weight='Bold', align='TopRight', hint='00'),
			{'type': 'polar', 'name': 'radar', 'plot': 'radar', 'prefix': 'aircraft', 'slots': 15, 'max': 30, 'labels': 4, 'sweep': True,
			 'rings': 3, 'accent': '$info', 'gradient': [{'at': 0, 'color': '$bad'}, {'at': 8000, 'color': '$warn'}, {'at': 40000, 'color': '$info'}],
			 'geometry': body}], fill=None, when='aircraft.active') | {'geometry': g(0, 0, 100, 100)},
		nest('dayClock', (x, Y + py, iw, H - 2 * py), [
			cap_('TODAY ROUND THE CLOCK', g(x, Y + py, iw, CAP), '$accent'),
			{'type': 'polar', 'name': 'dayClock', 'plot': 'clock', 'key': T, 'window': 'today', 'gradient': '$temperature', 'marks': False,
			 'geometry': body}], fill=None) | {'geometry': g(0, 0, 100, 100)}]}]
	for i, (name, items) in enumerate(cards.items()):
		B.append(nest(f'{name}Card', (X[i], Y, CW, H), items))
	return {'items': [{'type': 'group', 'name': 'board', 'items': B}]}


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
