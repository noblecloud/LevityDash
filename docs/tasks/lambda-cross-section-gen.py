#!/usr/bin/env python3
"""Writes docs/tasks/lambda-cross-section.levity: the neon cross-section. Needs SF Pro Display and SF Compact Display installed (Apple, developer.apple.com/fonts; not bundled). Tiles: a small caption over a big number that fills its cell."""
import sys
import os
import yaml

TH = os.environ.get('TH', '5.5mm')

CAP = '5.6mm'     # caption over a tile
VAL = '16mm'     # a tile's number; the cell usually limits it first
HERO2 = '19mm'    # room, pressure, alert heroes
HERO = '30mm'     # the outside temperature


def g(x, y, w, h):
	return {'x': f'{x}%', 'y': f'{y}%', 'width': f'{w}%', 'height': f'{h}%'}


def head(text, color='$accent'):
	return {'text': text, 'height': '10mm', 'font': '$display', 'weight': 'SemiBold', 'color': color,
	        'alignment': 'CenterLeft', 'matchingGroup': {'group': 'global.head', 'matchAll': True}}


def panel(name, title, items, size=None, color='$accent'):
	p = {'type': 'titled-group', 'name': name}
	if size:
		p['size'] = size
	p['title'] = head(title, color)
	p['items'] = items
	return p


def cap(text, geom, color='$muted'):
	return {'type': 'text', 'text': text, 'font': '$display', 'weight': 'Medium', 'color': color,
	        'alignment': 'BottomLeft', 'text-height': CAP, 'geometry': geom}


def val(key, geom, color='$text', precision=0, unit='Hidden', hint=None, height=VAL, group='global.tile', align='BottomLeft', fmt=None, weight='Regular'):
	label = {'text-height': height, 'color': color, 'font': '$body', 'weight': weight}
	if group:
		label['matchingGroup'] = {'group': group, 'matchAll': True}
	d = {'unitPosition': unit, 'precision': precision, 'valueLabel': label}
	if hint:
		d['format-hint'] = hint
	if fmt:
		d['format'] = fmt
	return {'type': 'realtime.text', 'key': key, 'title': False, 'alignment': align, 'display': d, 'geometry': geom}


def tile(caption, key, x, y, w, h, color='$text', capcolor='$muted', spark=None, **kw):
	"""Caption on the top 30% of the cell, the number under it; `spark` puts a faded mini graph of the key behind the number."""
	out = [cap(caption, g(x, y, w, h * 0.30), capcolor)]
	if spark is not None:
		out.append(mini(spark.pop('key', key), g(x, y + h * 0.30, w * 0.94, h * 0.70), **spark))
	return out + [val(key, g(x, y + h * 0.30, w, h * 0.70), color, **kw)]


def tiles(spec, x0, y0, w, h, cols):
	"""spec: list of (caption, key, opts) laid out row by row."""
	rows = (len(spec) + cols - 1) // cols
	cw, rh = w / cols, h / rows
	out = []
	for i, (c, k, o) in enumerate(spec):
		r, cl = divmod(i, cols)
		out += tile(c, k, round(x0 + cl * cw, 2), round(y0 + r * rh, 2), round(cw, 2), round(rh, 2), **o)
	return out


import itertools
_minis = itertools.count(1)


def mini(key, geom, color=None, gradient=None, hours=12, past=False, lo=None, hi=None, opacity=0.55, fill=0.25, figure=None, top='60%'):
	"""A mini graph with no labels behind a number: the next `hours`, or with `past` the last ones. The line is thin and
	the area under it fades out, so the number on top stays the thing you read."""
	plot = {'type': 'plot', 'weight': 0.45, 'opacity': opacity, 'fill': {'opacity': fill, 'fade': True}}
	if gradient:
		plot['gradient'] = gradient
	else:
		plot['color'] = color or '$accent'
	fig = {'figure': figure or f'mini{next(_minis)}', 'margins': {'top': top, 'bottom': '2%'}, key: {'plot': plot}}
	if lo is not None:
		fig['min'] = lo
	if hi is not None:
		fig['max'] = hi
	return {'type': 'mini-graph', 'geometry': geom,
	        'timeframe': {'hours': hours, 'lookback': {'hours': hours + 2}, 'offset': {'hours': -hours if past else -0.5}},
	        'annotations': {'dayLabels': {'enabled': False}, 'hourLabels': {'enabled': False}, 'lines': {'enabled': False}},
	        'indicator': {'opacity': 0}, 'figures': [fig]}


