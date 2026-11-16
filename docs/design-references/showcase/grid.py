"""Grid: the home-energy showcase. One condensed face at its two extremes: Black numerals, Thin units."""
import math

from kit import *

GLOW = {'strength': 1.3, 'reach': 2.0, 'passes': 6}
FREEZE = '2026-07-09T13:30:00'
E = 'energy'


def data():
	d = Data('grid', 'A clear July lunchtime: the array near its peak, the battery filling, the surplus going to the car and the street.', 13.5)
	solar = d.series(lambda h, day, t: 7.9 * sun(h, 5.6, 20.6) ** 1.5 * (1 - 0.3 * bell(h, 10.2, 0.6)), noise=0.06, smooth=1, lo=0, digits=2)
	load = d.series(lambda h, day, t: 0.55 + 1.5 * bell(h, 7.3, 1.0) + 1.2 * bell(h, 12.8, 1.2) + 2.6 * bell(h, 18.8, 1.5), noise=0.12, smooth=1, lo=0.3, digits=2)
	battery = d.series(lambda h, day, t: 22 + 76 / (1 + math.exp(-(h - 11.2) / 1.5)) - 62 * bell(h, 23.5, 3.5) - 40 * bell(h, 0, 3), lo=18, hi=100, digits=0)
	export = [round(max(-3, a - b - (1.5 if 9 < (i - 24) % 24 < 15 else 0)), 2) for i, (a, b) in enumerate(zip(solar, load))]
	d.add(f'{E}.solar.power', 'int', solar, value=6.42, digits=2, title='Solar')
	d.add(f'{E}.solar.peak', 'int', value=7.86, title='Peak today')
	d.add(f'{E}.solar.capacity', 'int', value=9.6, title='Array')
	d.add(f'{E}.home.power', 'int', load, value=1.84, digits=2, title='Home')
	d.add(f'{E}.grid.power', 'int', export, value=3.07, digits=2, title='Grid')
	d.add(f'{E}.battery.charge', 'int', battery, value=86, digits=0, title='Battery')
	d.add(f'{E}.battery.power', 'int', value=1.51, title='Battery power')
	d.add(f'{E}.battery.full', 'int', value=52, title='Minutes to full')
	d.add(f'{E}.battery.reserve', 'int', value=20, title='Reserve')
	d.add(f'{E}.today.produced', 'int', value=38.2, title='Produced')
	d.add(f'{E}.today.used', 'int', value=21.4, title='Used')
	d.add(f'{E}.today.exported', 'int', value=14.1, title='Exported')
	d.add(f'{E}.today.self', 'int', value=97, title='Self-powered')
	d.add(f'{E}.today.earned', 'int', value=3.18, title='Earned')
	d.add(f'{E}.vehicle.charge', 'int', value=64, title='Car')
	d.add(f'{E}.vehicle.range', 'int', value=187, title='Range')
	d.add(f'{E}.vehicle.power', 'int', value=7.2, title='Charging')
	return d


THEME = {
	'extends': 'default',
	'colors': {
		'background': '#04060c', 'surface': '#0b101c',
		'text': '#f3f6ff', 'muted': '#9aa6c4', 'faint': '#66708c', 'rule': '#1c2540',
		'accent': '#ffd60a', 'good': '#3dff8f', 'warn': '#ff8a1f', 'bad': '#ff4a3d', 'info': '#2ee6ff', 'violet': '#a98bff',
		'series-1': '#ffd60a', 'series-2': '#2ee6ff', 'series-3': '#3dff8f', 'series-4': '#ff8a1f', 'series-5': '#a98bff', 'series-6': '#ff4a3d',
	},
	'fonts': {'display': 'Big Shoulders Display', 'body': 'Big Shoulders Display', 'mono': 'JetBrains Mono'},
}
CAP = 1.9


def lab(s, geom, color='$muted', **kw):
	return cap(s, geom, color, tracking=0.2, weight='Bold', **kw)


