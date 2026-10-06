"""Show exactly how a moved member differs from HEAD's copy of it."""
import ast
import difflib
import subprocess
import sys
from pathlib import Path

#: The revision to compare against. Defaults to the *pre-move* commit of the
#: meter split; override with the first argument when auditing a later step.
REV = 'fd873b5:src/LevityDash/lib/ui/frontends/PySide/Modules/Displays/Gauge.py'
REPO = subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], text=True).strip()


def members(src: str, cls_name: str, wanted: set) -> dict:
	tree = ast.parse(src)
	cls = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == cls_name)
	out = {}
	for stmt in cls.body:
		key = getattr(stmt, 'name', None) or getattr(getattr(stmt, 'target', None), 'id', None)
		if key in wanted:
			out.setdefault(key, []).append(ast.get_source_segment(src, stmt))
	return out


def main(target_file: str, target_class: str, names: list) -> int:
	global REV
	if names and ':' in names[0]:
		REV, names = names[0], names[1:]
	old = subprocess.run(['git', '-C', REPO, 'show', REV], capture_output=True, text=True, check=True).stdout
	before = members(old, 'Gauge', set(names))
	after = members(Path(target_file).read_text(), target_class, set(names))
	for name in names:
		if before.get(name) == after.get(name):
			continue
		print(f'--- {name} ---')
		for b, a in zip(before.get(name, []), after.get(name, [])):
			diff = difflib.unified_diff(b.splitlines(), a.splitlines(), lineterm='', n=0)
			for line in list(diff)[2:]:
				print('   ' + line)
	return 0


if __name__ == '__main__':
	sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3:]))
