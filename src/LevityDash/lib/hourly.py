"""`preset: hourly-row`: columns of readings that sit under the matching time of a graph.

A graph draws `timeframe.range` across its whole width, starting `offset` from now (default 6 hours back). So the
time `now + t` is at `(t - offset) / range` of the width, and a column placed there lines up under the graph's own
line at that time, whatever the graph shows. The row takes the same `timeframe` as the graph and the same width
(put both in one column, or one `group`). Add `graph: <its name>` and each column also follows the graph's real axis
(`time-axis`), which is what keeps it exact when the graph starts earlier than `now + offset` because it has older data, and builds one column for every `step` hours from now.

	- preset: hourly-row
	  props:
	    timeframe: {days: 1, hours: 12}
	    step: 3
	    rows:
	      - {key: 'at(environment.temperature.temperature, {offset})', precision: 0}
	      - {key: 'at(environment.precipitation.probability, {offset})', precision: 0, color: $info}

`{offset}` in a key becomes the column's distance from now (`3h`, `1.5h`, or `0h` for now). Each column is a vertical
stack: the time, then one reading per row. The times are clocks that show `now + offset`; the readings and the
times are always for the same moment. The result is a `group`, so it is placed like any item with `geometry`.
Qt-free, like `table`.
"""
from math import floor
from typing import Any, Dict, List

__all__ = ['build', 'PROPS', 'NAME', 'columnTimes', 'spanHours']

NAME = 'hourly-row'

PROPS: Dict[str, tuple] = {
	'timeframe': ({'days': 1, 'hours': 12}, 'The same timeframe as the graph this row sits under: `{days, hours, ...}` and an optional `offset`'),
	'graph': (None, 'The `name` of the graph to follow. Set, the columns slide to sit under the graph\'s real time axis; unset, they sit where the timeframe says'),
	'step': (3, 'Hours between two columns'),
	'past': (False, 'Also build the columns before now that fit the graph (false: now and after)'),
	'rows': ([], 'The readings in each column: a list of {key, precision, format, color, unit}. `{offset}` in a key is the column\'s distance from now'),
	'head': ('clock', 'The name over a column: clock (the time, as a clock), relative (+3h) or none'),
	'headFormat': ('%-I%p', 'strftime format of a clock head'),
	'headSize': ('22%', 'Height of the head, as a share of the column; the readings share the rest'),
	'nowLabel': ('Now', 'The head of the column at now; empty keeps the clock'),
	'rowGap': ('$space_1', 'Space between the head and the readings'),
	'numberAlign': ('decimal', 'decimal, end or none: how the numbers in a column line up'),
	'titleGroup': ('global.title', 'Size group of the heads; the default spans the whole dashboard'),
	'valueGroup': ('global.value', 'Size group of the numbers; the default spans the whole dashboard'),
	'font': (None, 'Font of the numbers; unset keeps the font of the panel around it'),
}

_ROW = {'key', 'precision', 'format', 'color', 'unit'}
_RANGE = {'weeks', 'days', 'hours', 'minutes'}
_EDGE = 1e-6


def spanHours(value: Any, what: str) -> float:
	"""A span as hours: a number, `3h`, or a mapping such as `{days: 1, hours: 12}`."""
	if isinstance(value, dict):
		unknown = set(value) - _RANGE - {'offset', 'lookback'}
		if unknown:
			raise ValueError(f'{what} has no setting {", ".join(sorted(map(str, unknown)))}')
		return sum(float(value.get(k, 0)) * m for k, m in (('weeks', 168), ('days', 24), ('hours', 1), ('minutes', 1 / 60)))
	if isinstance(value, (int, float)) and not isinstance(value, bool):
		return float(value)
	text = str(value).strip().lower()
	for suffix, factor in (('min', 1 / 60), ('h', 1), ('d', 24)):
		if text.endswith(suffix):
			try:
				return float(text[:-len(suffix)]) * factor
			except ValueError:
				break
	raise ValueError(f'{what} is {value!r}; write hours as a number or 3h, 90min')


def _frame(timeframe: Any) -> tuple:
	"""(range, offset) in hours, read as a graph reads its `timeframe`."""
	if not isinstance(timeframe, dict):
		raise ValueError(f'timeframe is {timeframe!r}; write it like the graph: {{days: 1, hours: 12}}')
	span = spanHours(timeframe, 'timeframe')
	if span <= 0:
		raise ValueError('timeframe must be longer than zero')
	offset = timeframe.get('offset', -6)
	offset = spanHours(offset, 'timeframe offset')
	return span, offset


