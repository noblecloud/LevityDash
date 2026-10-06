"""Compare moved member text against the same member at a given git revision."""
import ast
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
	old = subprocess.run(['git', '-C', REPO, 'show', REV], capture_output=True, text=True, check=True).stdout
	new = Path(target_file).read_text()
	wanted = set(names)
	before = members(old, 'Gauge', wanted)
	after = members(new, target_class, wanted)
	bad = []
	for name in names:
		same = before.get(name) == after.get(name)
		if not same:
			bad.append(name)
		print('  {:<22} {}'.format(name, 'identical' if same else 'DIFFERS'))
	print('all identical' if not bad else 'DIFFER: ' + ', '.join(bad))
	return 1 if bad else 0


if __name__ == '__main__':
	sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3:]))
