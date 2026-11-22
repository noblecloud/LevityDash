"""Turn a folder of SVG icons into a glyph map.

A pack is data (see `lib/ui/icons.py`), so adding an icon set is a build step:
read every `.svg`, keep the drawing instructions, write one TOML map. Run it by
hand when a set is vendored or updated; nothing calls it at runtime.

	python -m LevityDash.devtools.import_svg_pack SOURCE_DIR OUT.toml \
	    --prefix qw --name "QWeather Icons" --style line --strip qi-

What it keeps: the `d` data of paths and the basic shapes (circle, ellipse, rect,
line, polyline, polygon), each part's stroke width and `transform`, and a role.
What it drops: gradients, masks, filters, clip paths, `<use>`, and CSS. A shape
that paints from `url(#…)` is skipped with a warning, because a single-colour
glyph cannot show it.

Roles: `fill="white"` becomes `cutout` (subtracted from the rest — the way a
monochrome set draws a hole), anything else is `body`.
"""
import argparse
import re
import sys
import xml.etree.ElementTree as ElementTree
from pathlib import Path
from typing import Dict, List, Optional

_NS = '{http://www.w3.org/2000/svg}'
#: Attribute inheritance that matters for a flat glyph.
_INHERITED = ('fill', 'stroke', 'stroke-width', 'fill-rule', 'opacity', 'fill-opacity', 'stroke-opacity')
_SKIP_TAGS = {f'{_NS}defs', f'{_NS}mask', f'{_NS}clipPath', f'{_NS}linearGradient', f'{_NS}radialGradient',
              f'{_NS}pattern', f'{_NS}filter', f'{_NS}symbol', f'{_NS}style', f'{_NS}title', f'{_NS}desc'}


def _tag(element) -> str:
	return element.tag if isinstance(element.tag, str) else ''


def _local(tag: str) -> str:
	return tag.split('}', 1)[-1]


def _num(element, name: str, default: float = 0.0) -> float:
	value = element.get(name)
	if value is None:
		return default
	value = value.strip().rstrip('px')
	try:
		return float(value)
	except ValueError:
		return default


def _style_of(element, inherited: dict) -> dict:
	"""Attributes this element paints with, merged over what it inherited."""
	style = dict(inherited)
	for key in _INHERITED:
		if (value := element.get(key)) is not None:
			style[key] = value.strip()
	# A `style="fill:#fff;stroke:none"` pair on the element itself.
	inline = element.get('style') or ''
	for declaration in inline.split(';'):
		if ':' in declaration:
			key, value = declaration.split(':', 1)
			if key.strip() in _INHERITED:
				style[key.strip()] = value.strip()
	if 'currentColor' in (style.get('fill', ''), style.get('stroke', '')):
		style.pop('fill-opacity', None)
	return style


def _shape_path(element, tag: str) -> Optional[str]:
	"""`d` data for one shape element, or `None` when the tag draws nothing."""
	if tag == f'{_NS}path':
		return element.get('d')
	if tag == f'{_NS}circle':
		cx, cy, r = _num(element, 'cx'), _num(element, 'cy'), _num(element, 'r')
		if r <= 0:
			return None
		return f'M{cx - r} {cy} A{r} {r} 0 1 0 {cx + r} {cy} A{r} {r} 0 1 0 {cx - r} {cy} Z'
	if tag == f'{_NS}ellipse':
		cx, cy, rx, ry = _num(element, 'cx'), _num(element, 'cy'), _num(element, 'rx'), _num(element, 'ry')
		if rx <= 0 or ry <= 0:
			return None
		return f'M{cx - rx} {cy} A{rx} {ry} 0 1 0 {cx + rx} {cy} A{rx} {ry} 0 1 0 {cx - rx} {cy} Z'
	if tag == f'{_NS}rect':
		x, y, width, height = _num(element, 'x'), _num(element, 'y'), _num(element, 'width'), _num(element, 'height')
		if width <= 0 or height <= 0:
			return None
		return f'M{x} {y} H{x + width} V{y + height} H{x} Z'
	if tag == f'{_NS}line':
		return f'M{_num(element, "x1")} {_num(element, "y1")} L{_num(element, "x2")} {_num(element, "y2")}'
	if tag in (f'{_NS}polyline', f'{_NS}polygon'):
		points = [float(x) for x in re.split(r'[\s,]+', (element.get('points') or '').strip()) if x]
		if len(points) < 4:
			return None
		pairs = list(zip(points[0::2], points[1::2]))
		data = f'M{pairs[0][0]} {pairs[0][1]}' + ''.join(f' L{x} {y}' for x, y in pairs[1:])
		return data + (' Z' if _local(tag) == 'polygon' else '')
	return None