def spark(key, geom, figure, plot, lo=None, hi=None, hours=12):
	p = {'key': key, 'hours': hours, 'figure': figure, 'plot': plot, 'top': '8%', 'bottom': '4%'}
	if lo is not None:
		p['min'], p['max'] = lo, hi
	return {'preset': 'sparkline', 'geometry': geom, 'props': p}


def temp_scale(key):
	return {'scale': '$temperature', 'of': key}


# ---------------------------------------------------------------- theme
theme = {
	'extends': 'default',
	'colors': {
		'background': '#000000', 'surface': '#100c22',
		'text': '#f4f1ff', 'muted': '#d2ccf5', 'faint': '#9a92c8', 'rule': '#3b3372',
		'accent': '#00f0ff', 'good': '#39ff88', 'warn': '#ffe600', 'bad': '#ff3b3b', 'info': '#38b6ff',
		'rain': '#3d8bff', 'wind': '#b6ff00', 'cloud': '#c9b8ff', 'cloud-2': '#b08cff', 'soil': '#ff9a1f', 'pink': '#ff2bd6',
		'series-1': '#00e5ff', 'series-2': '#ff9a1f', 'series-3': '#b6ff00', 'series-4': '#ffe600',
		'series-5': '#8a5cff', 'series-6': '#ff9a1f',
	},
	'fonts': {'display': 'SF Compact Display', 'body': 'SF Pro Display', 'mono': 'Roboto Mono'},
	'scales': {
		'TemperatureGradient': {'10°F': '#8a2bff', '30°F': '#3d6bff', '45°F': '#00e5ff', '58°F': '#00ffa8',
		                        '68°F': '#b6ff00', '77°F': '#ffe600', '86°F': '#ff9a1f', '96°F': '#ff4a3d', '108°F': '#ff2a2a'},
		'UVIndexGradient': {0: '#39ff88', 3: '#ffe600', 6: '#ff9a1f', 8: '#ff3b3b', 11: '#9d5cff'},
		'WindSpeedGradient': {0: '#3d8bff', 8: '#00e5ff', 16: '#b6ff00', 26: '#ffe600', 40: '#ff3b3b'},
		'PressureGradient': {0: '#8a5cff', 1: '#00e5ff'},
	},
}

GLOW = {'strength': 1.5, 'reach': 2.0, 'passes': 6}
T = 'environment.temperature.temperature'

# ---------------------------------------------------------------- sky
# The moon sits in the top left corner and the weekday and date beside it, so the time below has nothing empty over
# it. The time and am/pm both sit on the bottom edge; each hint has no descender, so the bottom of its fit rect is
# the baseline, and the two baselines meet.
clock = {
	'type': 'clock', 'name': 'clock', 'size': '22%',
	'items': [
		# No glow: with the glow effect on, the lit face is drawn offset from the dark disc (in the round 1 layout it
		# fell outside the panel, so only the dark disc showed).
		{'type': 'moon', 'glowStrength': 0, 'interval': {'minutes': 20}, 'geometry': g(0, 0, 22, 38)},
		{'format': '%A', 'alignment': 'BottomLeft', 'font': '$display', 'weight': 'SemiBold', 'color': '$accent', 'format-hint': 'Wednesday',
		 'margins': 0, 'geometry': g(26, 0, 74, 20)},
		{'format': '%B %-d', 'alignment': 'TopLeft', 'filters': ['AddOrdinal'], 'font': '$display', 'weight': 'Medium', 'format-hint': 'September 30th',
		 'color': '$muted', 'margins': 0, 'geometry': g(26, 21, 74, 17)},
		{'format': '%-I:%M', 'font': '$display', 'weight': 'SemiBold', 'alignment': 'BottomRight', 'format-hint': '10:00',
		 'margins': 0, 'geometry': g(0, 40, 82, 60)},
		{'format': '%p', 'font': '$display', 'weight': 'SemiBold', 'filters': ['Lower'], 'color': '$info', 'alignment': 'BottomLeft',
		 'format-hint': 'am', 'margins': 0, 'geometry': g(83, 78, 17, 22)},
	],
}

CL = 'environment.clouds.cover'