def big(key, geom, color, group=None, **kw):
	return val(key, geom, color, font='$display', weight='Black', group=group, tracking=0.01, **kw)


def unit(s, geom, color='$muted', **kw):
	"""The unit beside a number, in the thinnest cut of the same face."""
	return text(s, geom, font='$display', weight='Thin', color=color, align='BottomLeft', group='global.unit', **{'format-hint': 'KWH', **kw})


def tile(caption, key, x, y, w, color='$text', h=7, **kw):
	return [lab(caption, g(x, y, w, CAP)), big(key, g(x, y + CAP + 0.5, w, h), color, group='global.tile', **kw)]


def board():
	B = [
		text('GRID', g(2, 1.6, 12, 5), font='$display', weight='Black', color='$accent', align='CenterLeft', tracking=0.3, **{'format-hint': 'GRID'}),
		text('9.6 KWP ON THE ROOF   ·   13.5 KWH IN THE GARAGE   ·   ONE CAR', g(15, 2.9, 55, 2.4), font='$display', weight='Light', color='$muted',
		     align='CenterLeft', tracking=0.22),
		{'type': 'clock', 'name': 'clock', 'geometry': g(78, 1.6, 20, 5), 'items': [
			{'format': '%H:%M', 'font': '$display', 'weight': 'Thin', 'color': '$text', 'alignment': 'CenterRight', 'margins': 0, 'tracking': 0.06,
			 'format-hint': '00:00', 'geometry': g(0, 0, 100, 100)}]},
	]
	px, py = 1.3, 2
	Y1, H1, Y2, H2 = 8.4, 43.6, 53.6, 44.4
	cards, rects = {}, {}

	# ------------------------------------------------------------ solar
	R = rects['solar'] = (2, Y1, 40, H1)
	x, w = R[0] + px, R[2] - 2 * px
	cards['solar'] = [
		lab('SOLAR', g(x, Y1 + py, w, CAP), '$accent'),
		{'type': 'mini-graph', 'geometry': g(R[0], Y1 + 9, R[2], H1 - 9), 'timeframe': {'hours': 16, 'lookback': {'hours': 30}, 'offset': {'hours': -8.3}},
		 'annotations': {'dayLabels': {'enabled': False}, 'hourLabels': {'enabled': False}, 'lines': {'enabled': False}}, 'indicator': {'opacity': 0.5},
		 'figures': [{'figure': 'sun', 'margins': {'top': '38%', 'bottom': '0%'}, 'min': 0, 'max': 8.4,
		              f'{E}.solar.power': {'plot': {'type': 'plot', 'color': '$accent', 'weight': 0.7, 'opacity': 0.9, 'glow': GLOW,
		                                             'fill': {'opacity': 0.45, 'fade': True}}}}]},
		big(f'{E}.solar.power', g(x - 0.3, Y1 + 4.6, 30, 27), '$accent', precision=2, hint='0.00'),
		unit('KW', g(x + 30.4, Y1 + 21.6, 7, 9), '$accent', **{'format-hint': 'KW'}),
		*tile('PEAK TODAY', f'{E}.solar.peak', x, Y1 + 33.4, 9, precision=2, hint='0.00'),
		*tile('OF ARRAY %', f'{E}.solar.power * 100 / {E}.solar.capacity', x + 11, Y1 + 33.4, 9, '$muted', hint='00'),
	]
	# ------------------------------------------------------------ home, grid
	R = rects['home'] = (43.2, Y1, 27, 21.2)
	x, w = R[0] + px, R[2] - 2 * px
	cards['home'] = [
		lab('HOME', g(x, Y1 + py, w, CAP)),
		mini(f'{E}.home.power', g(R[0], Y1 + 6, R[2], 15.2), color='$text', hours=24, past=True, lo=0, top='40%', bottom='0%', opacity=0.4, fill=0.3),
		big(f'{E}.home.power', g(x, Y1 + 5, 16, 14), '$text', precision=2, hint='0.00', group='global.mid'),
		unit('KW', g(x + 16.4, Y1 + 12.4, 6, 6), **{'format-hint': 'KW'}),
	]
	Yg = Y1 + 22.4
	R = rects['street'] = (43.2, Yg, 27, 21.2)
	cards['street'] = [
		lab('TO THE STREET', g(x, Yg + py, w, CAP), '$info'),
		mini(f'{E}.grid.power', g(R[0], Yg + 6, R[2], 15.2), color='$info', hours=24, past=True, top='40%', bottom='0%', opacity=0.5, fill=0.3, glow=GLOW),
		big(f'{E}.grid.power', g(x, Yg + 5, 16, 14), '$info', precision=2, hint='0.00', group='global.mid'),
		unit('KW', g(x + 16.4, Yg + 12.4, 6, 6), '$info', **{'format-hint': 'KW'}),
	]
	# ------------------------------------------------------------ battery
	R = rects['battery'] = (71.4, Y1, 26.6, H1)
	x, w = R[0] + px, R[2] - 2 * px
	cards['battery'] = [
		lab('BATTERY', g(x, Y1 + py, w, CAP), '$good'),
		big(f'{E}.battery.charge', g(x, Y1 + 4.6, 15, 19), '$good', hint='00'),
		unit('%', g(x + 15.4, Y1 + 15.4, 5, 7.6), '$good', **{'format-hint': '%'}),
		bar(f'{E}.battery.charge', g(x, Y1 + 25, w, 6.4), 0, 100, color='$good', style='battery', track={'weight': '100%', 'color': '$muted'},
		    fill={'segments': 10, 'gap': '12%'}, markers=[{'value': f'{E}.battery.reserve', 'type': 'line', 'color': '$bad'}]),
		*tile('FILLING KW', f'{E}.battery.power', x, Y1 + 33.4, 8, precision=2, hint='0.00'),
		*tile('FULL MIN', f'{E}.battery.full', x + 9, Y1 + 33.4, 7.4, hint='00'),
		*tile('RESERVE', f'{E}.battery.reserve', x + 17.4, Y1 + 33.4, 6.6, '$bad', hint='00'),
	]
	# ------------------------------------------------------------ the day
	R = rects['day'] = (2, Y2, 54, H2)
	x, w = R[0] + px, R[2] - 2 * px
	cards['day'] = [
		lab('TODAY', g(x, Y2 + py, 10, CAP)),
		{**lab('SOLAR', g(x + 30, Y2 + py, 6, CAP), '$accent'), 'alignment': 'BottomRight'},
		{**lab('HOME', g(x + 37, Y2 + py, 6, CAP), '$text'), 'alignment': 'BottomRight'},
		{**lab('STREET', g(x + 44, Y2 + py, 7.4, CAP), '$info'), 'alignment': 'BottomRight'},
		{'type': 'graph', 'name': 'day', 'geometry': g(x, Y2 + 5.4, w, H2 - 7),
		 'timeframe': {'hours': 24, 'lookback': {'hours': 30}, 'offset': {'hours': -13.5}},
		 'annotations': {'dayLabels': {'enabled': False}, 'hourLabels': {'alignment': 'BottomCenter', 'spacingIntervals': '3', 'height': '5%'},
		                 'lines': {'weight': 0.3}},
		 'figures': [
			 {'figure': 'solar', 'margins': {'top': '6%', 'bottom': '10%'}, 'min': -3, 'max': 8.4,
			  f'{E}.solar.power': {'plot': {'type': 'plot', 'color': '$accent', 'weight': 0.9, 'glow': GLOW, 'fill': {'opacity': 0.4, 'fade': True}}}},
			 {'figure': 'street', 'margins': {'top': '6%', 'bottom': '10%'}, 'min': -3, 'max': 8.4,
			  f'{E}.grid.power': {'plot': {'type': 'plot', 'color': '$info', 'weight': 0.45, 'dashPattern': '4, 4'}}},
			 {'figure': 'home', 'margins': {'top': '6%', 'bottom': '10%'}, 'min': -3, 'max': 8.4,
			  f'{E}.home.power': {'plot': {'type': 'plot', 'color': '$text', 'weight': 0.5}}},
		 ]},
	]
	# ------------------------------------------------------------ totals
	R = rects['totals'] = (57.2, Y2, 20, H2)
	x, w = R[0] + px, R[2] - 2 * px
	T = cards['totals'] = [
		lab('SELF-POWERED', g(x, Y2 + py, w, CAP), '$accent'),
		ring(f'{E}.today.self', g(x + 2.2, Y2 + 5, w - 4.4, 17.6), 0, 100, color='$accent', weight='7%', glow=GLOW, start=-180, end=180),
		big(f'{E}.today.self', g(x + 5.4, Y2 + 9.4, w - 10.8, 8.8), '$text', hint='00', align='Center'),
	]
	for i, (name, key, color) in enumerate([('MADE', 'produced', '$accent'), ('USED', 'used', '$text'), ('SOLD', 'exported', '$info')]):
		y = Y2 + 24.4 + i * 4.6
		T += [lab(name, g(x, y + 1.4, 6, CAP)),
		      big(f'{E}.today.{key}', g(x + 6, y, 7.6, 4), color, precision=1, hint='00.0', align='BottomRight', group='global.row'),
		      unit('KWH', g(x + 14, y + 0.9, 3.6, 3.1), '$faint')]
	T += [lab('EARNED $', g(x, Y2 + 39.9, 7, CAP)),
	      big(f'{E}.today.earned', g(x + 6, Y2 + 38, 11.4, 5), '$accent', precision=2, hint='0.00', align='BottomRight', outline=2, group=None)]
	# ------------------------------------------------------------ the car
	R = rects['car'] = (78.4, Y2, 19.6, H2)
	x, w = R[0] + px, R[2] - 2 * px
	cards['car'] = [
		lab('THE CAR', g(x, Y2 + py, w, CAP), '$warn'),
		big(f'{E}.vehicle.charge', g(x, Y2 + 4.6, 11.4, 16), '$warn', hint='00'),
		unit('%', g(x + 11.8, Y2 + 13.4, 4, 6.4), '$warn', **{'format-hint': '%'}),
		bar(f'{E}.vehicle.charge', g(x, Y2 + 22.4, w, 2.6), 0, 100, color='$warn', track={'weight': '100%', 'color': '$rule', 'cap': 'flat'},
		    fill={'segments': 20, 'gap': '20%', 'cap': 'flat', 'glow': GLOW}, markers=[{'value': 80, 'type': 'line', 'color': '$text'}]),
		*tile('RANGE MI', f'{E}.vehicle.range', x, Y2 + 27.4, 8, hint='000'),
		*tile('ADDING KW', f'{E}.vehicle.power', x + 9, Y2 + 27.4, 7.6, '$warn', precision=1, hint='0.0'),
		lab('TO 80 % BY', g(x, Y2 + 38.4, 8, CAP)),
		text('15:40', g(x + 8.4, Y2 + 37, 8.4, 5), font='$display', weight='Black', color='$text', align='BottomRight', outline=2),
	]
	for name, items in cards.items():
		B.append(nest(f'{name}Card', rects[name], items))
	return {'theme': THEME, 'items': [{'type': 'group', 'name': 'board', 'items': B}]}


HEADER = """
Grid: the home-energy showcase. A clear July lunchtime with the array near its peak.

One typeface, Big Shoulders Display, at its two ends: Black for every number, Thin for the unit beside it, tracked
Bold capitals for labels. Yellow is the sun, white the house, cyan the street, green the battery, orange the car.

Invented data: everything under energy.* (solar, home, grid, battery, today, vehicle): an inverter, battery and
charger plugin that do not exist yet.
Fonts: Big Shoulders Display (OFL).
"""

if __name__ == '__main__':
	import math
	write('grid', HEADER, board(), data(), FREEZE)