def _is_background_plate(element, tag: str, box: Optional[tuple]) -> bool:
	"""A white shape that covers the whole viewBox is a backdrop, not a knock-out.

	Iconoir's `snapchat` is the case that found this: a `rect` 24×24 filled white under
	the real path. Treated as a cutout it carves the glyph away to nothing.
	"""
	if box is None or tag != f'{_NS}rect':
		return False
	_, _, width, height = box
	return (_num(element, 'x') <= 0 and _num(element, 'y') <= 0
	        and _num(element, 'width') >= width - 1e-6 and _num(element, 'height') >= height - 1e-6)


def _walk(element, inherited: dict, parts: List[dict], warnings: List[str], name: str, box: Optional[tuple] = None):
	tag = _tag(element)
	if tag in _SKIP_TAGS:
		return
	style = _style_of(element, inherited)
	data = _shape_path(element, tag)
	if data:
		fill = style.get('fill', 'black')
		stroke = style.get('stroke', 'none')
		stroke_width = float(style.get('stroke-width', 1.0) or 1.0)
		draws_nothing = fill in ('none', 'transparent') and stroke in ('none', 'transparent')
		if not draws_nothing:
			if fill.startswith('url(') and stroke in ('none', 'transparent'):
				warnings.append(f'{name}: a shape filled by {fill} is dropped (single-colour glyph)')
			elif fill in ('white', '#fff', '#ffffff', 'rgb(255,255,255)') and _is_background_plate(element, tag, box):
				pass  # a backdrop, not a cutout: skipping it is what makes the glyph draw
			else:
				part = {'d': ' '.join(data.split())}
				if fill in ('none', 'transparent'):
					part['stroke'] = stroke_width
				if style.get('fill-rule') == 'evenodd' or element.get('clip-rule') == 'evenodd':
					part['rule'] = 'evenodd'
				if fill in ('white', '#fff', '#ffffff', 'rgb(255,255,255)'):
					part['role'] = 'cutout'
				if element.get('transform'):
					part['transform'] = ' '.join(element.get('transform').split())
				parts.append(part)
	for child in element:
		_walk(child, style, parts, warnings, name, box)


def _viewbox_of(root) -> Optional[tuple]:
	value = root.get('viewBox')
	if value:
		numbers = [float(x) for x in re.split(r'[\s,]+', value.strip()) if x]
		if len(numbers) == 4:
			return tuple(numbers)
	width, height = _num(root, 'width'), _num(root, 'height')
	if width > 0 and height > 0:
		return (0.0, 0.0, width, height)
	return None


def _toml_string(value: str) -> str:
	return "'" + value.replace("'", "''") + "'"


_NUMBER = re.compile(r'[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?')


def _trim(d: str, precision: int) -> str:
	"""Round and compact a `d` string, so a dense set does not cost megabytes.

	Numbers are rounded, then packed the way an SVG minifier does: no space after a
	command letter, and a space between numbers only when the next one does not start
	with `-` or `.`. With three decimals the shift is invisible at glyph sizes (0.001
	of a 128 unit box is a thousandth of a pixel at 100 px).
	"""
	if precision is None:
		return d
	out: List[str] = []
	_COMMANDS = 'MmLlHhVvCcSsQqTtAaZz'
	_ARITY = {'M': 2, 'L': 2, 'H': 1, 'V': 1, 'C': 6, 'S': 4, 'Q': 4, 'T': 2, 'A': 7, 'Z': 0}
	pending_space = False
	command = ''
	position = 0
	index = 0
	length = len(d)
	while index < length:
		character = d[index]
		if character.isspace() or character == ',':
			index += 1
			continue
		if character in _COMMANDS:
			out.append(character)
			command = character.upper()
			position = 0
			pending_space = False
			index += 1
			continue
		if command == 'A' and position in (3, 4):
			# An arc's large-arc and sweep flags are *single characters*, so a writer may pack
			# them as `0022` (flags 0,0 then x=22). Reading that as one number loses an
			# argument and every later one shifts — the glyph then fails to parse at all.
			number = character
			index += 1
		else:
			match = _NUMBER.match(d, index)
			if match is None:
				index += 1
				continue
			number = f'{round(float(match.group()), precision):g}'
			index = match.end()
		if pending_space and not number.startswith(('-', '.')):
			out.append(' ')
		out.append(number)
		pending_space = True
		position += 1
		if _ARITY.get(command, 0) and position == _ARITY[command]:
			position = 0
	return ''.join(out)



