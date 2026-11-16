"""Grow: the greenhouse showcase. Ink on paper, set like a page of an almanac in two serif faces."""
import math

from kit import *

FREEZE = '2026-05-14T14:15:00'
G = 'garden'
SHELVES = [('Nepenthes', 'nepenthes', 76.2, 84, 71), ('Sundews', 'sundews', 74.8, 78, 88), ('Orchids', 'orchids', 77.9, 66, 42),
           ('Seedlings', 'seedlings', 79.4, 72, 58), ('Mushroom tent', 'mushrooms', 68.3, 93, 64)]


def data():
	d = Data('grow', 'A greenhouse on a bright May afternoon: vents open, light near its peak, one shelf running dry.', 14.25)
	light = d.series(lambda h, day, t: 780 * sun(h, 6.2, 20.2) ** 1.3 * (1 - 0.35 * bell(h, 11, 1.1)), noise=12, smooth=1, lo=0, digits=0)
	temp = d.series(lambda h, day, t: 71 + 7.5 * daily(h, 14.5), noise=0.2, smooth=1)
	hum = d.series(lambda h, day, t: 70 - 9 * daily(h, 14.5), noise=0.6, smooth=1, digits=0)
	vpd = [round(0.6108 * math.exp(17.27 * ((a - 32) / 1.8) / ((a - 32) / 1.8 + 237.3)) * (1 - b / 100), 2) for a, b in zip(temp, hum)]
	d.add(f'{G}.air.temperature', 'f', temp, title='Air')
	d.add(f'{G}.air.humidity', 'int', hum, digits=0, title='Humidity')
	d.add(f'{G}.air.vpd', 'int', vpd, digits=2, title='VPD')
	d.add(f'{G}.air.high', 'f', value=round(max(temp[24:48])), title='High')
	d.add(f'{G}.air.low', 'f', value=round(min(temp[24:48])), title='Low')
	d.add(f'{G}.air.co2', 'int', d.series(lambda h, day, t: 520 - 110 * sun(h, 6.2, 20.2), noise=6, smooth=1, digits=0), digits=0, title='CO2')
	d.add(f'{G}.air.leaf', 'f', [round(a - 2.4, 1) for a in temp], title='Leaf')
	d.add(f'{G}.air.dewpoint', 'f', [round(a - (100 - b) / 2.6, 1) for a, b in zip(temp, hum)], title='Dew point')
	d.add(f'{G}.air.fan', 'int', value=40, title='Fan')
	d.add(f'{G}.light.ppfd', 'int', light, digits=0, title='PPFD')
	i0 = d.index_now()
	d.add(f'{G}.light.dli', 'int', value=round(sum(light[24:i0 + 1]) * 3600 / 1e6, 1), title='DLI so far')
	d.add(f'{G}.light.target', 'int', value=24, title='DLI target')
	d.add(f'{G}.light.photoperiod', 'int', value=14, title='Photoperiod')
	for label, name, t0, h0, soil in SHELVES:
		d.add(f'{G}.shelf.temperature#{name}', 'f', value=t0, title=f'{label} temperature')
		d.add(f'{G}.shelf.humidity#{name}', 'int', value=h0, title=f'{label} humidity')
		d.add(f'{G}.shelf.moisture#{name}', 'int', value=soil, title=f'{label} moisture')
	d.add(f'{G}.water.level', 'int', value=38, title='Reservoir')
	d.add(f'{G}.water.ph', 'int', value=5.8, title='pH')
	d.add(f'{G}.water.ec', 'int', value=1.4, title='EC')
	d.add(f'{G}.water.temperature', 'f', value=66.2, title='Water')
	d.add(f'{G}.water.next', 'int', value=3, title='Hours to next watering')
	return d