def cloud_tile(caption, key, x, y, color):
	# A bar rather than a mini graph: cover sits at 100% for hours, and a flat line at the top of the scale reads
	# as a strike through the number.
	return [
		cap(caption, g(x, y, 48, 14)),
		val(key, g(x, y + 14, 48, 26), color, unit='Inline', hint='000%'),
		{'type': 'realtime.bar', 'key': key, 'title': False, 'geometry': g(x, y + 42, 48, 6),
		 'display': {'range': {'min': 0, 'max': 100}, 'track': {'weight': '60%'},
		             'fill': {'color': color, 'glow': GLOW}, 'value-label': {'visible': False}}},
	]


cloud = panel('cloud', 'CLOUD', [
	*cloud_tile('TOTAL', f'{CL}.cover', 0, 0, '$cloud'),
	*cloud_tile('HIGH', f'{CL}.high', 52, 0, '$cloud-2'),
	*cloud_tile('MID', f'{CL}.mid', 0, 52, '$cloud-2'),
	*cloud_tile('LOW', f'{CL}.low', 52, 52, '$cloud-2'),
], size='16%')

sun = panel('sun', 'SUN AND MOON', tiles([
	('RISE', 'astronomy.sun.rise', {'color': '$warn', 'fmt': '%-I:%M', 'hint': '0:00'}),
	('SET', 'astronomy.sun.set', {'color': '$pink', 'fmt': '%-I:%M', 'hint': '0:00'}),
	('DAYLIGHT', 'astronomy.sun.remaining', {'color': '$warn', 'fmt': 'duration', 'hint': '0h 00m'}),
	('MOON', 'astronomy.moon.phase', {'color': '$cloud', 'unit': 'Inline', 'hint': '00%'}),
], 0, 0, 100, 100, 2), size='16%')

P = 'environment.pressure.pressure'
pressure = panel('pressure', 'PRESSURE INHG', [
	spark(P, g(0, 0, 100, 58), 'pressure', {'type': 'plot', 'gradient': 'PressureGradient', 'weight': 0.7, 'opacity': 0.8, 'glow': GLOW,
	                                         'fill': {'opacity': 0.3, 'fade': True}}),
	val(P, g(0, 0, 62, 46), '$text', precision=2, hint='00.00', height=HERO2, group='global.hero2', weight='Bold'),
	{'type': 'switch', 'name': 'tendency', 'hold': '10m', 'fade': '0.4s', 'geometry': g(0, 46, 62, 13), 'items': [
		{'type': 'text', 'text': 'RISING ▲', 'font': '$display', 'weight': 'SemiBold', 'text-height': CAP, 'color': '$good', 'alignment': 'CenterLeft',
		 'when': f'{P} - at({P}, -3h) > 0.03 inHg'},
		{'type': 'text', 'text': 'FALLING ▼', 'font': '$display', 'weight': 'SemiBold', 'text-height': CAP, 'color': '$bad', 'alignment': 'CenterLeft',
		 'when': f'at({P}, -3h) - {P} > 0.03 inHg'},
		{'type': 'text', 'text': 'STEADY', 'font': '$display', 'weight': 'SemiBold', 'text-height': CAP, 'color': '$muted', 'alignment': 'CenterLeft'},
	]},
	*tiles([
		('3 H', f'{P} - at({P}, -3h)', {'precision': 2, 'color': '$info', 'hint': '-0.00'}),
		('24 H', f'{P} - at({P}, -24h)', {'precision': 2, 'color': '$info', 'hint': '-0.00'}),
		('VIS MI', 'environment.visibility', {'precision': 1, 'hint': '00.0', 'spark': {'color': '$muted'}}),
	], 0, 60, 100, 40, 3),
])

sky = {'type': 'stack', 'name': 'sky', 'direction': 'Horizontal', 'size': '22%', 'spacing': '4mm',
       'dividers': {'enabled': True, 'opacity': '60%', 'size': '80%'},
       'items': [clock, cloud, sun, pressure]}

