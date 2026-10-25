"""`preset: table`: a grid of readings with the labels written once.

A table is a preset whose item is built in code, because the number of cells depends on the rows and columns it is
given. It goes through the same `preset:` / `props:` path as a file preset (expansion, error tile, save folding), so
a saved dashboard keeps the short form. Qt-free, like `presets`.

	- preset: table
	  props:
	    columns:
	      - {head: Temp, unit: °F, key: 'indoor.temperature.temperature#{row}'}
	      - {head: Humidity, unit: '%', key: 'indoor.humidity.humidity#{row}'}
	    rows:
	      - {label: Bedroom, row: bedroom}
	      - {label: Office, row: office}

The result is a `grid` item: a head row (one `text` per column, the unit written once there), the row labels in the
first column (once per row), and one `realtime.text` per cell with its unit hidden and its digits aligned. The labels
and heads share the dashboard-wide `global.title` size group and the cells `global.value`.
"""
from typing import Any, Dict, List, Optional

__all__ = ['build', 'PROPS']

NAME = 'table'

#: property name -> (default, doc). The order is the order of the Studio's property list.
PROPS: Dict[str, tuple] = {
	'columns': ([], 'The columns: a list of {head, unit, key, precision, format, hint, color}. `key` may hold {row}, replaced by each row\'s `row` name'),
	'rows': ([], 'The rows: a list of {label, row, keys, color}. `keys` (one per column, null for an empty cell) replaces the columns\' keys for that row'),
	'labelWidth': ('1.2fr', 'Width of the label column, as a grid track size'),
	'headHeight': ('1fr', 'Height of the head row, as a grid track size; the rows share the rest equally'),
	'gutter': ('$space_4', 'Space between columns'),
	'rowGap': ('$space_1', 'Space between rows'),
	'numberAlign': ('decimal', 'decimal, end or none: how the numbers in a column line up'),
	'alignment': ('Center', 'Where the heads and numbers sit in their column: Left, Center or Right'),
	'titleGroup': ('global.title', 'Size group of the heads and the row labels; the default spans the whole dashboard'),
	'valueGroup': ('global.value', 'Size group of the numbers; the default spans the whole dashboard'),
	'font': (None, 'Font of the numbers; unset keeps the font of the panel around it'),
	'labelFont': (None, 'Font of the heads and the row labels; unset keeps the font of the panel around it'),
	'textHeight': (None, 'Height of every head, label and number (text-height, such as 4.5mm), so tables of different row heights share one text size; unset fits each to its cell'),
	'dividers': (None, 'dividers: settings (such as {enabled: true}) for lines between rows and columns'),
}

_COLUMN = {'head', 'unit', 'key', 'precision', 'format', 'hint', 'color'}
_ROW = {'label', 'row', 'keys', 'color'}
_ALIGN = {'Left': 'CenterLeft', 'Center': 'Center', 'Right': 'CenterRight'}


def _checked(entry: Any, allowed: set, what: str, index: int) -> dict:
	if not isinstance(entry, dict):
		raise ValueError(f'{what} {index + 1} is {entry!r}, not a mapping')
	unknown = set(entry) - allowed
	if unknown:
		raise ValueError(f'{what} {index + 1} has no setting {", ".join(sorted(map(str, unknown)))}. It has: {", ".join(sorted(allowed))}')
	return entry


def _head(column: dict) -> str:
	head, unit = column.get('head'), column.get('unit')
	return ' '.join(str(part) for part in (head, unit) if part not in (None, ''))


def build(props: Dict[str, Any]) -> dict:
	columns = props.get('columns') or []
	rows = props.get('rows') or []
	if not isinstance(columns, list) or not columns:
		raise ValueError('a table needs columns: a list with at least one column')
	if not isinstance(rows, list) or not rows:
		raise ValueError('a table needs rows: a list with at least one row')
	columns = [_checked(c, _COLUMN, 'column', i) for i, c in enumerate(columns)]
	rows = [_checked(r, _ROW, 'row', i) for i, r in enumerate(rows)]
	align = props.get('alignment') or 'Center'
	if align not in _ALIGN:
		raise ValueError(f'alignment is {align!r}; it is Left, Center or Right')
	number_align = props.get('numberAlign')
	if number_align not in ('decimal', 'end', 'none', None):
		raise ValueError(f'numberAlign is {number_align!r}; it is decimal, end or none')
	items: List[dict] = []
	title_group = {'group': props['titleGroup'], 'matchAll': True}
	value_group = {'group': props['valueGroup'], 'matchAll': True}
	text_height = props.get('textHeight')
	sized = {'text-height': text_height} if text_height not in (None, '') else {}
	if props.get('labelFont'):
		sized['font'] = props['labelFont']
	for at, column in enumerate(columns, start=1):
		if (text := _head(column)):
			items.append({
				'type': 'text', 'text': text, 'color': '$muted', 'alignment': _ALIGN[align],
				'matchingGroup': title_group, 'grid': {'column': at + 1, 'row': 1}, **sized,
			})
	for number, row in enumerate(rows, start=1):
		keys = row.get('keys')
		if keys is not None and (not isinstance(keys, list) or len(keys) != len(columns)):
			raise ValueError(f'row {number}: keys must be a list with one entry per column ({len(columns)}), or left out')
		if row.get('label') not in (None, ''):
			label = {
				'type': 'text', 'text': str(row['label']), 'alignment': 'CenterLeft', 'matchingGroup': title_group,
				'grid': {'column': 1, 'row': number + 1}, **sized,
			}
			if row.get('color'):
				label['color'] = row['color']
			else:
				label['color'] = '$muted'
			items.append(label)
		for at, column in enumerate(columns, start=1):
			key = keys[at - 1] if keys is not None else column.get('key')
			if key in (None, ''):
				continue
			if '{row}' in str(key):
				if row.get('row') in (None, ''):
					raise ValueError(f'row {number} has no `row` name, and column {at} writes {{row}} in its key')
				key = str(key).replace('{row}', str(row['row']))
			valueLabel: Dict[str, Any] = {'matchingGroup': value_group, 'alignment': _ALIGN[align], **sized}
			if number_align not in (None, 'none'):
				valueLabel['number-align'] = number_align
			color = column.get('color')
			if color:
				valueLabel['color'] = color
			# The font goes on the value label: a display has no font of its own, and one written there is ignored.
			if props.get('font'):
				valueLabel['font'] = props['font']
			display: Dict[str, Any] = {'unitPosition': 'Hidden', 'valueLabel': valueLabel}
			for name in ('precision', 'format'):
				if column.get(name) is not None:
					display[name] = column[name]
			if column.get('hint') is not None:
				display['format-hint'] = column['hint']
			items.append({
				'type': 'realtime.text', 'key': key, 'title': False, 'display': display,
				'grid': {'column': at + 1, 'row': number + 1},
			})
	grid: Dict[str, Any] = {
		'columns': [props['labelWidth'], *['1fr'] * len(columns)],
		'rows': [props['headHeight'], *['1fr'] * len(rows)],
		'gap': [props['rowGap'], props['gutter']],
	}
	item: Dict[str, Any] = {'type': 'grid', 'grid': grid, 'items': items}
	if props.get('dividers'):
		item['dividers'] = props['dividers']
	return item