def _part_inline(part: dict) -> str:
	fields = [f'd = {_toml_string(part["d"])}']
	if 'stroke' in part:
		fields.append(f'stroke = {part["stroke"]:g}')
	if part.get('role'):
		fields.append(f'role = {_toml_string(part["role"])}')
	if part.get('rule'):
		fields.append(f'rule = {_toml_string(part["rule"])}')
	if part.get('transform'):
		fields.append(f'transform = {_toml_string(part["transform"])}')
	return '{ ' + ', '.join(fields) + ' }'


def convert(source: Path, prefix: str, name: str, style: str, strip: str, pattern: str, default_stroke: float, precision: int = 3) -> tuple:
	files = sorted(source.glob(pattern))
	if not files:
		raise SystemExit(f'no SVG files in {source} matching {pattern}')
	glyphs: Dict[str, list] = {}
	box = None
	boxes = set()
	warnings: List[str] = []
	for file in files:
		try:
			root = ElementTree.parse(file).getroot()
		except ElementTree.ParseError as error:
			warnings.append(f'{file.name}: unreadable ({error}); skipped')
			continue
		box_for_file = _viewbox_of(root)
		if box_for_file is not None:
			boxes.add(tuple(round(x, 3) for x in box_for_file))
		parts: List[dict] = []
		_walk(root, {}, parts, warnings, file.stem, box_for_file)
		if not parts:
			warnings.append(f'{file.name}: no drawable shapes; skipped')
			continue
		icon = file.stem
		if strip and icon.startswith(strip):
			icon = icon[len(strip):]
		icon = icon.strip('-_ ').lower()
		for part in parts:
			part['d'] = _trim(part['d'], precision)
		glyphs[icon] = parts

	if len(boxes) > 1:
		raise SystemExit(f'the set uses {len(boxes)} different viewBoxes {sorted(boxes)}; convert one size at a time')
	if boxes:
		box = sorted(boxes)[0]
	return glyphs, box, warnings


def write_map(path: Path, prefix: str, name: str, style: str, box: tuple, default_stroke: float, glyphs: Dict[str, list]):
	lines = [
		f'[{prefix}]',
		f'prefix = "{prefix}"',
		f'name = "{name}"',
		f'default = "{style}"',
		'',
		f'[{prefix}.{style}]',
		f'viewBox = "{" ".join(f"{x:g}" for x in box)}"',
	]
	if default_stroke:
		lines.append(f'stroke = {default_stroke:g}')
	lines += ['', f'[{prefix}.{style}.svg]']
	for icon in sorted(glyphs):
		parts = glyphs[icon]
		uniform = (
			len(parts) == 1
			and 'transform' not in parts[0]
			and 'role' not in parts[0]
			and ('stroke' in parts[0]) == bool(default_stroke)
		)
		if uniform:
			lines.append(f'{icon} = {_toml_string(parts[0]["d"])}')
		else:
			rendered = ',\n  '.join(_part_inline(part) for part in parts)
			lines.append(f'{icon} = [\n  {rendered},\n]')
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text('\n'.join(lines) + '\n')


def main(argv=None) -> int:
	parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
	parser.add_argument('source', type=Path, help='folder of .svg files')
	parser.add_argument('out', type=Path, help='map file to write')
	parser.add_argument('--prefix', required=True, help='pack prefix, e.g. qw')
	parser.add_argument('--name', default=None, help='pack name for error messages')
	parser.add_argument('--style', default='line', help='style table name (default: line)')
	parser.add_argument('--strip', default='', help='filename prefix to strip from every icon name')
	parser.add_argument('--pattern', default='*.svg', help='glob inside the folder (default: *.svg)')
	parser.add_argument('--stroke', type=float, default=0.0, help='default stroke width for line sets (0 = filled)')
	parser.add_argument('--precision', type=int, default=3, help='decimals kept in path data (default: 3)')
	args = parser.parse_args(argv)

	glyphs, box, warnings = convert(
		args.source, args.prefix, args.name or args.prefix, args.style, args.strip, args.pattern, args.stroke, args.precision,
	)
	if box is None:
		box = (0.0, 0.0, 24.0, 24.0)
		warnings.append('no viewBox found; assumed 0 0 24 24')
	write_map(args.out, args.prefix, args.name or args.prefix, args.style, box, args.stroke, glyphs)
	for warning in warnings[:20]:
		print(f'warning: {warning}', file=sys.stderr)
	if len(warnings) > 20:
		print(f'warning: … and {len(warnings) - 20} more', file=sys.stderr)
	print(f'{len(glyphs)} glyphs -> {args.out} (viewBox {" ".join(f"{x:g}" for x in box)})')
	return 0


if __name__ == '__main__':
	raise SystemExit(main())
