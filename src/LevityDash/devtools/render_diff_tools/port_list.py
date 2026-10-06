"""What did upstream change, in terms of *what moved where*? The merge's port list.

Upstream (feat/value-sources) edited Gauge.py while this branch was moving its
contents into meter/. Git reports that as one huge conflict; the useful question
is per member: for every member upstream changed, does this branch have it
*somewhere*, and by how many hunks does upstream's text differ from ours?

    python port_list.py                 # judge against the merge's second parent
    python port_list.py --rev <rev>     # judge against a specific revision
    python port_list.py --full          # print the diffs themselves

Reads git objects only, so it works with the tree mid-merge. `MERGE_HEAD` is the
default because a moving upstream ref is the wrong answer mid-merge: it advanced
during the first sync, and judging against the new tip reported 17 members from
three commits that were never part of the merge.
"""
import ast
import difflib
import subprocess
import sys
from pathlib import Path

REPO = subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], text=True).strip()
GAUGE_PATH = 'src/LevityDash/lib/ui/frontends/PySide/Modules/Displays/Gauge.py'
MODULE_PATHS = {
	'Gauge.py': GAUGE_PATH,
	'meter/elements.py': 'src/LevityDash/lib/ui/frontends/PySide/Modules/Displays/meter/elements.py',
	'meter/meter.py': 'src/LevityDash/lib/ui/frontends/PySide/Modules/Displays/meter/meter.py',
	'meter/scale.py': 'src/LevityDash/lib/ui/frontends/PySide/Modules/Displays/meter/scale.py',
	'meter/track.py': 'src/LevityDash/lib/ui/frontends/PySide/Modules/Displays/meter/track.py',
}
REV = 'MERGE_HEAD'
#: The commit this branch grew from, for "what did upstream change".
BASE = 'fd873b5'


def show(rev: str, path: str = GAUGE_PATH) -> str:
	result = subprocess.run(['git', '-C', REPO, 'show', f'{rev}:{path}'], capture_output=True, text=True)
	if result.returncode:
		raise SystemExit(f'cannot read {rev}:{path}: {result.stderr.strip()}')
	return result.stdout


def show_ok(rev: str, path: str):
	result = subprocess.run(['git', '-C', REPO, 'show', f'{rev}:{path}'], capture_output=True, text=True)
	return result.stdout if not result.returncode else None


def here_rev() -> str:
	"""Which revision is *this branch's* side. Mid-merge the working file has
	conflict markers and HEAD is the branch being merged INTO, so the answer is
	MERGE_HEAD; after the merge (or outside one) it is the working file itself."""
	return 'MERGE_HEAD' if show_ok('MERGE_HEAD', GAUGE_PATH) else 'HEAD'


def read_module(rel: str) -> str:
	path = Path(REPO) / MODULE_PATHS[rel]
	if path.exists():
		text = path.read_text()
		if '<<<<<<<' not in text:
			return text
	return show(here_rev(), MODULE_PATHS[rel])


def classes_and_bases(src: str) -> dict:
	out = {}

	def walk(body, prefix=''):
		for node in body:
			if isinstance(node, ast.ClassDef):
				out[prefix + node.name] = [ast.unparse(b) for b in node.bases]
				walk(node.body, prefix + node.name + '.')

	walk(ast.parse(src).body)
	return out


def members(src: str) -> dict:
	"""name -> list of source segments, for module-level defs and every class body."""
	out = {}
	if not src:
		return out

	def walk(body, prefix=''):
		for node in body:
			if isinstance(node, ast.ClassDef):
				walk(node.body, prefix + node.name + '.')
			elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
				out.setdefault(prefix + node.name, []).append(ast.get_source_segment(src, node))
			elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
				out.setdefault(prefix + node.target.id, []).append(ast.get_source_segment(src, node))
			elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
				out.setdefault(prefix + node.targets[0].id, []).append(ast.get_source_segment(src, node))

	walk(ast.parse(src).body)
	return out


def main(argv: list) -> int:
	global REV
	full = '--full' in argv
	if '--rev' in argv:
		REV = argv[argv.index('--rev') + 1]

	upstream, base = show(REV), show(BASE)
	up_members, base_members = members(upstream), members(base)

	changed = {name: texts for name, texts in up_members.items() if base_members.get(name) != texts}
	print(f'upstream ({REV}) changed {len(changed)} members of Gauge.py, relative to {BASE}\n')

	# every member this branch has, wherever it now lives
	here = {}
	for rel in MODULE_PATHS:
		for name, texts in members(read_module(rel)).items():
			here.setdefault(name, (rel, texts))

	missing, ports = [], []
	for name, texts in sorted(changed.items()):
		if name not in here:
			missing.append((name, texts))
			continue
		rel, mine = here[name]
		diff = list(difflib.unified_diff(''.join(texts).splitlines(), ''.join(mine).splitlines(), lineterm='', n=1))
		count = len([line for line in diff if line.startswith('@@')])
		if count:
			ports.append((name, rel, count, diff))

	print(f'=== {len(ports)} member(s) still differ from upstream ===')
	for name, rel, count, diff in ports:
		print(f'  {name:<44} {rel:<20} {count} hunk(s)')
		if full:
			for line in diff[2:]:
				print('      ' + line)
	if missing:
		print(f'\n=== {len(missing)} member(s) upstream has and this branch has nowhere ===')
		for name, texts in missing:
			print(f'  {name:<44} {sum(len(t.splitlines()) for t in texts)} lines upstream')
	if not ports and not missing:
		print('\nnothing left to port')

	up_bases, base_bases = classes_and_bases(upstream), classes_and_bases(base)
	here_bases = {}
	for rel in MODULE_PATHS:
		here_bases.update(classes_and_bases(read_module(rel)))
	unported = {name: bases for name, bases in up_bases.items()
	            if base_bases.get(name) != bases and here_bases.get(name) != bases}
	print(f'\n=== class bases upstream changed: {len(unported)} not carried over ===')
	for name, bases in sorted(unported.items()):
		print(f'  {name:<30} upstream {bases}  here {here_bases.get(name)}')
	return 0


if __name__ == '__main__':
	sys.exit(main(sys.argv[1:]))
