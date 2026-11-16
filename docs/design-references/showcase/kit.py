"""Shared pieces for the showcase dashboards: item builders, made-up data, and the writer.

Each board module builds a `.levity` document and a Fixture scenario from these and calls `write`.
Nothing here is imported by the app.
"""
import itertools
import math
import random
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent

# ---------------------------------------------------------------- geometry and text


def g(x, y, w, h):
	return {'x': f'{round(x, 3)}%', 'y': f'{round(y, 3)}%', 'width': f'{round(w, 3)}%', 'height': f'{round(h, 3)}%'}


def text(s, geom, font='$display', weight='Medium', color='$muted', align='CenterLeft', height=None, group=None, **kw):
	t = {'type': 'text', 'text': s, 'font': font, 'weight': weight, 'color': color, 'alignment': align, 'geometry': geom}
	if height:
		t['text-height'] = height
	if group:
		t['matchingGroup'] = {'group': group, 'matchAll': True}
	t.update(kw)
	return t


def cap(s, geom, color='$muted', align='BottomLeft', tracking=0.14, group='global.cap', **kw):
	"""A small tracked caption: the label of a tile."""
	# The hint has no descender, so the caps are fitted to the box and every caption is one size.
	kw.setdefault('format-hint', 'HEADING')
	kw.setdefault('weight', 'Medium')
	return text(s, geom, color=color, align=align, tracking=tracking, group=group, **kw)


def val(key, geom, color='$text', precision=0, unit='Hidden', hint=None, height=None, group=None, align='BottomLeft',
        fmt=None, weight='Regular', font='$body', **label):
	"""One live number. `label` takes any text setting: tracking, outline, italic."""
	vl = {'color': color, 'font': font, 'weight': weight}
	if height:
		vl['text-height'] = height
	if group:
		vl['matchingGroup'] = {'group': group, 'matchAll': True}
	vl.update(label)
	d = {'unitPosition': unit, 'precision': precision, 'valueLabel': vl}
	if hint:
		d['format-hint'] = hint
	if fmt:
		d['format'] = fmt
	return {'type': 'realtime.text', 'key': key, 'title': False, 'alignment': align, 'display': d, 'geometry': geom}


_figures = itertools.count(1)


def mini(key, geom, color=None, gradient=None, hours=12, past=False, lo=None, hi=None, opacity=0.6, fill=0.25, top='55%',
         bottom='2%', weight=0.45, glow=None, kind='plot', smooth=True):
	"""A graph with no labels, to sit behind a number or stand as a sparkline."""
	plot = {'type': kind, 'weight': weight, 'opacity': opacity}
	if kind == 'plot' and fill:
		plot['fill'] = {'opacity': fill, 'fade': True}
	if kind == 'bar':
		plot.pop('weight')
		plot['width'] = 0.72
	if gradient:
		plot['gradient'] = gradient
	else:
		plot['color'] = color or '$accent'
	if glow:
		plot['glow'] = glow
	item = {'plot': plot}
	if not smooth:
		item['smooth'] = False
	fig = {'figure': f'fig{next(_figures)}', 'margins': {'top': top, 'bottom': bottom}, key: item}
	if lo is not None:
		fig['min'] = lo
	if hi is not None:
		fig['max'] = hi
	return {'type': 'mini-graph', 'geometry': geom,
	        'timeframe': ({'hours': hours, 'lookback': {'hours': hours * 2}, 'offset': {'hours': -hours}} if past
		                      else {'hours': hours, 'lookback': {'hours': 0}, 'offset': {'hours': 0}}),
	        'annotations': {'dayLabels': {'enabled': False}, 'hourLabels': {'enabled': False}, 'lines': {'enabled': False}},
	        'indicator': {'opacity': 0}, 'figures': [fig]}