# ---------------------------------------------------------------- surface
now = {'type': 'group', 'name': 'now', 'size': '20%', 'items': [
	val(T, g(0, 0, 100, 33), temp_scale(T), unit='Inline', hint='00°', height=HERO, group=None, weight='Bold', align='CenterLeft'),
	{'type': 'realtime.text', 'key': 'environment.condition.condition', 'title': False, 'alignment': 'CenterLeft',
	 'display': {'valueLabel': {'color': '$info', 'text-height': '6mm', 'font': '$display', 'weight': 'SemiBold'}},
	 'geometry': g(0, 33, 100, 8)},
	{'type': 'realtime.bar', 'key': T, 'title': False, 'geometry': g(0, 41, 100, 13),
	 'display': {'range': {'min': 30, 'max': 100}, 'track': {'weight': '26%', 'color': '$rule'},
	             'fill': {'from': 'environment.temperature.low', 'to': 'environment.temperature.high', 'gradient': 'TemperatureGradient', 'glow': GLOW},
	             'pointer': {'type': 'triangle', 'color': '$text', 'side': 'before'},
	             'major': {'interval': 10, 'side': 'after', 'labels': True, 'size': '45%'},
	             'value-label': {'visible': False}}},
	*tiles([
		('LOW', 'environment.temperature.low', {'unit': 'Inline', 'color': '$info', 'hint': '00°'}),
		('HIGH', 'environment.temperature.high', {'unit': 'Inline', 'color': '$bad', 'hint': '00°'}),
		('FEELS', 'environment.temperature.feelsLike', {'unit': 'Inline', 'color': temp_scale('environment.temperature.feelsLike'), 'hint': '00°',
		                                                'spark': {'gradient': 'TemperatureGradient'}}),
		('DEW', 'environment.temperature.dewpoint', {'unit': 'Inline', 'color': '$good', 'hint': '00°', 'spark': {'color': '$good'}}),
		('HUMID', 'environment.humidity.humidity', {'unit': 'Inline', 'color': '$info', 'hint': '00%', 'spark': {'color': '$info', 'lo': 0, 'hi': 100}}),
		('VPD KPA', 'environment.pressure.vaporPressureDeficit', {'precision': 1, 'color': '$accent', 'hint': '0.0', 'spark': {'color': '$accent'}}),
	], 0, 55, 100, 45, 3),
]}

forecast = {
	'type': 'graph', 'name': 'forecast', 'timeframe': {'days': 2, 'hours': 12},
	'annotations': {'dayLabels': {'enabled': False},
	                'hourLabels': {'alignment': 'BottomCenter', 'spacingIntervals': '3, 6, 12'},
	                'lines': {'spacing': '8 mm', 'weight': 0.5}},
	'figures': [
		{'figure': 'glyphs', 'margins': {'top': '7%', 'bottom': '85%'},
		 'environment.temperature.dewpoint': {'plot': {'type': 'strip', 'pins': {
			 'key': 'environment.precipitation.precipitation', 'size': 24, 'at': 0.5, 'color': '$cloud',
			 'steps': [[0, 'wi:day-sunny'], [0.02, 'wi:sprinkle'], [0.1, 'wi:showers'], [0.3, 'wi:rain']]}}}},
		{'figure': 'windarrows', 'margins': {'top': '15%', 'bottom': '79%'},
		 'environment.temperature.dewpoint': {'plot': {'type': 'strip', 'pins': {
			 'key': 'environment.wind.direction.direction', 'glyph': 'wi:direction-up', 'rotate': 180,
			 'size': 20, 'at': 0.5, 'color': '$wind'}}}},
		{'figure': 'temperature', 'margins': {'bottom': '30%', 'top': '25%'},
		 T: {'labels': {'enabled': True},
		     'plot': {'type': 'plot', 'gradient': 'TemperatureGradient', 'weight': 1.0, 'glow': GLOW,
		              'fill': {'opacity': 0.45, 'fade': True}}, 'resolution': 2},
		 'environment.temperature.feelsLike': {'plot': {'type': 'plot', 'gradient': 'TemperatureGradient', 'weight': 0.35, 'opacity': 0.6}, 'resolution': 2},
		 'environment.temperature.dewpoint': {'plot': {'type': 'plot', 'cap': 'square', 'color': '$good', 'dashPattern': '5, 5', 'weight': 0.35}}},
		{'figure': 'chance', 'margins': {'bottom': '5%', 'top': '68%'}, 'min': 0, 'max': 1,
		 'environment.precipitation.probability': {'plot': {'type': 'plot', 'color': '$pink', 'dashPattern': '3, 3', 'weight': 0.5, 'opacity': 0.9}}},
		{'figure': 'precipitation', 'margins': {'bottom': '5%', 'top': '68%'}, 'min': 0, 'max': 0.5,
		 'environment.precipitation.precipitation': {'plot': {'type': 'bar', 'color': '$rain', 'width': 0.9, 'glow': GLOW}, 'smooth': False}},
	],
}


