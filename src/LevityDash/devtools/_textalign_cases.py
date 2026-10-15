"""The case catalogue for the text alignment harness. Qt-free, so the tests can read it without booting anything.

A case is one or more panels on an empty 1600x1000 dashboard, each holding items written the way a `.levity`
file writes them. The runner (`text_alignment.py`) builds the panels, lets the dashboard settle, and measures
every text it finds. `facts` carries what the test needs and the measurement cannot know: for a layout case,
the cells the items were meant to land in, in scene pixels.

Ids are paths: `align/wide/TopLeft`, `font/Roboto Mono-Bold/Center`. A test selects cases by prefix.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

SCENE = (1600, 1000)

ALIGNMENTS = (
	'TopLeft', 'CenterLeft', 'BottomLeft',
	'TopCenter', 'Center', 'BottomCenter',
	'TopRight', 'CenterRight', 'BottomRight',
)

#: The bundled fonts (src/LevityDash/resources/fonts)
FONTS = ('Nunito', 'Roboto', 'Roboto Mono')
WEIGHTS = ('Normal', 'Bold')

#: A string with ascenders, a descender and digits, and a short one with none of the last
TEXTS = ('Hamburg 88', 'Hi')


@dataclass
class Panel:
	geometry: dict
	items: list


@dataclass
class Case:
	id: str
	panels: list[Panel]
	facts: dict = field(default_factory=dict)
	note: str = ''


def px(x, y, width, height) -> dict:
	return {'x': f'{x}px', 'y': f'{y}px', 'width': f'{width}px', 'height': f'{height}px'}


def label(text: str, alignment: str = 'Center', **kw) -> dict:
	return {'type': 'label', 'text': text, 'alignment': alignment, **kw}


#: name -> (width, height) of a label box in px; wide leaves room across, tall leaves room down
SHAPES = {'wide': (620, 84), 'tall': (92, 420), 'square': (300, 300)}


def alignCases() -> Iterable[Case]:
	"""Every alignment in boxes that leave room on one axis, for a string with a descender and one without."""
	for shape, (w, h) in SHAPES.items():
		for alignment in ALIGNMENTS:
			panels = [
				Panel(px(40 + i * (w + 60), 40, w, h), [label(text, alignment, margins='0px')])
				for i, text in enumerate(TEXTS)
			]
			yield Case(f'align/{shape}/{alignment}', panels)


def fontCases() -> Iterable[Case]:
	for font in FONTS:
		for weight in WEIGHTS:
			for alignment in ('TopLeft', 'Center', 'BottomRight'):
				yield Case(f'font/{font}-{weight}/{alignment}', [
					Panel(px(40, 40, 700, 90), [label('Hamburg 88', alignment, font=font, weight=weight)]),
				])


def sizeCases() -> Iterable[Case]:
	for height in (14, 24, 48, 96, 200):
		for alignment in ('TopLeft', 'Center', 'BottomRight'):
			yield Case(f'size/{height}px/{alignment}', [
				Panel(px(40, 40, 520, height), [label('Hamburg 88', alignment, margins='0px')]),
			])


#: margins as a file would write them
MARGINS = {
	'none': '0px',
	'even-10px': '10px',
	'even-20pct': '20%',
	'uneven': {'left': '30px', 'top': '2px', 'right': '4px', 'bottom': '20px'},
	'default': None,
}


def marginCases() -> Iterable[Case]:
	for name, margins in MARGINS.items():
		for alignment in ('TopLeft', 'Center', 'BottomRight'):
			extra = {} if margins is None else {'margins': margins}
			yield Case(f'margins/{name}/{alignment}', [
				Panel(px(40, 40, 520, 110), [label('Hamburg 88', alignment, **extra)]),
			])


def textHeightCases() -> Iterable[Case]:
	"""`text-height` narrows the limit rect to a band centred in the box."""
	for height in ('12px', '40%', '60px'):
		for alignment in ('TopLeft', 'Center', 'BottomRight'):
			yield Case(f'text-height/{height}/{alignment}', [
				Panel(px(40, 40, 520, 110), [label('Hamburg 88', alignment, margins='0px', **{'text-height': height})]),
			])


def nestedCases() -> Iterable[Case]:
	"""Percent geometry three levels deep: the label's box must be where the nominal arithmetic puts it."""
	outer = (100, 100, 800, 400)
	mid = (outer[0] + .25 * outer[2], outer[1] + .25 * outer[3], .5 * outer[2], .5 * outer[3])
	inner = (mid[0] + .1 * mid[2], mid[1] + .1 * mid[3], .8 * mid[2], .3 * mid[3])
	for alignment in ('CenterLeft', 'Center', 'CenterRight', 'TopLeft', 'BottomRight'):
		yield Case(
			f'nested/{alignment}',
			[Panel(px(*outer), [{
				'type': 'group', 'geometry': {'x': '25%', 'y': '25%', 'width': '50%', 'height': '50%'},
				'items': [{
					'type': 'group', 'name': 'inner', 'geometry': {'x': '10%', 'y': '10%', 'width': '80%', 'height': '30%'},
					'items': [label('Nested 42', alignment, name='leaf', margins='0px')],
				}],
			}])],
			facts={'boxes': {'Nested 42': list(inner)}},
		)