THEME = {
	'extends': 'default', 'mode': 'light',
	'colors': {
		'background': '#f2ead8', 'surface': '#e9dfc8',
		'text': '#1c2618', 'muted': '#4f5c47', 'faint': '#6f7a64', 'rule': '#cdbf9f',
		'accent': '#2c6a36', 'good': '#2c6a36', 'warn': '#b96c0c', 'bad': '#b0341c', 'info': '#1f6a8c', 'violet': '#6f4585',
		'series-1': '#2c6a36', 'series-2': '#b96c0c', 'series-3': '#1f6a8c', 'series-4': '#b0341c', 'series-5': '#6f4585', 'series-6': '#1c2618',
	},
	'fonts': {'display': 'Fraunces', 'body': 'Instrument Serif', 'mono': 'Fraunces'},
}
CAP = 1.45


def head(numeral, s, x, y, w):
	"""A section heading: a roman numeral in italics, the title in tracked capitals, and a hairline."""
	return [
		text(numeral, g(x, y, 2.4, 2.2), font='$body', weight='Regular', italic=True, color='$accent', align='BottomLeft', group='global.numeral'),
		cap(s, g(x + 2.6, y + 0.5, w - 2.6, CAP), '$text', tracking=0.24, font='$display', group='global.head'),
		rule(x, y + 2.7, w, 0.1),
	]


def rule(x, y, w, h, color='$text'):
	return {'type': 'group', 'geometry': g(x, y, w, h), 'border': {'enabled': True, 'radius': 0, 'fill': color, 'weight': 0}}


def small(s, geom, color='$muted', **kw):
	return cap(s, geom, color, tracking=0.18, font='$display', **kw)


def aside(s, geom, color='$muted', align='CenterLeft', group='global.aside', **kw):
	return text(s, geom, font='$body', weight='Regular', italic=True, color=color, align=align, group=group, **kw)


def num(key, geom, color='$text', weight='SemiBold', group='global.num', font='$display', **kw):
	return val(key, geom, color, font=font, weight=weight, group=group, **kw)


def figure(caption, key, x, y, w, color='$text', h=5.4, **kw):
	return [small(caption, g(x, y, w, CAP)), num(key, g(x, y + CAP + 0.4, w, h), color, **kw)]


def dial(key, geom, lo, hi, zones, step, color='$text'):
	return {'type': 'realtime.gauge', 'key': key, 'title': False, 'geometry': geom, 'display': {
		'radius': '92%', 'range': {'min': lo, 'max': hi}, 'font': '$display',
		'arc': {'start-angle': -110, 'end-angle': 110, 'weight': '1.2%', 'color': '$text', 'cap': 'flat'},
		'zones': [{**z, 'weight': '6%'} for z in zones],
		'major': {'interval': step, 'length': '9%', 'width': '2px', 'color': '$text', 'labels': {'position': 'inside', 'height': '17%', 'offset': '6%'}},
		'minor': {'enabled': False}, 'micro': {'enabled': False},
		'needle': {'type': 'tapered', 'length': '70%', 'width': '5%', 'tail': '14%', 'hub': '9%', 'hub-color': '$text', 'color': color},
		'value-label': {'visible': False}, 'unit-label': {'visible': False}}}


