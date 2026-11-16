"""Atmos: the weather flagship. Black ground, neon data, heavy and thin numerals against tracked caps."""
import math
import time
from datetime import datetime

from kit import *

T = 'environment.temperature.temperature'
P = 'environment.pressure.pressure'
PR = 'environment.precipitation.precipitation'
PC = 'environment.precipitation.probability'
W = 'environment.wind'
U = 'environment.light.uvi'
GLOW = {'strength': 1.4, 'reach': 2.0, 'passes': 6}
FREEZE = '2026-06-20T18:40:00'


def data():
	d = Data('atmos', 'A June evening before a wet Sunday: 74 F and clear at 6:40 pm, rain from late morning tomorrow, a clearing Monday.', 18 + 40 / 60)
	dayshift = {-1: 2.0, 0: 0.0, 1: -7.0, 2: -1.0, 3: 4.0}
	rain = lambda t: 0.34 * bell(t, 24 + 13, 3.2) + 0.08 * bell(t, 24 + 20, 1.5)
	cloud = lambda t: min(100, 18 + 82 * bell(t, 24 + 12, 9) + 25 * bell(t, -14, 5))
	temp = d.series(lambda h, day, t: 67 + 11 * daily(h, 15.5) + dayshift.get(day, 0) * (0.5 + 0.5 * sun(h)) - 3 * bell(t, 37, 4), noise=0.25, smooth=1)
	dew = d.series(lambda h, day, t: 55 + 2 * daily(h, 17) + 5 * bell(t, 36, 8), noise=0.2, smooth=1)
	hum = [round(min(99, max(22, 100 - (a - b) * 2.55))) for a, b in zip(temp, dew)]
	feels = [round(a + (0.045 * (h - 45) if a > 72 else -0.6), 1) for a, h in zip(temp, hum)]
	speed = d.series(lambda h, day, t: 6 + 3 * daily(h, 16) + 8 * bell(t, 34, 6), noise=0.5, smooth=1, lo=1)
	gust = [round(s * 1.55 + 1.5, 1) for s in speed]
	direction = d.series(lambda h, day, t: 205 + 28 * math.sin(t / 9) + 75 / (1 + math.exp(-(t - 40) / 4)), noise=5, smooth=1, digits=0)
	pressure = d.series(lambda h, day, t: 30.04 - 0.30 * bell(t, 37, 13) + 0.012 * math.sin(h / 12 * math.pi), digits=2)
	precipitation = d.series(lambda h, day, t: rain(t), lo=0, digits=2)
	chance = d.series(lambda h, day, t: min(96, 4 + 300 * rain(t) + 55 * bell(t, 35, 7)), lo=0, digits=0)
	uv = d.series(lambda h, day, t: 9.2 * sun(h) ** 1.6 * (1 - cloud(t) / 135), lo=0)
	sunlight = d.series(lambda h, day, t: 930 * sun(h) ** 1.2 * (1 - cloud(t) / 125), lo=0, digits=0)

	d.add(T, 'f', temp)
	d.add('environment.temperature.feelsLike', 'f', feels)
	d.add('environment.temperature.dewpoint', 'f', dew)
	today = temp[24:48]
	d.add('environment.temperature.high', 'f', value=round(max(today)))
	d.add('environment.temperature.low', 'f', value=round(min(today)))
	d.add('environment.humidity.humidity', '%', hum, digits=0)
	d.add(P, 'inHg', pressure, digits=2)
	d.add(f'{W}.speed.speed', WIND, speed, type='wind')
	d.add(f'{W}.speed.gust', WIND, gust, type='wind')
	d.add(f'{W}.direction.direction', 'º', direction, type='direction', digits=0)
	d.add(PR, ['in', 'hr'], precipitation, type='precipitationHourly', digits=2)
	d.add(PC, '%p', chance, digits=0)
	d.add('environment.precipitation.daily', ['in', 'day'], value=0.0, type='precipitationDaily', title='Today')
	d.add('environment.precipitation.tomorrow', ['in', 'day'], value=round(sum(precipitation[48:72]), 2), type='precipitationDaily', title='Tomorrow')
	i0 = d.index_now()
	# Invented: what a forecast plugin would publish for the next 24 hours.
	d.add('environment.precipitation.probabilityNext24', '%p', value=max(chance[i0:i0 + 24]), title='Chance, next 24 h')
	d.add('environment.precipitation.peakNext24', ['in', 'hr'], value=max(precipitation[i0:i0 + 24]), type='precipitationHourly', title='Peak rate, next 24 h')
	d.add('environment.clouds.cover.cover', '%c', d.series(lambda h, day, t: cloud(t), digits=0), type='cloudcover', digits=0)
	d.add('environment.visibility', 'mi', d.series(lambda h, day, t: 10 - 6.5 * bell(t, 37, 4)), digits=1)
	d.add(U, 'uvi', uv, type='index', title='UV Index')
	d.add('environment.light.irradiance.irradiance', 'W/m^2', sunlight, digits=0)
	d.add('environment.condition.condition', None, value=1, type='WeatherCode')
	rise = datetime.fromisoformat('2026-06-20T05:22:00')
	set_ = datetime.fromisoformat('2026-06-20T20:58:00')
	# The render's clock is UTC and the seed's place is four hours behind it.
	d.add('astronomy.sun.rise', 'epoch', value=int(time.mktime(rise.timetuple())) + 4 * 3600, type='datetime')
	d.add('astronomy.sun.set', 'epoch', value=int(time.mktime(set_.timetuple())) + 4 * 3600, type='datetime')
	d.add('astronomy.sun.hour', 'int', value=round(d.now, 3), title='Hour of day')
	d.add('astronomy.sun.remaining', 'int', value=138, title='Daylight left (minutes)')
	# Invented: an air-quality plugin (PurpleAir or AirNow) under environment.airQuality.
	aqi = d.series(lambda h, day, t: 38 + 16 * daily(h, 17) - 20 * bell(t, 38, 6), noise=1.5, smooth=1, lo=8, digits=0)
	d.add('environment.airQuality.index', 'int', aqi, digits=0, title='AQI')
	d.add('environment.airQuality.pm25', 'int', [round(a * 0.24, 1) for a in aqi], title='PM2.5')
	d.add('environment.airQuality.ozone', 'int', d.series(lambda h, day, t: 22 + 26 * sun(h), noise=1, digits=0), digits=0, title='Ozone ppb')
	d.add('environment.airQuality.pollen', 'int', value=7.2, title='Pollen')
	rooms = {'living': (73.4, 44, 91, 1.4), 'bedroom': (71.2, 47, 64, 1.0), 'office': (76.8, 39, 88, 2.2), 'nursery': (70.6, 49, 17, 0.8)}
	for i, (room, (t0, h0, battery, swing)) in enumerate(rooms.items()):
		ts = d.series(lambda h, day, t: t0 + swing * daily(h, 17 + i), noise=0.1, smooth=1)
		d.add(f'indoor.temperature.temperature#{room}', 'f', ts)
		d.add(f'indoor.humidity.humidity#{room}', '%', d.series(lambda h, day, t: h0 - 3 * daily(h, 16), noise=0.4, smooth=1, digits=0), type='humidity', digits=0)
		d.add(f'indoor.battery.battery#{room}', '%', value=battery)
	return d