def layoutCases() -> Iterable[Case]:
	"""Labels in flex and grid cells: the label fills its cell, and the text sits in the label by its alignment."""
	for alignment in ('CenterLeft', 'Center', 'CenterRight', 'TopLeft', 'BottomRight'):
		x, y, w, h = 40, 40, 900, 100
		rest = (w * .8) / 2
		yield Case(
			f'flex/{alignment}',
			[Panel(px(x, y, w, h), [{
				'type': 'stack', 'direction': 'Horizontal', 'spacing': '0px', 'flex': {},
				'items': [
					label('Fixed', alignment, name='c1', size='20%', margins='0px'),
					label('Grows A', alignment, name='c2', flex={'grow': 1}, margins='0px'),
					label('Grows B', alignment, name='c3', flex={'grow': 1}, margins='0px'),
				],
			}])],
			facts={'boxes': {'Fixed': [x, y, w * .2, h], 'Grows A': [x + w * .2, y, rest, h], 'Grows B': [x + w * .2 + rest, y, rest, h]}},
		)
		x, y, w, h = 40, 40, 800, 300
		cw = [w * .25, w * .75]
		yield Case(
			f'grid/{alignment}',
			[Panel(px(x, y, w, h), [{
				'type': 'grid', 'spacing': '0px', 'grid': {'columns': ['1fr', '3fr'], 'rows': ['1fr', '1fr']},
				'items': [
					label('Tall cell', alignment, name='a', margins='0px', grid={'column': 1, 'row': 1, 'row-span': 2}),
					label('Top right', alignment, name='b', margins='0px', grid={'column': 2, 'row': 1}),
					label('Bottom right', alignment, name='c', margins='0px', grid={'column': 2, 'row': 2}),
				],
			}])],
			facts={'boxes': {'Tall cell': [x, y, cw[0], h], 'Top right': [x + cw[0], y, cw[1], h / 2], 'Bottom right': [x + cw[0], y + h / 2, cw[1], h / 2]}},
		)


#: Value displays on the Fixture scenario: temperature 98 F, wind 7 mph, humidity 31 %
READINGS = {
	'temperature': 'environment.temperature.temperature',
	'wind': 'environment.wind.speed.speed',
	'humidity': 'environment.humidity.humidity',
}


def reading(key: str, alignment: str | None = None, spelling: str = 'valueLabel', **display) -> dict:
	"""A `realtime.text`. `spelling`: `valueLabel` puts the alignment on the value label (the documented place),
	`item` writes `alignment:` on the item itself, the way a user expects a label to take it."""
	item = {'type': 'realtime.text', 'key': READINGS[key], 'display': dict(display)}
	if alignment and spelling == 'valueLabel':
		item['display']['valueLabel'] = {'alignment': alignment, 'margins': '0px'}
	elif alignment:
		item['alignment'] = alignment
	return item


def realtimeCases() -> Iterable[Case]:
	for key in READINGS:
		for alignment in ('CenterLeft', 'Center', 'CenterRight'):
			for spelling in ('valueLabel', 'item'):
				for unit in ('float-under', 'hidden'):
					extra = {} if unit == 'float-under' else {'unitLabel': {'visible': False}}
					yield Case(f'realtime/{key}/{spelling}/{unit}/{alignment}', [
						Panel(px(40, 40, 420, 130), [reading(key, alignment, spelling, **extra)]),
					])


