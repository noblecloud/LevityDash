"""Tide: the coast showcase. A wide rounded face on deep water: Black for the sea level, Light for the hour."""
import math
import time
from datetime import datetime

from kit import *

GLOW = {'strength': 1.2, 'reach': 2.0, 'passes': 6}
FREEZE = '2026-09-18T16:20:00'
M = 'marine'
HIGH, PERIOD = 19.7, 12.42


def tide(t):
	return 3.1 + 2.6 * math.cos(2 * math.pi * (t - HIGH) / PERIOD) + 0.5 * math.cos(2 * math.pi * (t - HIGH) / (2 * PERIOD))


def epoch(hours):
	"""A clock time today (hours from midnight) as the scenario stores it."""
	base = datetime.fromisoformat('2026-09-18T00:00:00')
	return int(time.mktime(base.timetuple())) + int(hours * 3600) + 4 * 3600


def data():
	d = Data('tide', 'A September afternoon on the coast: the tide coming in to a 6.2 ft high at dusk, an onshore breeze, a long swell.', 16 + 20 / 60)
	level = d.series(lambda h, day, t: tide(t), digits=2)
	d.add(f'{M}.tide.height', 'int', level, digits=1, title='Tide')
	d.add(f'{M}.tide.nextHigh', 'epoch', value=epoch(HIGH), type='datetime', title='Next high')
	d.add(f'{M}.tide.nextLow', 'epoch', value=epoch(HIGH + PERIOD / 2), type='datetime', title='Next low')
	d.add(f'{M}.tide.highHeight', 'int', value=round(tide(HIGH), 1), title='High')
	d.add(f'{M}.tide.lowHeight', 'int', value=round(tide(HIGH + PERIOD / 2), 1), title='Low')
	wind = d.series(lambda h, day, t: 6 + 9 * bell(h, 16, 3.5), noise=0.7, smooth=1, lo=1)
	d.add(f'{M}.wind.speed', 'int', wind, digits=0, title='Wind')
	d.add(f'{M}.wind.gust', 'int', [round(w * 1.45 + 1) for w in wind], digits=0, title='Gust')
	d.add(f'{M}.wind.direction', 'º', d.series(lambda h, day, t: 285 + 22 * math.sin(t / 7) - 40 * bell(h, 5, 3), noise=5, smooth=1, digits=0),
	      type='direction', digits=0, title='Wind direction')
	swell = d.series(lambda h, day, t: 4.6 + 1.6 * bell(t, 30, 14) + 0.3 * math.sin(t / 5), noise=0.08, smooth=1)
	d.add(f'{M}.swell.height', 'int', swell, title='Swell')
	d.add(f'{M}.swell.period', 'int', value=13, title='Period')
	d.add(f'{M}.swell.direction', 'º', value=292, type='direction', title='Swell direction')
	d.add(f'{M}.water.temperature', 'f', d.series(lambda h, day, t: 57 + 0.6 * daily(h, 16), smooth=1), title='Water')
	d.add('environment.temperature.temperature', 'f', d.series(lambda h, day, t: 60 + 5 * daily(h, 15), noise=0.2, smooth=1))
	d.add('environment.visibility', 'mi', value=8)
	d.add('astronomy.sun.set', 'epoch', value=epoch(19 + 11 / 60), type='datetime')
	return d


THEME = {
	'extends': 'default',
	'colors': {
		'background': '#020a18', 'surface': '#061a2b',
		'text': '#eefaff', 'muted': '#9cc3d6', 'faint': '#6590a6', 'rule': '#143a52',
		'accent': '#35f0d0', 'good': '#35f0d0', 'warn': '#ffc24a', 'bad': '#ff6b5e', 'info': '#4db8ff', 'violet': '#9d8cff',
		'series-1': '#35f0d0', 'series-2': '#4db8ff', 'series-3': '#ffc24a', 'series-4': '#9d8cff', 'series-5': '#ff6b5e', 'series-6': '#eefaff',
	},
	'fonts': {'display': 'Unbounded', 'body': 'Space Grotesk', 'mono': 'Space Grotesk'},
	'scales': {'sky': {0: '#010611', 1: '#06323d'}},
}
CAP = 1.5


def lab(s, geom, color='$muted', **kw):
	return cap(s, geom, color, tracking=0.2, font='$body', **kw)