def card(name, geom, items, fill='$surface', radius='22px', pad=(5, 6), **kw):
	"""A rounded card. `pad` is the inset of the content, percent of the card's width and height."""
	px, py = pad
	inner = {'type': 'group', 'name': f'{name}Body', 'geometry': g(px, py, 100 - 2 * px, 100 - 2 * py), 'items': items}
	c = {'type': 'group', 'name': name, 'geometry': geom,
	     'border': {'enabled': True, 'radius': radius, 'fill': fill, 'weight': 0}, 'items': [inner]}
	c.update(kw)
	return c


def bar(key, geom, lo, hi, color='$accent', track='$rule', weight='100%', glow=None, **display):
	fill = {'color': color}
	if glow:
		fill['glow'] = glow
	if not isinstance(track, dict):
		track = {'weight': weight, 'color': track}
	d = {'range': {'min': lo, 'max': hi}, 'track': track, 'fill': fill, 'value-label': {'visible': False}}
	for k, v in display.items():
		if isinstance(v, dict) and isinstance(d.get(k), dict):
			d[k].update(v)
		else:
			d[k] = v
	return {'type': 'realtime.bar', 'key': key, 'title': False, 'geometry': geom, 'display': d}


def ring(key, geom, lo, hi, color='$accent', track='$rule', weight='7%', start=0, end=360, glow=None, cap='round', **display):
	"""A dial with no needle: a track and a fill up to the value."""
	fill = {'weight': weight, 'color': color, 'cap': cap}
	if glow:
		fill['glow'] = glow
	d = {'radius': '96%', 'arc': {'start-angle': start, 'end-angle': end, 'weight': weight, 'color': track, 'cap': cap},
	     'range': {'min': lo, 'max': hi},
	     'major': {'enabled': False, 'labels': {'enabled': False}}, 'minor': {'enabled': False}, 'micro': {'enabled': False},
	     'needle': {'visible': False}, 'fill': fill,
	     'value-label': {'visible': False}, 'unit-label': {'visible': False}}
	for k, v in display.items():
		if isinstance(v, dict) and isinstance(d.get(k), dict):
			d[k].update(v)
		else:
			d[k] = v
	return {'type': 'realtime.gauge', 'key': key, 'title': False, 'geometry': geom, 'display': d}


# ---------------------------------------------------------------- made-up data