def board():
	B = []
	# ------------------------------------------------------------ masthead
	B += [
		text('Greenhouse', g(2, 1, 44, 12.4), font='$display', weight='Black', color='$text', align='BottomLeft', tracking=-0.035, **{'format-hint': 'Greenhouse'}),
		aside('a daily almanac of the glass room', g(2.3, 13.4, 40, 2.4), group=None),
		{'type': 'clock', 'name': 'clock', 'geometry': g(54, 1, 44, 15), 'items': [
			{'format': '%A', 'filters': ['Upper'], 'tracking': 0.34, 'font': '$display', 'weight': 'SemiBold', 'color': '$accent', 'alignment': 'BottomRight',
			 'margins': 0, 'format-hint': 'WEDNESDAY', 'geometry': g(40, 6, 60, 10)},
			{'format': '%-d %B', 'font': '$display', 'weight': 'Light', 'italic': True, 'color': '$text', 'alignment': 'BottomRight', 'margins': 0,
			 'tracking': -0.02, 'format-hint': '14 May', 'geometry': g(20, 16, 80, 52)},
			{'format': '%-I:%M %p', 'filters': ['Lower'], 'font': '$body', 'weight': 'Regular', 'italic': True, 'color': '$muted', 'alignment': 'CenterRight',
			 'margins': 0, 'format-hint': '10:00 pm', 'geometry': g(50, 84, 50, 16)},
		]},
		rule(2, 17, 96, 0.28), rule(2, 17.6, 96, 0.08),
	]
	# ------------------------------------------------------------ I. the air
	V = f'{G}.air.vpd'
	x, w, y = 2, 31, 19.6
	edge = lambda v: x + (v - 0.2) / 1.8 * w
	B += [
		*head('i.', 'THE AIR', x, y, w),
		num(V, g(x - 0.4, y + 3.6, 23, 19.4), '$accent', weight='Black', precision=2, hint='0.00', tracking=-0.04, group=None),
		aside('kPa', g(x + 23.4, y + 15.4, 7, 5), '$accent', group=None, align='BottomLeft'),
		aside('vapour pressure deficit, the pull of the air on a leaf', g(x, y + 23.4, w, 2.4)),
		bar(V, g(x, y + 27, w, 3.4), 0.2, 2.0, color='$text', track={'weight': '26%', 'color': '$rule', 'cap': 'flat'},
		    zones=[{'from': 0.4, 'to': 0.8, 'color': '$info', 'weight': '26%'}, {'from': 0.8, 'to': 1.2, 'color': '$good', 'weight': '26%'},
		           {'from': 1.2, 'to': 1.6, 'color': '$warn', 'weight': '26%'}, {'from': 1.6, 'to': 2.0, 'color': '$bad', 'weight': '26%'}],
		    fill={'opacity': 0}, pointer={'type': 'triangle', 'color': '$text', 'side': 'before', 'size': '46%'}),
		*[aside(s, g(edge(a), y + 30.2, edge(b) - edge(a), 2.2), c, align='Center', group='global.zone')
		  for s, a, b, c in [('cuttings', 0.4, 0.8, '$info'), ('leaf', 0.8, 1.2, '$good'), ('flower', 1.2, 1.6, '$warn'), ('stress', 1.6, 2.0, '$bad')]],
	]
	y2 = y + 35
	B += [
		small('AIR, FAHRENHEIT', g(x, y2, 14, CAP)),
		mini(f'{G}.air.temperature', g(x, y2 + 2, 14, 11), color='$warn', hours=24, past=True, top='45%', opacity=0.55, fill=0.35, weight=0.4),
		num(f'{G}.air.temperature', g(x, y2 + 2, 14, 11), '$text', weight='Black', precision=1, hint='00.0', tracking=-0.03, group='global.big'),
		small('HUMIDITY %', g(x + 16.5, y2, 14, CAP)),
		mini(f'{G}.air.humidity', g(x + 16.5, y2 + 2, 14, 11), color='$info', hours=24, past=True, top='45%', opacity=0.55, fill=0.35, weight=0.4),
		num(f'{G}.air.humidity', g(x + 16.5, y2 + 2, 14, 11), '$text', weight='Black', hint='00.0', tracking=-0.03, group='global.big'),
		small('HIGH', g(x, y2 + 15, 6, CAP)),
		num(f'{G}.air.high', g(x, y2 + 17, 6.4, 6), '$bad', weight='Regular', font='$body', hint='00', outline=2, tracking=0.03, group='global.hollow', fmt={'unit_symbol': False}),
		small('LOW', g(x + 7.6, y2 + 15, 6, CAP)),
		num(f'{G}.air.low', g(x + 7.6, y2 + 17, 6.4, 6), '$info', weight='Regular', font='$body', hint='00', outline=2, tracking=0.03, group='global.hollow', fmt={'unit_symbol': False}),
		*figure('CO₂ PPM', f'{G}.air.co2', x + 16.5, y2 + 15, 7, hint='000'),
		*figure('LEAF', f'{G}.air.leaf', x + 24.4, y2 + 15, 6.6, '$accent', precision=1, hint='00.0', fmt={'unit_symbol': False}),
	]
	B += [
		small('THE PULL, THE LAST DAY', g(x, y2 + 26, w, CAP)),
		{'type': 'graph', 'name': 'pull', 'geometry': g(x, y2 + 28, w, 15.4),
		 'timeframe': {'hours': 24, 'offset': {'hours': -21}},
		 'annotations': {'dayLabels': {'enabled': False}, 'hourLabels': {'alignment': 'BottomCenter', 'spacingIntervals': '6', 'height': '10%'},
		                 'lines': {'weight': 0.3}},
		 'figures': [{'figure': 'vpd', 'margins': {'top': '10%', 'bottom': '18%'}, 'min': 0.2, 'max': 1.6,
		              V: {'labels': {'enabled': True}, 'plot': {'type': 'plot', 'color': '$accent', 'weight': 0.6, 'fill': {'opacity': 0.4, 'fade': True}}}}]},
	]
	# ------------------------------------------------------------ II. the light
	x, w = 36, 32
	L = f'{G}.light'
	B += [
		*head('ii.', 'THE LIGHT', x, y, w),
		{'type': 'graph', 'name': 'light', 'geometry': g(x, y + 3.6, w, 22.4),
		 'timeframe': {'hours': 24, 'offset': {'hours': -14.25}},
		 'annotations': {'dayLabels': {'enabled': False}, 'hourLabels': {'alignment': 'BottomCenter', 'spacingIntervals': '6', 'height': '7%'},
		                 'lines': {'weight': 0.3}},
		 'figures': [{'figure': 'ppfd', 'margins': {'top': '8%', 'bottom': '12%'}, 'min': 0, 'max': 900,
		              f'{L}.ppfd': {'plot': {'type': 'plot', 'color': '$warn', 'weight': 0.6, 'fill': {'opacity': 0.55, 'fade': True}}}}]},
		*figure('PPFD µMOL', f'{L}.ppfd', x, y + 27.6, 9, '$warn', hint='000'),
		*figure('LIGHT SUM', f'{L}.dli', x + 10, y + 27.6, 8, precision=1, hint='00.0'),
		aside('mol today', g(x + 10, y + 34.6, 9, 2.2)),
		*figure('OF', f'{L}.target', x + 19, y + 27.6, 5, '$faint', hint='00'),
		*figure('DAY H', f'{L}.photoperiod', x + 25.4, y + 27.6, 6, hint='00'),
		bar(f'{L}.dli', g(x, y + 37.6, w, 1.2), 0, 24, color='$warn', track={'weight': '100%', 'color': '$rule', 'cap': 'flat'}, fill={'cap': 'flat'}),
	]
	# ------------------------------------------------------------ III. the shelves
	ys = y + 41.6
	cols = [(13.4, 5.4, 'TEMP'), (19.4, 5, 'RH %'), (25, 7, 'SOIL %')]
	B += [*head('iii.', 'THE SHELVES', x, ys, w)]
	B += [{**small(s, g(x + cx, ys + 3.6, cw, CAP)), 'alignment': 'BottomRight'} for cx, cw, s in cols]
	for i, (label, name, t0, h0, soil) in enumerate(SHELVES):
		yr = ys + 6 + i * 6.1
		dry = soil < 45
		B += [
			aside(label, g(x, yr, 13.4, 3.6), '$bad' if dry else '$text', group='global.shelf'),
			num(f'{G}.shelf.temperature#{name}', g(x + 13.4, yr, 5.4, 3.6), '$text', precision=0, hint='00', align='CenterRight', group='global.row', fmt={'unit_symbol': False}),
			num(f'{G}.shelf.humidity#{name}', g(x + 19.4, yr, 5, 3.6), '$info', hint='00', align='CenterRight', group='global.row'),
			num(f'{G}.shelf.moisture#{name}', g(x + 25, yr, 7, 3.6), '$bad' if dry else '$accent', hint='00', align='CenterRight', weight='Black', group='global.row'),
			bar(f'{G}.shelf.moisture#{name}', g(x, yr + 4, w, 0.7), 0, 100, color='$bad' if dry else '$accent',
			    track={'weight': '100%', 'color': '$rule', 'cap': 'flat'}, fill={'cap': 'flat'},
			    markers=[{'value': 45, 'type': 'line', 'color': '$text', 'size': '260%'}]),
		]
	# ------------------------------------------------------------ IV. the water
	x, w = 72, 26
	Wt = f'{G}.water'
	B += [
		*head('iv.', 'THE WATER', x, y, w),
		bar(f'{Wt}.level', g(x, y + 4.2, 4.4, 30), 0, 60, color='$info', orientation='vertical',
		    track={'weight': '100%', 'color': '$rule', 'cap': 'flat'}, fill={'segments': 12, 'gap': '14%', 'cap': 'flat'}),
		small('RESERVOIR L', g(x + 6.4, y + 4.2, 12, CAP)),
		num(f'{Wt}.level', g(x + 6.2, y + 6.2, 13, 11), '$info', weight='Black', hint='00', tracking=-0.03, group='global.big'),
		aside('of sixty, about four days', g(x + 6.4, y + 17.6, 19, 2.4)),
		dial(f'{Wt}.ph', g(x + 5.6, y + 21, 10, 13.4), 4, 8, [{'from': 5.5, 'to': 6.5, 'color': '$good'}], 1),
		dial(f'{Wt}.ec', g(x + 16, y + 21, 10, 13.4), 0, 3, [{'from': 1.0, 'to': 1.8, 'color': '$good'}], 1),
		small('PH', g(x + 6.4, y + 35.2, 4, CAP)),
		num(f'{Wt}.ph', g(x + 9, y + 34.2, 6, 3.6), precision=1, hint='0.0', align='CenterRight', group='global.row'),
		small('EC', g(x + 16.8, y + 35.2, 4, CAP)),
		num(f'{Wt}.ec', g(x + 19.4, y + 34.2, 6, 3.6), precision=1, hint='0.0', align='CenterRight', group='global.row'),
	]
	# ------------------------------------------------------------ V. the notebook
	B += [
		*head('v.', 'THE NOTEBOOK', x, ys, w),
		small('NEXT WATERING IN', g(x, ys + 3.8, 16, CAP)),
		num(f'{Wt}.next', g(x, ys + 5.6, 7, 10), '$accent', weight='Regular', font='$body', hint='0', outline=2.5, group=None),
		aside('hours,', g(x + 7.4, ys + 8.4, 18, 3), '$text', group='global.note'),
		aside('the orchids first', g(x + 7.4, ys + 11.6, 18, 3), '$bad', group='global.note'),
		rule(x, ys + 17.2, w, 0.08, '$rule'),
		aside('A new pitcher on the ventrata.', g(x, ys + 18.6, w, 3), '$text', group='global.note'),
		aside('Sundews in flower; pinch the stalks.', g(x, ys + 22.6, w, 3), '$text', group='global.note'),
		aside('Mist the tent at dusk.', g(x, ys + 26.6, w, 3), '$text', group='global.note'),
		aside('Tuesday', g(x, ys + 31, w, 2.2), '$faint', align='CenterRight', group='global.aside'),
	]
	return {'theme': THEME, 'items': [{'type': 'group', 'name': 'board', 'items': B}]}


HEADER = """
Grow: the greenhouse showcase. A bright May afternoon with one shelf running dry.

Set like a page of an almanac: a light paper theme, no cards, hairline rules and five numbered sections. Numerals in
Fraunces (Black for the readings, hollow for the high and low), asides and names in Instrument Serif italic, section
titles in tracked capitals.

Invented data: everything under garden.* (air, light, shelf, water): a grow-controller plugin that does not exist yet.
Fonts: Fraunces and Instrument Serif (both OFL).
"""

if __name__ == '__main__':
	write('grow', HEADER, board(), data(), FREEZE)