def alert(name, when, title, color, hero, caption, rest):
	return {'type': 'titled-group', 'name': name, 'when': when, 'title': head(title, color), 'items': [
		val(hero[0], g(0, 0, 100, 32), color, height=HERO2, group='global.hero2', weight='Bold', **hero[1]),
		cap(caption, g(0, 30, 100, 9)),
		*tiles(rest, 0, 42, 100, 58, 2),
	]}


PR = 'environment.precipitation.precipitation'
U = 'environment.light.uvi'
# An alert whose `when` holds takes the panel; otherwise the polar day clock shows. It used to share the quiet time
# with a TODAY panel on a 20 s cycle, which read as the clock vanishing and coming back.
watch = {'type': 'switch', 'name': 'watch', 'size': '22%', 'hold': '2m', 'fade': '0.5s', 'items': [
	alert('rainAlert', 'max(environment.precipitation.probability, 12h) > 50%', 'RAIN COMING', '$rain',
	      ('max(environment.precipitation.probability, 12h)', {'unit': 'Inline'}), 'CHANCE IN THE NEXT 12 H', [
		      ('NOW IN/HR', PR, {'precision': 2, 'color': '$rain'}),
		      ('PEAK IN/HR', f'max({PR}, 12h)', {'precision': 2, 'color': '$rain'}),
		      ('TODAY IN', 'environment.precipitation.rainDaily', {'precision': 2, 'color': '$info'}),
		      ('NEXT 12 H IN', f'avg({PR}, 12h) * 12', {'precision': 2, 'color': '$info'}),
	      ]),
	alert('frostAlert', f'min({T}, 24h) < 34°F', 'FROST TONIGHT', '$info',
	      ('environment.temperature.low', {'unit': 'Inline'}), 'LOW TONIGHT', [
		      ('WIND MPH', 'environment.wind.speed.speed', {'color': '$wind'}),
		      ('DEW POINT', 'environment.temperature.dewpoint', {'unit': 'Inline', 'color': '$good'}),
		      ('SOIL SURFACE', 'environment.soil.temperature.temperature', {'unit': 'Inline', 'color': '$soil'}),
		      ('CLOUD', 'environment.clouds.cover.cover', {'unit': 'Inline', 'color': '$cloud'}),
	      ]),
	alert('windAlert', 'environment.wind.speed.gust > 25mph', 'GUSTY', '$wind',
	      ('environment.wind.speed.gust', {}), 'MPH GUST NOW', [
		      ('WIND', 'environment.wind.speed.speed', {'color': '$wind'}),
		      ('PEAK 12 H', 'max(environment.wind.speed.gust, 12h)', {'color': '$warn'}),
		      ('AT 80 M', 'environment.wind.speed.80m', {'color': '$info'}),
		      ('AT 180 M', 'environment.wind.speed.180m', {'color': '$info'}),
	      ]),
	alert('uvAlert', f'{U} >= 6 uvi', 'STRONG SUN', '$bad',
	      (U, {}), 'UV INDEX', [
		      ('PEAK TODAY', f'max({U}, today)', {'color': '$warn'}),
		      ('SUN W/M²', 'environment.light.irradiance.irradiance', {'color': '$warn'}),
		      ('CLOUD', 'environment.clouds.cover.cover', {'unit': 'Inline', 'color': '$cloud'}),
		      ('SUN ELEV', 'astronomy.sun.elevation', {'unit': 'Inline'}),
	      ]),
	{'preset': 'polar-card', 'name': 'dayClock', 'props': {
		'title': 'Today round the clock', 'plot': 'clock', 'key': T, 'window': 'today',
		'gradient': [{'at': a, 'color': c} for a, c in [(30, '#3d6bff'), (45, '#00e5ff'), (58, '#00ffa8'), (68, '#b6ff00'),
		                                                  (77, '#ffe600'), (86, '#ff9a1f'), (96, '#ff4a3d')]]}},
]}

surface = {'type': 'stack', 'name': 'surface', 'direction': 'Horizontal', 'spacing': '4mm', 'items': [now, forecast, watch]}

# ---------------------------------------------------------------- ground


