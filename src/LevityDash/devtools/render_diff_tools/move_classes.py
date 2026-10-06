"""Move classes from one module to another, byte for byte, and say what to import.

Built for the meter split (docs/tasks/meter-harness-status.md): each step moves
one family of classes out of Gauge.py into the meter package, verbatim, with the
import block computed rather than guessed. Doing it by hand meant reading and
retyping a thousand lines per family, which is where transcription errors live.

    python move_classes.py SOURCE.py TARGET.py ClassName [ClassName ...]

What it does: extracts each class (decorators included), deletes it from SOURCE
(taking the blank lines with it), appends it to TARGET, and prints

    - the names the moved classes use that resolve to SOURCE's imports, i.e. the
      block TARGET needs: name and where it comes from;
    - the names they use that SOURCE itself defines - these need a lazy import or
      a move of their own, because TARGET is imported *by* SOURCE;
    - anything else it could not resolve, which is usually a local.

It does NOT edit imports: that needs judgement (a lazy import for a cycle, an
alias, a name that already exists in TARGET), and a wrong guess here is a bug
that only shows at runtime.
"""
import ast
import builtins
import sys
from pathlib import Path


def main(argv: list) -> int:
	if len(argv) < 3:
		print(__doc__)
		return 2
	source_path, target_path = Path(argv[0]), Path(argv[1])
	wanted = set(argv[2:])

	source_text = source_path.read_text()
	tree = ast.parse(source_text)
	lines = source_text.splitlines(keepends=True)

	module_origins = {}
	for node in tree.body:
		if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
			module_origins[node.name] = None  # defined here
		elif isinstance(node, ast.Assign):
			for target in node.targets:
				if isinstance(target, ast.Name):
					module_origins[target.id] = None
		elif isinstance(node, (ast.Import, ast.ImportFrom)):
			for alias in node.names:
				module_origins[alias.asname or alias.name.split('.')[0]] = (
					node.module if isinstance(node, ast.ImportFrom) else alias.name
				)

	found = [(node, node.name) for node in tree.body if isinstance(node, ast.ClassDef) and node.name in wanted]
	missing = wanted - {name for _, name in found}
	if missing:
		print(f'not module-level classes in {source_path}: {sorted(missing)}')
		return 1

	# extract, in the order they appear, with decorators
	pieces, spans, used, defined_inside = [], [], set(), set()
	for node, name in found:
		start = min([node.lineno] + [d.lineno for d in node.decorator_list])
		text = ''.join(lines[start - 1:node.end_lineno]).rstrip() + '\n'
		pieces.append(f'\n\n{text}')
		spans.append((start, node.end_lineno))
		for sub in ast.walk(node):
			if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and sub is not node:
				defined_inside.add(sub.name)
				for arg in sub.args.args + sub.args.kwonlyargs + sub.args.posonlyargs:
					defined_inside.add(arg.arg)
			elif isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load):
				used.add(sub.id)
			elif isinstance(sub, ast.Attribute):
				base = sub
				while isinstance(base, ast.Attribute):
					base = base.value
				if isinstance(base, ast.Name):
					used.add(base.id)

	drop = set()
	for start, end in spans:
		while end + 1 <= len(lines) and lines[end].strip() == '':
			end += 1
		drop.update(range(start, end + 1))
	kept = [line for number, line in enumerate(lines, start=1) if number not in drop]
	source_path.write_text(''.join(kept))

	with target_path.open('a') as target:
		target.write(''.join(pieces))

	moved_lines = sum(piece.count('\n') for piece in pieces)
	print(f'moved {len(pieces)} classes ({moved_lines} lines) into {target_path.name}')

	external = sorted(n for n in used if n not in defined_inside and n not in dir(builtins))
	imports = [(n, module_origins[n]) for n in external if module_origins.get(n)]
	own = [n for n in external if n in module_origins and module_origins[n] is None]
	unknown = [n for n in external if n not in module_origins]

	print(f'\n{target_path.name} needs, from {source_path.name}\'s imports:')
	for name, origin in imports:
		print(f'    {name:<26} from {origin}')

	if own:
		print(f'\n{source_path.name} defines these itself - lazy import or move them:')
		for name in own:
			print(f'    {name}')
	if unknown:
		print('\nunresolved (locals, or a typo):')
		for name in unknown:
			print(f'    {name}')
	return 0


if __name__ == '__main__':
	sys.exit(main(sys.argv[1:]))
