"""Which module-level names does a set of classes in Gauge.py actually use?

The import block for a moved module has to be exactly this list, no more and no
less: anything missing breaks at import, anything extra is dead weight a reviewer
has to check. Run it before each move, with the class names being moved.

    python move_inventory.py MeterItem GaugePathItem Graduations Tick SubTick TickSurface
"""
import ast
import builtins
import sys
from pathlib import Path

GAUGE = Path(sys.argv[1])
ARGS = sys.argv[2:]


def main(names: list) -> int:
	source = GAUGE.read_text()
	tree = ast.parse(source)

	# Everything Gauge.py defines or imports at module level, and where from.
	module_names = {}
	for node in tree.body:
		if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
			module_names[node.name] = 'defined here'
		elif isinstance(node, ast.Assign):
			for target in node.targets:
				if isinstance(target, ast.Name):
					module_names[target.id] = 'defined here'
		elif isinstance(node, (ast.Import, ast.ImportFrom)):
			for alias in node.names:
				module_names[alias.asname or alias.name.split('.')[0]] = f'{".".join(filter(None, [getattr(node, "module", None)]))}'

	wanted = set(names)
	found = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef) and node.name in wanted}
	missing = wanted - set(found)
	if missing:
		print(f'not a module-level class in Gauge.py: {sorted(missing)}')
		return 1

	used, defined_inside = set(), set()
	for name, node in found.items():
		for sub in ast.walk(node):
			if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and sub is not node:
				defined_inside.add(sub.name)
				for arg in sub.args.args + sub.args.kwonlyargs + sub.args.posonlyargs:
					defined_inside.add(arg.arg)
			if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load):
				used.add(sub.id)
			elif isinstance(sub, ast.Attribute):
				base = sub
				while isinstance(base, ast.Attribute):
					base = base.value
				if isinstance(base, ast.Name):
					used.add(base.id)

	external = sorted(n for n in used if n not in defined_inside and n not in dir(builtins))
	print(f'classes: {", ".join(sorted(found))}')
	print(f'uses {len(external)} outside names:\n')
	from_elsewhere = [n for n in external if n in module_names and module_names[n] != 'defined here']
	defined_here = [n for n in external if module_names.get(n) == 'defined here']
	print('  imports to bring along:')
	for name in from_elsewhere:
		print(f'    {name:<28} from {module_names[name]}')
	print('\n  Gauge.py\'s own functions/classes it calls (move these first, or move together):')
	for name in defined_here:
		print(f'    {name}')
	unknown = [n for n in external if n not in module_names]
	if unknown:
		print('\n  not at module level at all (locals? typos?):')
		for name in unknown:
			print(f'    {name}')
	return 0


if __name__ == '__main__':
	sys.exit(main(ARGS))