def room(name, title, ident, hum_color, tlo, thi):
	t = f'indoor.temperature.temperature#{ident}'
	h = f'indoor.humidity.humidity#{ident}'
	b = f'indoor.battery.battery#{ident}'
	return panel(name, title, [
		mini(t, g(0, 12, 50, 48), gradient='TemperatureGradient', hours=24, past=True, lo=tlo, hi=thi, opacity=0.9, fill=0.4, figure='indoor', top='5%'),
		mini(h, g(52, 12, 48, 48), color=hum_color, hours=24, past=True, opacity=0.9, fill=0.4, figure='humid', top='35%'),
		cap('TEMP °F · 24 H', g(0, 0, 50, 10)),
		val(t, g(0, 10, 50, 34), temp_scale(t), unit='Hidden', hint='00', fmt={'unit_symbol': False}, height=HERO2, group='global.hero2', weight='Bold'),
		cap('HUMIDITY %', g(52, 0, 48, 10)),
		val(h, g(52, 10, 48, 34), hum_color, unit='Inline', hint='00%', height=HERO2, group='global.hero2', weight='Bold'),
		*tiles([
			('LO', f'min({t}, 24h)', {'color': '$info', 'hint': '000', 'fmt': {'unit_symbol': False}}),
			('HI', f'max({t}, 24h)', {'color': '$bad', 'hint': '000', 'fmt': {'unit_symbol': False}}),
		], 0, 62, 50, 26, 2),
		*tiles([
			('LO', f'min({h}, 24h)', {'color': hum_color, 'hint': '000', 'fmt': {'unit_symbol': False}}),
			('HI', f'max({h}, 24h)', {'color': hum_color, 'hint': '000', 'fmt': {'unit_symbol': False}}),
		], 52, 62, 48, 26, 2),
		{**cap('BATTERY', g(0, 89, 30, 11), '$muted'), 'alignment': 'CenterLeft'},
		{'type': 'realtime.bar', 'key': b, 'title': False, 'geometry': g(32, 89, 68, 11),
		 'display': {'style': 'battery', 'range': {'min': 0, 'max': 100}, 'fill': {'color': 'zone', 'glow': GLOW},
		             'zones': [{'to': 20, 'color': '$bad', 'opacity': 0}, {'from': 20, 'to': 50, 'color': '$warn', 'opacity': 0},
		                       {'from': 50, 'color': '$good', 'opacity': 0}],
		             'value-label': {'position': 'end', 'size': '80%', 'format': {'precision': 0}}}},
	], size='21%')


W = 'environment.wind'
wind = panel('wind', 'WIND MPH', [
	{'preset': 'compass', 'geometry': g(0, 0, 54, 54),
	 'props': {'label': 'mph', 'caption_size': '34%', 'label_size': '13%', 'arc_weight': '2.5%'},
	 'display': {'arc': {'color': '$rule', 'glow': GLOW}, 'needle': {'color': '$wind', 'glow': GLOW},
	             'major': {'labels': {'height': '14%', 'color': '$muted'}}}},
	*tiles([
		('GUST', f'{W}.speed.gust', {'color': '$wind', 'spark': {'color': '$wind', 'lo': 0}}),
		('PEAK', f'max({W}.speed.gust, today)', {'color': '$warn'}),
	], 58, 0, 42, 54, 1),
	{'preset': 'table', 'geometry': g(0, 57, 100, 43),
	 'props': {
		 'labelWidth': '36%', 'alignment': 'Right', 'font': '$body', 'labelFont': '$display', 'titleGroup': 'global.aloft-head',
		 'valueGroup': 'global.aloft-cell',
		 'columns': [{'head': 'MPH', 'key': f'{W}.speed.{{row}}', 'precision': 0, 'hint': '00', 'color': '$wind'},
		             {'head': 'FROM', 'key': f'{W}.direction.{{row}}', 'hint': 'SSW', 'color': '$info'}],
		 'rows': [{'label': '180 M', 'row': '180m'}, {'label': '120 M', 'row': '120m'}, {'label': '80 M', 'row': '80m'}],
	 }},
], size='20%')