THEME = {
	'extends': 'default',
	'colors': {
		'background': '#000000', 'surface': '#0c0a1a',
		'text': '#f4f1ff', 'muted': '#b9b3dd', 'faint': '#7d76a8', 'rule': '#2a2550',
		'accent': '#00f0ff', 'good': '#39ff88', 'warn': '#ffe600', 'bad': '#ff4a3d', 'info': '#38b6ff',
		'rain': '#3d8bff', 'wind': '#b6ff00', 'pink': '#ff2bd6', 'violet': '#a98bff',
		'series-1': '#00e5ff', 'series-2': '#ff9a1f', 'series-3': '#b6ff00', 'series-4': '#ffe600', 'series-5': '#8a5cff', 'series-6': '#ff2bd6',
	},
	'fonts': {'display': 'SF Compact Display', 'body': 'SF Pro Display', 'mono': 'Roboto Mono'},
	'scales': {
		'TemperatureGradient': {'10°F': '#8a2bff', '30°F': '#3d6bff', '45°F': '#00e5ff', '58°F': '#00ffa8',
		                        '68°F': '#b6ff00', '77°F': '#ffe600', '86°F': '#ff9a1f', '96°F': '#ff4a3d', '108°F': '#ff2a2a'},
		'PressureGradient': {0: '#8a5cff', 1: '#00e5ff'},
	},
}
TEMP = [{'at': a, 'color': c} for a, c in [(30, '#3d6bff'), (45, '#00e5ff'), (58, '#00ffa8'), (68, '#b6ff00'), (77, '#ffe600'), (86, '#ff9a1f'), (96, '#ff4a3d')]]

