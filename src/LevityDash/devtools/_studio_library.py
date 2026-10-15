"""Dev-only: the Studio's library: every preset, example and dashboard the repository ships, and the user's own,
in one list, each with the mode that opens it.

Qt-free so it can be tested without a window. `entries()` returns the list; `classify` says which editor a `.levity`
file belongs in (`dashboard`, `gauge` or `polar`).

Groups, in order:
- Dashboards: the design dashboards and the example-config templates.
- Presets: the shipped presets and the user's (`<studio dir>/presets`), by name, the way the builder's Open menu has them.
- Gauges: the gauge examples (one file each) and the cells of the gauge showcase.
- Polar plots.
- Panels and fragments: everything else in `docs/design-references` (bars, panels, the other showcases).
- Your dashboards: the real config folder's `.levity` files, to open and look at. Save never writes there.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator, List, Optional, Tuple

import yaml

REPO = Path(__file__).resolve().parents[3]
REFERENCES = REPO / 'docs' / 'design-references'
TEMPLATES = REPO / 'src' / 'LevityDash' / 'resources' / 'example-config' / 'templates'

DASHBOARD, GAUGE, POLAR, PRESET, CELL = 'dashboard', 'gauge', 'polar', 'preset', 'cell'
GROUPS = ('Dashboards', 'Presets', 'Gauges', 'Bars', 'Polar plots', 'Panels and fragments', 'Your dashboards')

_CONTAINERS = {'group', 'stack', 'value-stack', 'grid', 'titled-group', 'switch', 'graph', 'mini-graph', 'clock'}


@dataclass(frozen=True)
class Entry:
	group: str
	label: str
	kind: str  # DASHBOARD, GAUGE, POLAR, PRESET (by name) or CELL (a gauge out of the showcase)
	path: Optional[Path] = None
	name: Optional[str] = None
	payload: Optional[dict] = None
	note: str = ''

	@property
	def search(self) -> str:
		return f'{self.group} {self.label} {self.note}'.lower()


def _types(node: Any) -> Iterator[str]:
	if isinstance(node, dict):
		if isinstance(node.get('type'), str):
			yield node['type']
		for value in node.values():
			yield from _types(value)
	elif isinstance(node, list):
		for value in node:
			yield from _types(value)


def classify(path: Path) -> str:
	"""The editor a `.levity` or `.yaml` file belongs in. A file that is not understood is a dashboard."""
	try:
		data = yaml.safe_load(Path(path).read_text(encoding='utf-8'))
	except (OSError, yaml.YAMLError):
		return DASHBOARD
	if isinstance(data, dict) and 'template' in data:
		return PRESET
	types = set(_types(data))
	if 'polar' in types:
		return POLAR
	if types & {'realtime.gauge', 'realtime.bar'} and not types & _CONTAINERS:
		return GAUGE
	return DASHBOARD


def _label(path: Path) -> str:
	return path.stem.replace('-', ' ').replace('_', ' ')


def _files(folder: Path, *patterns: str) -> List[Path]:
	if not folder.is_dir():
		return []
	return sorted({p for pattern in patterns for p in folder.glob(pattern) if p.is_file()})


def realConfigRoots() -> List[Path]:
	"""Where the real LevityDash keeps its config. Read only here: the Studio never writes into these."""
	roots: List[Path] = []
	try:
		from appdirs import AppDirs
		dirs = AppDirs(appname='LevityDash', appauthor='LevityDash.app')
		roots += [Path(dirs.user_config_dir), Path(dirs.user_data_dir)]
	except ImportError:
		pass
	home = Path.home()
	roots += [home / 'Library' / 'Application Support' / 'LevityDash', home / '.config' / 'LevityDash']
	seen: List[Path] = []
	for root in roots:
		if root.is_dir() and root not in seen:
			seen.append(root)
	return seen


def entries(
	presetNames: Optional[Callable[[], List[str]]] = None,
	cells: Optional[Callable[[], List[Tuple[str, dict]]]] = None,
	realRoots: Optional[List[Path]] = None,
	references: Path = REFERENCES,
) -> List[Entry]:
	"""Everything the library lists. `presetNames` and `cells` are injected so the caller owns the preset search path and
	the showcase reader."""
	found: List[Entry] = []
	for path in _files(references / 'dashboards', '*.levity'):
		found.append(Entry('Dashboards', _label(path), DASHBOARD, path, note='design dashboard'))
	for path in _files(TEMPLATES, '**/*.levity'):
		found.append(Entry('Dashboards', _label(path), DASHBOARD, path, note='template'))
	for name in (presetNames() if presetNames else []):
		found.append(Entry('Presets', name.replace('-', ' '), PRESET, name=name, note=name))
	taken = set()
	for path in _files(references / 'presets', '*.levity'):
		kind = classify(path)
		if kind == POLAR:
			found.append(Entry('Polar plots', _label(path), POLAR, path))
		elif kind == GAUGE:
			found.append(Entry('Gauges', _label(path), GAUGE, path, note='example'))
		else:
			found.append(Entry('Panels and fragments', _label(path), DASHBOARD, path, note='example'))
		taken.add(path)
	for label, entry in (cells() if cells else []):
		found.append(Entry('Gauges', label, CELL, payload=entry, note='showcase'))
	for path in _files(references, '*.levity') + _files(references / 'bars', '*.levity'):
		if path.parent.name == 'bars' and classify(path) == GAUGE:
			found.append(Entry('Bars', _label(path), GAUGE, path, note='example'))  # one bar: the gauge editor edits it
		else:
			found.append(Entry('Panels and fragments', _label(path), DASHBOARD, path, note=path.parent.name))
	for root in (realConfigRoots() if realRoots is None else realRoots):
		for path in _files(root, '**/*.levity'):
			found.append(Entry('Your dashboards', _label(path), DASHBOARD, path, note=str(path.parent.name)))
	order = {name: i for i, name in enumerate(GROUPS)}
	return sorted(found, key=lambda e: order[e.group])  # stable: files stay in the order they were read