def wide(key, geom, color='$text', weight='Black', group=None, **kw):
	return val(key, geom, color, font='$display', weight=weight, group=group, **kw)


def rule(x, y, w, h, color='$rule'):
	return {'type': 'group', 'geometry': g(x, y, w, h), 'border': {'enabled': True, 'radius': 0, 'fill': color, 'weight': 0}}


def tile(caption, key, x, y, w, color='$text', h=5.4, **kw):
	return [lab(caption, g(x, y, w, CAP)), wide(key, g(x, y + CAP + 0.6, w, h), color, weight='Medium', group='global.tile', **kw)]


def board():
	H = f'{M}.tide.height'
	B = [
		lab('HALF MOON BAY   ·   SEA LEVEL ABOVE THE CHART', g(2, 3, 44, CAP), '$accent'),
		wide(H, g(1.6, 6, 31, 25), '$text', precision=1, hint='0.0', tracking=-0.05),
		text('ft', g(26, 21.4, 8, 8), font='$display', weight='Light', color='$muted', align='BottomLeft'),
		{'type': 'switch', 'name': 'tendency', 'hold': '10m', 'geometry': g(2, 31.6, 24, 2.6), 'items': [
			{**text('RISING  ↑', g(0, 0, 100, 100), font='$body', weight='Bold', color='$accent', tracking=0.3), 'when': f'{H} - at({H}, -1h) > 0'},
			text('FALLING  ↓', g(0, 0, 100, 100), font='$body', weight='Bold', color='$warn', tracking=0.3)]},
		# the next two turns of the tide
		lab('HIGH WATER', g(46, 6.6, 14, CAP), '$accent'),
		wide(f'{M}.tide.nextHigh', g(46, 9, 17, 8.4), '$accent', fmt='%-I:%M', hint='0:00', outline=2.5, group='global.turn'),
		wide(f'{M}.tide.highHeight', g(63.6, 11.4, 6, 5), '$text', weight='Light', precision=1, hint='0.0', group='global.turnft'),
		lab('LOW WATER', g(46, 20.6, 14, CAP), '$info'),
		wide(f'{M}.tide.nextLow', g(46, 23, 17, 8.4), '$info', fmt='%-I:%M', hint='0:00', outline=2.5, group='global.turn'),
		wide(f'{M}.tide.lowHeight', g(63.6, 25.4, 6, 5), '$text', weight='Light', precision=1, hint='0.0', group='global.turnft'),
		{'type': 'clock', 'name': 'clock', 'geometry': g(72, 3, 26, 16), 'items': [
			{'format': '%A %-d %B', 'filters': ['Upper'], 'tracking': 0.2, 'font': '$body', 'weight': 'Medium', 'color': '$muted', 'alignment': 'BottomRight',
			 'margins': 0, 'format-hint': 'WEDNESDAY 30 SEPTEMBER', 'geometry': g(0, 0, 100, 9.4)},
			{'format': '%-I:%M', 'font': '$display', 'weight': 'Light', 'color': '$text', 'alignment': 'BottomRight', 'margins': 0, 'tracking': -0.03,
			 'format-hint': '10:00', 'geometry': g(0, 18, 100, 82)}]},
		{'type': 'moon', 'glowStrength': 0, 'geometry': g(92, 21.6, 6, 9.6)},
		*tile('SUNSET', 'astronomy.sun.set', 74, 21.6, 9, '$warn', fmt='%-I:%M', hint='0:00', h=6),
		rule(2, 36.4, 96, 0.1),
	]
	# ------------------------------------------------------------ two days of water
	B.append({
		'type': 'graph', 'name': 'water', 'geometry': g(2, 37.4, 96, 30.6),
		'timeframe': {'hours': 44, 'lookback': {'hours': 14}, 'offset': {'hours': -6}},
		'annotations': {'dayLabels': {'position': 'Center', 'alignment': 'Center', 'opacity': '10%', 'height': '46%'},
		                'hourLabels': {'alignment': 'BottomCenter', 'spacingIntervals': '3, 6', 'height': '4.6%'}, 'lines': {'weight': 0.3}},
		'figures': [{'figure': 'tide', 'margins': {'top': '22%', 'bottom': '12%'}, 'min': -0.5, 'max': 6.6,
		             H: {'labels': {'enabled': True}, 'plot': {'type': 'plot', 'color': '$accent', 'weight': 1.0, 'glow': GLOW,
		                                                        'fill': {'opacity': 0.5, 'fade': True}}}}]})
	B.append(rule(2, 69, 96, 0.1))
	# ------------------------------------------------------------ four columns
	Y = 71.4
	X = [2, 26.5, 51, 75.5]
	W = 22.5
	B += [rule(x - 1.3, Y, 0.06, 26) for x in X[1:]]
	hero = lambda key, x, color, **kw: wide(key, g(x - 0.2, Y + 2.6, 12, 11), color, group='global.hero', tracking=-0.04, **kw)
	x = X[0]
	B += [
		lab('WIND · KNOTS', g(x, Y, W, CAP), '$warn'),
		hero(f'{M}.wind.speed', x, '$warn', hint='00'),
		*tile('GUST', f'{M}.wind.gust', x + 13.4, Y + 4.6, 8, hint='00', h=6),
		{'type': 'polar', 'name': 'heading', 'plot': 'carousel', 'direction': f'{M}.wind.direction', 'view': 120, 'compass': 16, 'legend': False,
		 'geometry': g(x, Y + 15.4, W, 10.6)},
	]
	x = X[1]
	B += [
		lab('SWELL · FEET', g(x, Y, W, CAP), '$info'),
		mini(f'{M}.swell.height', g(x, Y + 2.6, W, 11), color='$info', hours=24, lo=3, hi=7.5, top='40%', opacity=0.6, fill=0.3, glow=GLOW),
		hero(f'{M}.swell.height', x, '$info', precision=1, hint='0.0'),
		*tile('EVERY, SEC', f'{M}.swell.period', x, Y + 16.4, 9, hint='00', h=6),
		*tile('FROM', f'{M}.swell.direction', x + 10.5, Y + 16.4, 11, '$info', hint='WNW', h=6),
	]
	x = X[2]
	Wt = f'{M}.water.temperature'
	B += [
		lab('WATER · °F', g(x, Y, W, CAP), '$accent'),
		hero(Wt, x, '$accent', hint='00', fmt={'unit_symbol': False}),
		bar(Wt, g(x, Y + 14.4, W, 0.9), 48, 70, color='$accent', track={'weight': '100%', 'color': '$rule'},
		    fill={'color': '$accent', 'glow': GLOW}, markers=[{'value': 'environment.temperature.temperature', 'type': 'triangle', 'color': '$text'}]),
		*tile('AIR', 'environment.temperature.temperature', x, Y + 16.4, 9, hint='00', h=6, fmt={'unit_symbol': False}),
		*tile('SEEN, MILES', 'environment.visibility', x + 10.5, Y + 16.4, 11, hint='00', h=6),
	]
	x = X[3]
	B += [
		lab('WIND, THE LAST DAY', g(x, Y, W, CAP)),
		{'type': 'polar', 'name': 'rose', 'plot': 'rose', 'direction': f'{M}.wind.direction', 'speed': f'{M}.wind.speed', 'window': '24h',
		 'legend': False, 'rings': 3, 'compass': 8,
		 'gradient': [{'at': 0, 'color': '#4db8ff'}, {'at': 8, 'color': '#35f0d0'}, {'at': 14, 'color': '#ffc24a'}],
		 'geometry': g(x + 2, Y + 2.4, W - 4, 23.8)},
	]
	return {'theme': THEME, 'background': {'gradient': '$sky', 'angle': 180}, 'items': [{'type': 'group', 'name': 'board', 'items': B}]}


HEADER = """
Tide: the coast showcase. A September afternoon with the tide coming in.

No cards: a gradient ground, hairline rules and one wide rounded face (Unbounded) in Black for the sea level, Light
for the clock and hollow for the turns of the tide, with Space Grotesk for labels. Two days of water across the
middle with the day names behind it; a compass strip, a swell sparkline and a wind rose below.

Invented data: everything under marine.* (tide, wind, swell, water): a tide-table and buoy plugin that do not exist yet.
Fonts: Unbounded and Space Grotesk (both OFL).
"""

if __name__ == '__main__':
	write('tide', HEADER, board(), data(), FREEZE)