class Data:
	"""A scenario under construction. Series are hourly, `days` long, and begin `start` hours from midnight today."""

	def __init__(self, name, description, now_hour, days=5, start=-24):
		self.name, self.description = name, description
		self.now, self.days, self.start = now_hour, days, start
		self.n = days * 24
		self.keys = {}
		self.places = {}
		self.rng = random.Random(name)

	def hours(self):
		"""The hour of the day of every sample, and its index."""
		return [((i + self.start) % 24, i) for i in range(self.n)]

	def index_now(self):
		return int(self.now) - self.start

	def series(self, fn, noise=0.0, smooth=0, lo=None, hi=None, digits=1):
		"""`fn(hour_of_day, day_index, t)` for every hour; `t` counts hours from midnight today."""
		out = []
		for i in range(self.n):
			t = i + self.start
			v = fn(t % 24, t // 24, t)
			if noise:
				v += self.rng.gauss(0, noise)
			out.append(v)
		for _ in range(smooth):
			out = [(out[max(i - 1, 0)] + 2 * out[i] + out[min(i + 1, len(out) - 1)]) / 4 for i in range(len(out))]
		if lo is not None:
			out = [max(lo, v) for v in out]
		if hi is not None:
			out = [min(hi, v) for v in out]
		return [round(v, digits) for v in out]

	def at_now(self, series):
		"""The series read at the scenario's clock, between its two hours."""
		i = self.index_now()
		f = self.now - int(self.now)
		return series[i] + (series[min(i + 1, len(series) - 1)] - series[i]) * f

	def add(self, key, unit, series=None, value=None, digits=1, **meta):
		entry = {}
		if value is None and series is not None:
			value = round(self.at_now(series), digits)
		entry['value'] = value
		if unit is not None:
			entry['unit'] = unit
		entry.update(meta)
		if series is not None:
			entry['series'] = series
		self.keys[key] = entry
		return key

	def doc(self):
		d = {'name': self.name, 'description': self.description, 'start': self.start}
		if self.places:
			d['places'] = self.places
		d['keys'] = self.keys
		return d


def bell(h, centre, width):
	"""A smooth bump over the hours of a day, 1 at `centre`."""
	return math.exp(-((h - centre) / width) ** 2)


def daily(h, peak=15):
	"""A day's cosine, 1 at `peak` and -1 twelve hours away."""
	return math.cos((h - peak) / 24 * 2 * math.pi)


def sun(h, rise=5.5, set_=20.8):
	"""The sun's height as a share of noon, 0 at night."""
	if h <= rise or h >= set_:
		return 0.0
	return math.sin((h - rise) / (set_ - rise) * math.pi)


WIND = ['mi', 'hr']


# ---------------------------------------------------------------- writing

class _Dumper(yaml.SafeDumper):
	pass


def _series(dumper, data):
	# A list of plain numbers on one line; anything else as blocks.
	flow = len(data) > 4 and all(isinstance(v, (int, float)) or v is None for v in data)
	return dumper.represent_sequence('tag:yaml.org,2002:seq', data, flow_style=flow)


_Dumper.add_representer(list, _series)


def write(name, header, doc, data: Data, freeze, size='2880x1800'):
	"""Write `<name>.levity` and `scenarios/<name>.yaml` beside this file."""
	head = ''.join(f'# {line}\n' if line else '#\n' for line in header.strip('\n').split('\n'))
	head += (f'#\n# Generated by docs/design-references/showcase/{name}.py; edit that and run build.py.\n'
	         f'# Render: render_dashboard.py OUT.png --levity docs/design-references/showcase/{name}.levity\n'
	         f'#           --scenario docs/design-references/showcase/scenarios/{name}.yaml --size {size} --freeze-time {freeze}\n')
	(HERE / f'{name}.levity').write_text(head + yaml.dump(doc, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=150))
	(HERE / 'scenarios').mkdir(exist_ok=True)
	shead = f'# Made-up data for the {name} showcase dashboard. Generated by docs/design-references/showcase/{name}.py.\n'
	(HERE / 'scenarios' / f'{name}.yaml').write_text(shead + yaml.dump(data.doc(), Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=4000))
	return {'name': name, 'freeze': freeze, 'size': size}


def inside(parent, x, y, w, h):
	"""Board coordinates as the geometry of a child of `parent` (board x, y, w, h)."""
	px, py, pw, ph = parent
	return g((x - px) / pw * 100, (y - py) / ph * 100, w / pw * 100, h / ph * 100)


def plate(name, x, y, w, h, fill='$surface', radius='24px', **kw):
	"""An empty rounded card, drawn under whatever is placed over it."""
	p = {'type': 'group', 'name': name, 'geometry': g(x, y, w, h), 'border': {'enabled': True, 'radius': radius, 'fill': fill, 'weight': 0}}
	p.update(kw)
	return p


def nest(name, rect, items, fill='$surface', radius='24px', **kw):
	"""A rounded card holding `items`, whose geometry was written in board coordinates."""
	px, py, pw, ph = rect
	out = []
	for item in items:
		item = dict(item)
		if 'geometry' in item:
			q = {k: float(str(v).rstrip('%')) for k, v in item['geometry'].items()}
			item['geometry'] = g((q['x'] - px) / pw * 100, (q['y'] - py) / ph * 100, q['width'] / pw * 100, q['height'] / ph * 100)
		out.append(item)
	group = {'type': 'group', 'name': name, 'geometry': g(*rect), 'items': out}
	if fill:
		group['border'] = {'enabled': True, 'radius': radius, 'fill': fill, 'weight': 0}
	group.update(kw)
	return group