def statRowCases() -> Iterable[Case]:
	"""The `stat-row` preset (a value-stack of titled readings in two global size groups) in rows of different
	shapes: a low wide strip, a tall block, and a narrow column. The text of every reading must stay in its box."""
	items = [
		{'type': 'realtime.text', 'key': READINGS['temperature'], 'title': {'text': 'Temp'}, 'display': {'precision': 0}},
		{'type': 'realtime.text', 'key': READINGS['wind'], 'title': {'text': 'Wind'}, 'display': {'precision': 0}},
		{'type': 'realtime.text', 'key': READINGS['humidity'], 'title': {'text': 'Humidity'}, 'display': {'precision': 0}},
		{'type': 'realtime.text', 'key': 'environment.pressure.pressure', 'title': {'text': 'Pressure'}, 'display': {'precision': 0}},
	]
	shapes = {'strip': (880, 80), 'block': (700, 290), 'tall': (420, 640), 'column': (150, 640)}
	for name, (w, h) in shapes.items():
		for font in ('Nunito', 'Roboto Mono'):
			yield Case(f'statrow/{name}/{font}', [Panel(px(40, 40, w, h), [
				{'preset': 'stat-row', 'props': {'items': items, 'font': font}},
			])])
	# every shape at once: the preset's groups are dashboard-wide, so the strip and the tall block fit as one
	yield Case('statrow/together', [
		Panel(px(40 + x, 40 + y, w, h), [{'preset': 'stat-row', 'props': {'items': items, 'font': 'Roboto Mono'}}])
		for (x, y), (w, h) in zip(((0, 0), (0, 120), (760, 0), (1180, 0)), shapes.values())
	])


def tileCases() -> Iterable[Case]:
	"""The tall presets built on `stat-row`, where they exist (they arrive with the example dashboards)."""
	from LevityDash.lib import presets

	available = set(presets.available())
	stats = [
		{'type': 'realtime.text', 'key': READINGS['humidity'], 'title': {'text': 'Humidity'}, 'display': {'precision': 0}},
		{'type': 'realtime.text', 'key': READINGS['wind'], 'title': {'text': 'Wind'}, 'display': {'precision': 0}},
		{'type': 'realtime.text', 'key': 'environment.pressure.pressure', 'title': {'text': 'Pressure'}, 'display': {'precision': 0}},
	]
	if 'metric-tile' in available:
		for name, (w, h) in {'wide': (528, 200), 'square': (420, 420), 'tall': (300, 520)}.items():
			yield Case(f'tiles/metric-tile/{name}', [Panel(px(40, 40, w, h), [
				{'preset': 'metric-tile', 'props': {'key': READINGS['temperature'], 'items': stats}},
			])])
	if 'climate-card' in available:
		for name, (w, h) in {'card': (380, 520), 'small': (300, 400)}.items():
			yield Case(f'tiles/climate-card/{name}', [Panel(px(40, 40, w, h), [
				{'preset': 'climate-card', 'props': {'title': 'Terrarium', 'id': 'tent'}},
			])])


def groupCases() -> Iterable[Case]:
	"""One size group across panels of different shapes. The boxes are one height (one tier) and differ in width,
	so ungrouped the narrow ones fit smaller than the wide ones, and grouped they must all come out the smallest."""
	shapes = [(40, 40, 520, 60), (600, 40, 150, 60), (40, 140, 300, 60), (380, 140, 520, 60)]
	words = ('UV', 'Temperature', 'Dew point', 'Pressure')
	for name, grouped in (('matchall', True), ('none', False)):
		group = {'group': 'global.t', 'matchAll': True}
		yield Case(f'group/labels-{name}', [
			Panel(px(*shape), [label(text, 'Center', margins='0px', **({'matchingGroup': group} if grouped else {}))])
			for shape, text in zip(shapes, words)
		], facts={'grouped': grouped})
	# the same across panels that hold values, one with a unit line and one without
	group = {'group': 'global.v', 'matchAll': True}
	for name, grouped in (('matchall', True), ('none', False)):
		panels = []
		for i, key in enumerate(READINGS):
			item = reading(key, 'Center')
			if grouped:
				item['display']['valueLabel']['matchingGroup'] = group
			if key == 'humidity':
				item['display']['unitLabel'] = {'visible': False}
			panels.append(Panel(px(40 + i * 340, 40, 300, 140), [item]))
		yield Case(f'group/values-{name}', panels, facts={'grouped': grouped})


def catalogue() -> list[Case]:
	cases: list[Case] = []
	for source in (alignCases, fontCases, sizeCases, marginCases, textHeightCases, nestedCases, layoutCases, realtimeCases, groupCases, statRowCases, tileCases):
		cases.extend(source())
	return cases


def select(prefix: str = '') -> list[Case]:
	return [case for case in catalogue() if case.id.startswith(prefix)]