IR = 'environment.light.irradiance'
uv = panel('uv', 'UV  ·  SUN', [
	mini(U, g(0, 10, 100, 40), gradient='UVIndexGradient', lo=0, hi=12, opacity=0.9, fill=0.3, figure='uv', top='10%'),
	*tiles([
		('UV NOW', U, {'color': {'scale': 'UVIndexGradient', 'of': U}, 'weight': 'Bold'}),
		('PEAK', f'max({U}, today)', {'color': '$warn'}),
	], 0, 0, 100, 50, 2),
	{'preset': 'table', 'geometry': g(0, 54, 100, 46),
	 'props': {
		 'labelWidth': '46%', 'alignment': 'Right', 'font': '$body', 'labelFont': '$display', 'titleGroup': 'global.sun-head',
		 'valueGroup': 'global.sun-cell',
		 'columns': [{'head': 'W/M²', 'key': f'{IR}.{{row}}', 'precision': 0, 'hint': '000', 'color': '$warn'}],
		 'rows': [{'label': 'ALL', 'row': 'irradiance'}, {'label': 'DIRECT', 'row': 'direct'}, {'label': 'DIFFUSE', 'row': 'diffuse'}],
	 }},
], size='15%')

SOIL = [('SURFACE', 'environment.soil.temperature.temperature', 'environment.soil.moisture.1-3cm'),
        ('6 CM', 'environment.soil.temperature.6cm', 'environment.soil.moisture.3-9cm'),
        ('18 CM', 'environment.soil.temperature.18cm', 'environment.soil.moisture.9-27cm'),
        ('54 CM', 'environment.soil.temperature.54cm', 'environment.soil.moisture.27-81cm')]
soil_items = [{**cap('°F', g(34, 0, 30, 10)), 'alignment': 'BottomRight'}, {**cap('WET %', g(70, 0, 30, 10)), 'alignment': 'BottomRight'}]
for i, (depth, tk, mk) in enumerate(SOIL):
	y = 12 + i * 22
	soil_items += [
		{'type': 'text', 'text': depth, 'font': '$display', 'weight': 'Medium', 'color': '$muted', 'alignment': 'CenterLeft',
		 'text-height': '5mm', 'geometry': g(0, y, 34, 20)},
		val(tk, g(34, y, 30, 20), '$soil', hint='00', align='CenterRight', unit='Hidden', height='10mm', fmt={'unit_symbol': False}),
		val(mk, g(70, y, 30, 20), '$info', hint='00', align='CenterRight', unit='Hidden', height='10mm', fmt={'unit_symbol': False}),
	]
# Wetness as a thin bar under each row, on a fixed 0 to 50 % span.
for i, (depth, tk, mk) in enumerate(SOIL):
	soil_items.append({'type': 'realtime.bar', 'key': mk, 'title': False, 'geometry': g(34, 12 + i * 22 + 19, 66, 2.5),
	                   'display': {'range': {'min': 0, 'max': 50}, 'track': {'weight': '100%', 'color': '$rule'},
	                               'fill': {'color': '$info', 'glow': GLOW}, 'value-label': {'visible': False}}})
soil = panel('soil', 'SOIL', soil_items)

ground = {'type': 'stack', 'name': 'ground', 'direction': 'Horizontal', 'size': '38%', 'spacing': '4mm',
          'dividers': {'enabled': True, 'opacity': '60%', 'size': '88%'},
          'items': [room('bedroom', 'BEDROOM', 'bedroom', '$info', 60, 85),
                    room('terrarium', 'TERRARIUM', 'terrarium', '$good', 65, 90), wind, uv, soil]}

doc = {
	'theme': theme,
	'items': [{'type': 'stack', 'defaultType': 'group', 'name': 'main', 'padding': '3mm', 'spacing': '3mm',
	           'dividers': {'enabled': True, 'opacity': '70%', 'size': '99%'},
	           'items': [sky, surface, ground]}],
}

def scope_groups(node, panel=None):
	if isinstance(node, dict):
		if node.get('type') in ('titled-group', 'group', 'switch') and node.get('name'):
			panel = node['name']
		mg = node.get('matchingGroup')
		if isinstance(mg, dict) and mg.get('group') == 'global.tile' and panel:
			mg['group'] = f'global.tile-{panel}'
		for v in node.values():
			scope_groups(v, panel)
	elif isinstance(node, list):
		for v in node:
			scope_groups(v, panel)


scope_groups(doc)

HEADER = """\
# Cross-section, neon: sky, surface, ground. The room display on lambda (1680x1050 logical).
# Generated by docs/tasks/lambda-cross-section-gen.py. Tiles: a small caption over a number that fills its cell; tables where a column of numbers
# must line up. Only keys lambda publishes (OpenMeteo, Astronomy, the bedroom and terrarium Govee sensors).
"""
sys.stdout.write(HEADER + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=140))