def _offsetText(hours: float) -> str:
	return f'{hours:g}h' if float(hours).is_integer() or round(hours * 4) == hours * 4 else f'{round(hours * 60)}min'


def columnTimes(timeframe: dict, step: float, past: bool = False) -> List[tuple]:
	"""(hours from now, left edge in % of the width, width in %) of each column that fits the graph.

	A column is `step` hours wide and centred on its time, so it sits on the graph from half a step before to half a
	step after. Columns that would hang over the graph's edge are left out.
	"""
	span, offset = _frame(timeframe)
	if step <= 0:
		raise ValueError('step must be more than zero')
	width = step / span * 100
	columns = []
	first = floor(offset / step) - 1 if past else 0
	last = int((offset + span) // step) + 1
	for k in range(first, last + 1):
		t = k * step
		left = ((t - offset) / span) * 100 - width / 2
		if left < -_EDGE or left + width > 100 + _EDGE:
			continue
		columns.append((t, round(left, 4), round(width, 4)))
	return columns


def build(props: Dict[str, Any]) -> dict:
	rows = props.get('rows') or []
	if not isinstance(rows, list) or not rows:
		raise ValueError('an hourly row needs rows: a list with at least one reading')
	for number, row in enumerate(rows, start=1):
		if not isinstance(row, dict):
			raise ValueError(f'row {number} is {row!r}, not a mapping')
		unknown = set(row) - _ROW
		if unknown:
			raise ValueError(f'row {number} has no setting {", ".join(sorted(map(str, unknown)))}. It has: {", ".join(sorted(_ROW))}')
		if not row.get('key'):
			raise ValueError(f'row {number} has no key')
	head = props.get('head') or 'none'
	if head not in ('clock', 'relative', 'none'):
		raise ValueError(f'head is {head!r}; it is clock, relative or none')
	number_align = props.get('numberAlign')
	if number_align not in ('decimal', 'end', 'none', None):
		raise ValueError(f'numberAlign is {number_align!r}; it is decimal, end or none')
	try:
		step = float(props['step'])
	except (TypeError, ValueError):
		raise ValueError(f'step is {props["step"]!r}; it is a number of hours') from None
	columns = columnTimes(props['timeframe'], step, bool(props.get('past')))
	if not columns:
		raise ValueError('no column fits the timeframe: lower the step or lengthen the timeframe')
	title_group = {'group': props['titleGroup'], 'matchAll': True}
	value_group = {'group': props['valueGroup'], 'matchAll': True}
	items: List[dict] = []
	for t, left, width in columns:
		offset = _offsetText(t) if t else '0h'
		cell: List[dict] = []
		if head != 'none':
			if t == 0 and props.get('nowLabel'):
				cell.append({'type': 'text', 'text': str(props['nowLabel']), 'color': '$muted', 'alignment': 'Center', 'matchingGroup': title_group})
			elif head == 'relative':
				cell.append({'type': 'text', 'text': f'{t:+g}h', 'color': '$muted', 'alignment': 'Center', 'matchingGroup': title_group})
			else:
				cell.append({
					'type': 'clock', 'items': [{'format': props['headFormat'], 'offset': offset, 'color': '$muted', 'alignment': 'Center', 'matchingGroup': title_group}],
				})
			cell[0]['size'] = props['headSize']
		for row in rows:
			valueLabel: Dict[str, Any] = {'matchingGroup': value_group, 'alignment': 'Center'}
			if number_align not in (None, 'none'):
				valueLabel['number-align'] = number_align
			if row.get('color'):
				valueLabel['color'] = row['color']
			display: Dict[str, Any] = {'valueLabel': valueLabel}
			if not row.get('unit'):
				display['unitPosition'] = 'Hidden'
			if props.get('font'):
				display['font'] = props['font']
			for name in ('precision', 'format'):
				if row.get(name) is not None:
					display[name] = row[name]
			cell.append({'type': 'realtime.text', 'key': str(row['key']).replace('{offset}', offset), 'title': False, 'display': display})
		column = {
			'type': 'stack', 'direction': 'Vertical', 'spacing': props['rowGap'],
			'geometry': {'x': f'{left:g}%', 'y': '0%', 'width': f'{width:g}%', 'height': '100%'}, 'items': cell,
		}
		if props.get('graph'):
			column['time-axis'] = {'graph': props['graph'], 'at': offset}
		items.append(column)
	return {'type': 'group', 'items': items}
