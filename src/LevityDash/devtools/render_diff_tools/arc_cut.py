"""Classify a class's members: general (a Meter could hold it) vs arc-specific.

For the meter split. For each member of the class, count references to arc-ish
names (the arc, angles, radius sizing, radial placement) against the general
ones, so the cut is made on what the code touches rather than on member names.

    python arc_cut.py Gauge.py Gauge
"""
import ast
import sys
from pathlib import Path

ARC_NAMES = {
	'arc', 'ArcTrack', 'GaugeArc', 'GaugeTickText', 'GaugeTickTextGroup', 'radius', 'crossSize', 'sizeAcross',
	'angle', 'angles', '_angles', '_angle', 'angleAt', 'startAngle', 'endAngle', 'start_angle', 'end_angle',
	'clockTurn', 'CLOCK_HANDS', '_tickClock', 'radialPoint', 'normalAtAngle', 'pointAtAngle', 'markAngle',
	'subPath', 'arcLength', 'arc_length', 'arcRect', 'arcEnd', 'arcStart', '_dialRect', '_gauge_path',
	'full_gauge_path', 'full_gauge_rect', '_radial', 'Angular', 'ticks', 'tickType', 'tick_type',
}
GENERAL_NAMES = {
	'range', 'valueSource', 'valueClass', 'value', 'refresh', 'rebuild', '_update_shape', 'trackRect', 'center',
	'baseWidth', 'marginRect', 'anchor', 'inset', 'safe_area', 'recenter', 'statefulParent', 'configure', 'source',
	'displayValue', 'label', 'unit',
}


def member_nodes(cls):
	for stmt in cls.body:
		if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
			yield stmt.name, stmt.lineno, stmt.end_lineno, stmt
		elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
			yield f'{stmt.target.id} (field)', stmt.lineno, stmt.end_lineno, stmt
		elif isinstance(stmt, ast.Assign):
			for t in stmt.targets:
				if isinstance(t, ast.Name):
					yield f'{t.id} (field)', stmt.lineno, stmt.end_lineno, stmt


def names_used(node) -> set:
	used = set()
	for sub in ast.walk(node):
		if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load):
			used.add(sub.id)
		elif isinstance(sub, ast.Attribute):
			used.add(sub.attr)
	return used


def main(path: str, class_name: str) -> int:
	source = Path(path).read_text()
	tree = ast.parse(source)
	cls = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == class_name)
	# decorators belong to the member, so read a few lines above each definition
	lines = source.splitlines()

	rows = []
	for name, start, end, node in member_nodes(cls):
		used = names_used(node)
		# decorators sit just above: include them
		header_start = start
		while header_start > 1 and lines[header_start - 2].lstrip().startswith('@'):
			header_start -= 1
			used |= names_used(ast.parse('\n'.join(lines[header_start - 1:start - 1])) if False else node)
		arc = used & ARC_NAMES
		general = used & GENERAL_NAMES
		rows.append((len(arc), len(general), name, header_start, end, sorted(arc), sorted(general)))

	rows.sort(key=lambda r: (-r[0], r[2]))
	print(f'{class_name}: {len(rows)} members\n')
	print('arc-specific (the meter cannot hold these):')
	for arc, general, name, start, end, arc_names, _ in rows:
		if arc:
			print(f'  {name:<34} lines {start}-{end:<5} ({end - start + 1:>3})  arc:{",".join(arc_names[:5])}')
	print('\nno arc reference at all:')
	for arc, general, name, start, end, _, general_names in rows:
		if not arc:
			tag = f'  general:{",".join(general_names[:4])}' if general_names else ''
			print(f'  {name:<34} lines {start}-{end:<5} ({end - start + 1:>3}){tag}')
	return 0


if __name__ == '__main__':
	sys.exit(main(sys.argv[1], sys.argv[2]))