CAP = 1.5     # caption box height, board units
TILE = 5.6    # tile number box height


def tile(caption, key, x, y, w, color='$text', h=TILE, spark=None, group='global.tile', **kw):
	out = [cap(caption, g(x, y, w, CAP))]
	if spark:
		out.append(mini(spark.pop('key', key), g(x, y + CAP + 0.4, w * 0.92, h), **spark))
	out.append(val(key, g(x, y + CAP + 0.4, w, h), color, group=group, **kw))
	return out


def board():
	B = []
	# ------------------------------------------------------------ now
	B += [
		cap('OUTSIDE', g(2, 3, 20, CAP), '$accent'),
		val(T, g(1.7, 5, 21, 21.5), {'scale': '$temperature', 'of': T}, unit='Inline', hint='00°', weight='Black', tracking=-0.045),
		cap('HIGH', g(24, 6.2, 8, CAP)),
		val('environment.temperature.high', g(24, 8.6, 9, 7.6), '$bad', hint='00', weight='Black', outline=2.5, group='global.hollow', fmt={'unit_symbol': False}),
		cap('LOW', g(24, 16.6, 8, CAP)),
		val('environment.temperature.low', g(24, 19, 9, 7.6), '$info', hint='00', weight='Black', outline=2.5, group='global.hollow', fmt={'unit_symbol': False}),
		bar(T, g(2, 27.6, 31, 2.6), 40, 100, track={'weight': '34%', 'color': '$rule'},
		    fill={'from': 'environment.temperature.low', 'to': 'environment.temperature.high', 'gradient': 'TemperatureGradient', 'glow': GLOW},
		    pointer={'type': 'triangle', 'color': '$text', 'side': 'before'}),
		{'type': 'realtime.text', 'key': 'environment.condition.condition', 'title': False, 'alignment': 'CenterLeft', 'geometry': g(2, 30.3, 14, 2.6),
		 'display': {'valueLabel': {'color': '$muted', 'font': '$body', 'weight': 'Light', 'italic': True}}},
		text('feels', g(16.5, 30.3, 4, 2.6), font='$body', weight='Light', color='$faint', italic=True, align='CenterRight'),
		val('environment.temperature.feelsLike', g(21, 30.3, 4, 2.6), '$text', unit='Inline', hint='00°', weight='Medium', align='CenterLeft'),
		text('dew', g(25, 30.3, 3, 2.6), font='$body', weight='Light', color='$faint', italic=True, align='CenterRight'),
		val('environment.temperature.dewpoint', g(28.5, 30.3, 4, 2.6), '$good', unit='Inline', hint='00°', weight='Medium', align='CenterLeft'),
	]
	# ------------------------------------------------------------ clock
	C = (36, 3, 31, 30)
	B.append({'type': 'clock', 'name': 'clock', 'geometry': g(*C), 'items': [
		{'format': '%A', 'filters': ['Upper'], 'tracking': 0.32, 'font': '$display', 'weight': 'SemiBold', 'color': '$accent', 'alignment': 'BottomLeft',
		 'format-hint': 'WEDNESDAY', 'margins': 0, 'geometry': inside(C, 36.4, 3, 20, CAP)},
		{'format': '%-I:%M', 'font': '$body', 'weight': 'Thin', 'tracking': -0.02, 'alignment': 'BottomLeft', 'format-hint': '10:00',
		 'margins': 0, 'geometry': inside(C, 36, 5, 26, 21.5)},
		{'format': '%p', 'tracking': 0.2, 'font': '$display', 'weight': 'SemiBold', 'color': '$muted', 'alignment': 'BottomLeft',
		 'format-hint': 'PM', 'margins': 0, 'geometry': inside(C, 62, 24.4, 4, 1.7)},
		{'type': 'moon', 'glowStrength': 0, 'geometry': inside(C, 61.6, 6.4, 5.4, 8.6)},
		{'format': '%B %-d', 'filters': ['AddOrdinal'], 'font': '$body', 'weight': 'Light', 'italic': True, 'color': '$muted', 'alignment': 'CenterLeft',
		 'format-hint': 'September 30th', 'margins': 0, 'geometry': inside(C, 36.4, 30.3, 16, 2.6)},
	]})
	# ------------------------------------------------------------ sun
	B += [
		cap('DAYLIGHT LEFT', g(70, 3, 20, CAP), '$warn'),
		ring('astronomy.sun.remaining', g(70, 6, 18.5, 21), 5.37, 20.97, color='$warn', weight='3.2%', start=-90, end=90, glow=GLOW,
		     fill={'to': 'astronomy.sun.hour'},
		     markers=[{'value': 'astronomy.sun.hour', 'type': 'dot', 'width': '9%', 'halo': '2.4%', 'halo-color': '$background', 'color': '$warn'}],
		     **{'value-label': {'visible': True, 'position': 'center', 'size': '17%', 'format': 'duration'},
		        }),
		*tile('SUNRISE', 'astronomy.sun.rise', 90.5, 6, 7.5, '$warn', fmt='%-I:%M', hint='0:00'),
		*tile('SUNSET', 'astronomy.sun.set', 90.5, 15.2, 7.5, '$pink', fmt='%-I:%M', hint='0:00'),
		*tile('UV', U, 70, 24.6, 6, {'scale': 'UVIndexGradient', 'of': U}, hint='00', weight='Medium'),
		*tile('CLOUD %', 'environment.clouds.cover.cover', 77, 24.6, 6, '$violet', hint='000', fmt={'unit_symbol': False}),
		*tile('HUMID %', 'environment.humidity.humidity', 84, 24.6, 6, '$info', hint='000', fmt={'unit_symbol': False}),
		*tile('VIS MI', 'environment.visibility', 91, 24.6, 7, '$text', hint='00', precision=0),
	]
	# ------------------------------------------------------------ the days ahead
	B.append({
		'type': 'graph', 'name': 'forecast', 'geometry': g(2, 35.5, 69, 31),
		'timeframe': {'days': 2, 'hours': 18, 'offset': {'hours': -5}},
		'annotations': {'dayLabels': {'position': 'Center', 'alignment': 'Center', 'opacity': '13%', 'height': '40%'},
		                'hourLabels': {'alignment': 'BottomCenter', 'spacingIntervals': '6, 12', 'height': '4.2%'},
		                'lines': {'spacing': '12 mm', 'weight': 0.4}},
		'figures': [
			{'figure': 'sky', 'margins': {'top': '4%', 'bottom': '86%'},
			 'environment.temperature.dewpoint': {'plot': {'type': 'strip', 'pins': {
				 'key': PR, 'size': 34, 'at': 0.5, 'color': '$violet', 'spacing': 3.2,
				 'steps': [[0, 'wi:day-sunny'], [0.02, 'wi:sprinkle'], [0.1, 'wi:showers'], [0.25, 'wi:rain']]}}}},
			{'figure': 'arrows', 'margins': {'top': '15%', 'bottom': '78%'},
			 'environment.temperature.dewpoint': {'plot': {'type': 'strip', 'pins': {
				 'key': f'{W}.direction.direction', 'glyph': 'wi:direction-up', 'rotate': 180, 'size': 26, 'at': 0.5, 'spacing': 3.4, 'color': '$wind'}}}},
			{'figure': 'temperature', 'margins': {'top': '30%', 'bottom': '30%'},
			 T: {'labels': {'enabled': True},
			     'plot': {'type': 'plot', 'gradient': 'TemperatureGradient', 'weight': 1.1, 'glow': GLOW, 'fill': {'opacity': 0.4, 'fade': True}}, 'resolution': 2},
			 'environment.temperature.dewpoint': {'plot': {'type': 'plot', 'color': '$good', 'dashPattern': '5, 5', 'weight': 0.35, 'cap': 'square'}}},
			{'figure': 'chance', 'margins': {'top': '70%', 'bottom': '9%'}, 'min': 0, 'max': 1,
			 PC: {'plot': {'type': 'plot', 'color': '$pink', 'dashPattern': '3, 3', 'weight': 0.45, 'opacity': 0.9}}},
			{'figure': 'rain', 'margins': {'top': '70%', 'bottom': '9%'}, 'min': 0, 'max': 0.45,
			 PR: {'plot': {'type': 'bar', 'color': '$rain', 'width': 0.86, 'glow': GLOW}, 'smooth': False}},
		]})
	B += [
		cap('TODAY ROUND THE CLOCK', g(74, 35.5, 24, CAP), '$accent'),
		{'type': 'polar', 'name': 'dayClock', 'plot': 'clock', 'key': T, 'window': 'today', 'gradient': TEMP, 'geometry': g(74.5, 38.6, 23, 28)},
	]
	# ------------------------------------------------------------ cards
	Y, H, CW, GAP = 69.5, 27.5, 18.24, 1.2
	X = [2 + i * (CW + GAP) for i in range(5)]
	cards = {}
	px, py = 1.2, 1.7
	iw = CW - 2 * px
	HERO = 9.5
	hero = lambda key, x, w, color, **kw: val(key, g(x, Y + py + CAP + 0.6, w, HERO), color, weight='Bold', tracking=-0.03, group='global.hero2', **kw)

	# wind
	x = X[0] + px
	cards['wind'] = [
		cap('WIND · MPH', g(x, Y + py, iw, CAP), '$wind'),
		mini(f'{W}.speed.speed', g(x, Y + py + CAP + 0.6, 7.6, HERO), color='$wind', lo=0, glow=GLOW),
		hero(f'{W}.speed.speed', x, 7.6, '$wind', hint='00'),
		{'type': 'polar', 'name': 'rose', 'plot': 'rose', 'direction': f'{W}.direction.direction', 'speed': f'{W}.speed.speed', 'window': '24h',
		 'legend': False, 'rings': 3, 'compass': 4,
		 'gradient': [{'at': 0, 'color': '#3d8bff'}, {'at': 6, 'color': '#00e5ff'}, {'at': 11, 'color': '#b6ff00'}, {'at': 17, 'color': '#ffe600'}],
		 'geometry': g(x + 7.2, Y + 0.6, 9.2, 15.4)},
		*tile('GUST', f'{W}.speed.gust', x, Y + 16.6, 5, '$warn', hint='00'),
		*tile('PEAK', f'max({W}.speed.gust, today)', x + 5.4, Y + 16.6, 5, '$bad', hint='00'),
		*tile('FROM', f'{W}.direction.direction', x + 10.8, Y + 16.6, 5, '$info', hint='SSW'),
	]
	# rain
	x = X[1] + px
	cards['rain'] = [
		cap('RAIN · NEXT 24 H', g(x, Y + py, iw, CAP), '$rain'),
		hero('environment.precipitation.probabilityNext24', x, 9, '$rain', unit='Inline', hint='00%'),
		text('chance', g(x + 9.3, Y + py + CAP + 6.6, 6, 2.6), font='$body', weight='Light', italic=True, color='$faint', align='BottomLeft'),
		mini(PR, g(x, Y + 13.2, iw, 5), color='$rain', hours=24, lo=0, hi=0.45, kind='bar', top='4%', bottom='4%', opacity=1, glow=GLOW, smooth=False),
		*tile('NOW IN/HR', PR, x, Y + 18.6, 5, '$rain', precision=2, hint='0.00', h=4.4),
		*tile('PEAK', 'environment.precipitation.peakNext24', x + 5.4, Y + 18.6, 5, '$info', precision=2, hint='0.00', h=4.4),
		*tile('TOMORROW IN', 'environment.precipitation.tomorrow', x + 10.8, Y + 18.6, 5.2, '$violet', precision=2, hint='0.00', h=4.4),
	]
	# pressure
	x = X[2] + px
	S = (x, Y + 13.6, iw, 3)
	trend = lambda s, color, when=None: {**text(s, g(0, 0, 100, 100), weight='SemiBold', color=color, tracking=0.18), **({'when': when} if when else {})}
	cards['pressure'] = [
		cap('PRESSURE · INHG', g(x, Y + py, iw, CAP), '$violet'),
		mini(P, g(x, Y + py + CAP + 0.6, iw, HERO + 1.5), gradient='PressureGradient', hours=24, past=True, top='30%', opacity=0.85, fill=0.3, weight=0.6, glow=GLOW),
		hero(P, x, iw, '$text', precision=2, hint='00.00'),
		{'type': 'switch', 'name': 'tendency', 'hold': '10m', 'fade': '0.4s', 'geometry': g(*S), 'items': [
			trend('RISING ▲', '$good', f'{P} - at({P}, -3h) > 0.02 inHg'),
			trend('FALLING ▼', '$bad', f'at({P}, -3h) - {P} > 0.02 inHg'),
			trend('STEADY', '$muted')]},
		*tile('3 H', f'{P} - at({P}, -3h)', x, Y + 18.6, 5, '$info', precision=2, hint='-0.00', h=4.4),
		*tile('24 H', f'{P} - at({P}, -24h)', x + 5.4, Y + 18.6, 5, '$info', precision=2, hint='-0.00', h=4.4),
		*tile('IN 12 H', f'at({P}, 12h)', x + 10.8, Y + 18.6, 5.2, '$violet', precision=2, hint='00.00', h=4.4),
	]
	# air
	x = X[3] + px
	A = 'environment.airQuality'
	cards['air'] = [
		cap('AIR QUALITY', g(x, Y + py, iw, CAP), '$good'),
		ring(f'{A}.index', g(x - 0.4, Y + 4.4, 9.4, 15.6), 0, 200, color='zone', weight='6%', start=-130, end=130, glow=GLOW,
		     zones=[{'from': 0, 'to': 50, 'color': '$good'}, {'from': 50, 'to': 100, 'color': '$warn'},
		            {'from': 100, 'to': 150, 'color': '#ff9a1f'}, {'from': 150, 'to': 200, 'color': '$bad'}],
		     **{'value-label': {'visible': True, 'position': 'center', 'size': '30%', 'format': {'precision': 0}},
		        'sub-label': {'text': 'AQI · GOOD', 'size': '9.5%', 'offset': {'y': 0.09}, 'color': '$good'}}),
		*tile('PM 2.5', f'{A}.pm25', x + 9.6, Y + 4.6, 6, '$good', precision=1, hint='00.0', h=4.4),
		*tile('OZONE PPB', f'{A}.ozone', x + 9.6, Y + 11.6, 6, '$info', hint='00', h=4.4),
		*tile('POLLEN', f'{A}.pollen', x + 9.6, Y + 18.6, 6, '$warn', precision=1, hint='0.0', h=4.4),
		mini(f'{A}.index', g(x, Y + 20.4, 9, 5.4), color='$good', hours=24, past=True, top='10%', opacity=0.9, fill=0.3),
	]
	# rooms
	x = X[4] + px
	R = cards['rooms'] = [cap('INDOORS', g(x, Y + py, 8, CAP), '$accent'),
	                      {**cap('°F', g(x + 6.6, Y + py, 3.6, CAP)), 'alignment': 'BottomRight'},
	                      {**cap('RH %', g(x + 10.6, Y + py, 5.2, CAP)), 'alignment': 'BottomRight'}]
	for i, (room, label) in enumerate([('living', 'Living'), ('bedroom', 'Bedroom'), ('office', 'Office'), ('nursery', 'Nursery')]):
		y = Y + 4.6 + i * 5.5
		t = f'indoor.temperature.temperature#{room}'
		R += [
			text(label, g(x, y + 0.5, 6.6, 2.3), font='$body', weight='Regular', color='$muted', group='global.rowlabel'),
			val(t, g(x + 6.6, y, 3.6, 3.4), {'scale': '$temperature', 'of': t}, hint='00', align='CenterRight', weight='Medium', group='global.row', fmt={'unit_symbol': False}),
			val(f'indoor.humidity.humidity#{room}', g(x + 10.6, y, 5.2, 3.4), '$info', hint='00', align='CenterRight', weight='Medium', group='global.row', fmt={'unit_symbol': False}),
			bar(f'indoor.battery.battery#{room}', g(x, y + 3.7, iw, 0.5), 0, 1, color='$bad' if room == 'nursery' else '$good', track={'weight': '100%', 'color': '$rule'}),
		]
	for i, (name, items) in enumerate(cards.items()):
		B.append(nest(f'{name}Card', (X[i], Y, CW, H), items))
	return {'theme': THEME, 'items': [{'type': 'group', 'name': 'board', 'items': B}]}


HEADER = """
Atmos: the weather showcase. A June evening before a wet Sunday.

Three bands. Top: the temperature in a heavy face beside the clock in a thin one, with the day's high and low as hollow
numerals and the sun's arc. Middle: two and a half days of forecast with the day names behind it, and today's
temperature round a 24 hour clock. Bottom: five cards (wind rose, rain, pressure with a tendency switch, air quality,
rooms).

Invented data: environment.airQuality.* (index, pm25, ozone, pollen) and environment.precipitation.{tomorrow, probabilityNext24, peakNext24}.
Fonts: SF Pro Display and SF Compact Display (Apple; not bundled). Set theme fonts to change them.
"""

if __name__ == '__main__':
	write('atmos', HEADER, board(), data(), FREEZE)
