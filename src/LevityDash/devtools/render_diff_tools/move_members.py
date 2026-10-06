"""Move members from one class body to another, byte for byte, as whole groups.

Part of the meter split (docs/tasks/meter-harness-status.md): `Meter(Display)` is
built by taking members off `Gauge` a cluster at a time. A member is often more
than one definition - a `StateProperty` with its `@prop.factory`, `@prop.setter`
and `@prop.decode` companions - and they only work as a set: the decorators are
evaluated in the class body, so the base property has to be defined before them.
So the unit of movement is "every definition with this name, in order".

    python move_members.py SOURCE.py SourceClass TARGET.py TargetClass Name [Name ...]

Both classes are class bodies at module level, so a member's text (decorators
included) is byte-identical on both sides - the move does not reindent. The target
class must be the last statement in its module, which is where a class is built up
by appending.

It prints what it moved, and the caller still has to make the names resolve: run
`ruff check --select F821` on both files afterwards.
"""
import ast
import sys
from pathlib import Path


def find_class(tree, name):
	matches = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == name]
	if len(matches) != 1:
		raise SystemExit(f'expected exactly one class named {name}, found {len(matches)}')
	return matches[0]


def group_members(cls, name):
	"""Every definition in the class body with this name, decorators included."""
	group = []
	for stmt in cls.body:
		if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) and stmt.name == name:
			group.append(stmt)
		elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name) and stmt.target.id == name:
			group.append(stmt)
		elif isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name) \
				and stmt.targets[0].id == name:
			group.append(stmt)
	if not group:
		raise SystemExit(f'{cls.name} has no member named {name}')
	start = min([stmt.lineno for stmt in group] + [d.lineno for stmt in group for d in getattr(stmt, 'decorator_list', [])])
	end = max(stmt.end_lineno for stmt in group)
	return start, end, len(group)


def main(argv: list) -> int:
	if len(argv) < 5:
		print(__doc__)
		return 2
	source_path, source_class, target_path, target_class = Path(argv[0]), argv[1], Path(argv[2]), argv[3]
	wanted = argv[4:]

	source_text = source_path.read_text()
	source_lines = source_text.splitlines(keepends=True)
	source_tree = ast.parse(source_text)
	src_cls = find_class(source_tree, source_class)

	target_text = target_path.read_text()
	target_lines = target_text.splitlines(keepends=True)
	target_tree = ast.parse(target_text)
	tgt_cls = find_class(target_tree, target_class)
	# members are inserted after the target class's last line, so the class may sit
	# anywhere at module level; the next run re-parses and picks up the new layout

	moved, drop = [], set()
	for name in wanted:
		start, end, count = group_members(src_cls, name)
		piece = ''.join(source_lines[start - 1:end]).rstrip() + '\n'
		moved.append((name, piece, count, start, end))
		tail = end
		while tail + 1 <= len(source_lines) and source_lines[tail].strip() == '':
			tail += 1
		drop.update(range(start, tail + 1))

	kept = [l for i, l in enumerate(source_lines, start=1) if i not in drop]
	source_path.write_text(''.join(kept))

	# one insert, as a block: inserting member by member renumbers the lines under
	# us and lands the later ones inside the earlier ones
	block = ''.join('\n' + piece.rstrip() + '\n' for _, piece, _, _, _ in moved)
	target_lines.insert(tgt_cls.end_lineno, block)
	for name, piece, count, start, end in moved:
		print(f'  {name:<28} {count} def(s), lines {start}-{end} in {source_path.name}')

	target_path.write_text(''.join(target_lines))
	ast.parse(source_path.read_text())
	ast.parse(target_path.read_text())
	print(f'moved {len(moved)} member group(s) from {source_class} to {target_class}')
	return 0


if __name__ == '__main__':
	sys.exit(main(sys.argv[1:]))
