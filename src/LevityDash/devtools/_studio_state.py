"""Dev-only: Studio's per-user state and the section styles.

State lives in a folder of its own: `QStandardPaths.AppDataLocation` for "LevityDash Studio"
(`~/Library/Application Support/LevityDash Studio` on macOS). The folder was called "Gauge Studio" until the
Studio became the dashboard editor; the first run moves it (`_moveOldFolder`), so saved pins and styles stay. It holds `studio.ini` (pins and
section fold state) and `styles/<section>.yaml` (styles the user saved). Nothing here
reads or writes the LevityDash config or the repository. `LEVITYDASH_STUDIO_DIR` moves the
folder, which is how a test keeps off the real one.

A built-in style is a data file, `studio_styles/<section>.yaml`: a mapping from style
name to the `display:` keys it sets. Adding a style is a data edit.
"""
import copy
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, NamedTuple

import yaml
from PySide6.QtCore import QCoreApplication, QSettings, QStandardPaths

BUILTIN_DIR = Path(__file__).resolve().parent / 'studio_styles'

#: The top sections. `paths` are the rows (dotted property paths); `owns` are the top-level
#: `display:` keys a style of the section may set and "Save current as style" records.
#: `labels` names a row whose last key alone would be ambiguous here, such as three rows that
#: would all read "enabled". `subsections` adds folded child sections, each holding a part of the
#: gauge (every property under that path) or a single property.
QUICK: Dict[str, Dict[str, Any]] = {
	'Shape': {
		'paths': ('arc.start-angle', 'arc.end-angle', 'radius', 'arc.weight', 'arc.color', 'arc.cap', 'anchor'),
		'owns': ('arc', 'radius', 'anchor', 'inset'),
		'labels': {'arc.color': 'arc color', 'arc.cap': 'arc cap'},
	},
	'Needle': {
		'paths': ('needle.visible', 'needle.type', 'needle.color', 'needle.length', 'needle.width', 'needle.point'),
		'owns': ('needle',),
		'labels': {'needle.visible': 'show needle'},
	},
	'Value': {
		'paths': ('value-label.visible', 'value-label.position', 'value-label.size', 'value-label.format', 'unit-label.visible'),
		'owns': ('value-label', 'unit-label'),
		'labels': {'value-label.visible': 'show value', 'unit-label.visible': 'show unit'},
	},
	'Text': {
		'paths': (),
		# Each entry is one folded subsection: a part (every property under it) or one property.
		'subsections': {'Value label': 'value-label', 'Unit label': 'unit-label', 'Caption': 'caption',
		                'Sub-label': 'sub-label', 'Major tick labels': 'major.labels',
		                'Minor tick labels': 'minor.labels', 'Micro tick labels': 'micro.labels'},
		'owns': ('value-label', 'unit-label', 'caption', 'sub-label'),
	},
	'Ticks': {
		'paths': ('major.enabled', 'minor.enabled', 'micro.enabled', 'major.labels.height', 'major.labels.position',
		          'major.labels.curve', 'major.color'),
		'owns': ('major', 'minor', 'micro'),
		'labels': {'major.enabled': 'major ticks', 'minor.enabled': 'minor ticks', 'micro.enabled': 'micro ticks',
		           'major.labels.height': 'label size', 'major.labels.position': 'label position',
		           'major.labels.curve': 'label curve', 'major.color': 'major color'},
	},
	'Extras': {
		'paths': ('fill', 'zones', 'markers', 'caption', 'sub-label', 'value-label.warp'),
		'owns': ('fill', 'zones', 'markers', 'caption', 'sub-label'),
		'labels': {'value-label.warp': 'value warp'},
	},
}


class Style(NamedTuple):
	name: str
	data: dict
	replace: bool  # a saved snapshot replaces the section's keys; a built-in one merges into them
	user: bool


NAME = 'LevityDash Studio'
OLD_NAME = 'Gauge Studio'


def _moveOldFolder(new: Path) -> Path:
	"""Move the folder the Studio had before it was renamed, once: only if the new one does not exist yet."""
	old = new.parent / OLD_NAME
	if not new.exists() and old.is_dir():
		try:
			shutil.move(str(old), str(new))
		except OSError:
			return new
	return new


def stateDir() -> Path:
	env = os.environ.get('LEVITYDASH_STUDIO_DIR')
	if env:
		return Path(env)
	if QCoreApplication.applicationName() == NAME:
		new = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))
	else:
		new = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericDataLocation)) / NAME
	return _moveOldFolder(new)


def settings() -> QSettings:
	folder = stateDir()
	folder.mkdir(parents=True, exist_ok=True)
	return QSettings(str(folder / 'studio.ini'), QSettings.Format.IniFormat)


def _load(path: Path) -> dict:
	try:
		data = yaml.safe_load(path.read_text())
	except (OSError, yaml.YAMLError):
		return {}
	return data if isinstance(data, dict) else {}


def styles(title: str) -> List[Style]:
	found = [Style(str(name), frag or {}, False, False) for name, frag in _load(BUILTIN_DIR / f'{title.lower()}.yaml').items()]
	for name, entry in _load(stateDir() / 'styles' / f'{title.lower()}.yaml').items():
		if isinstance(entry, dict) and isinstance(entry.get('display'), dict):
			found.append(Style(str(name), entry['display'], bool(entry.get('replace', True)), True))
	return found


def snapshot(title: str, display: dict) -> dict:
	"""The section's keys as `display` holds them now. A key at its default is `None`."""
	return {key: copy.deepcopy(display.get(key)) for key in QUICK[title]['owns']}


def saveUser(title: str, name: str, display: dict) -> None:
	"""Record the section's current look under `name`, replacing a style of that name."""
	path = stateDir() / 'styles' / f'{title.lower()}.yaml'
	path.parent.mkdir(parents=True, exist_ok=True)
	data = _load(path)
	data[name] = {'replace': True, 'display': snapshot(title, display)}
	path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))


def merge(base: dict, fragment: dict) -> dict:
	"""`base` with `fragment` deep-merged in. A `None` in the fragment removes the key (back to its default)."""
	out = copy.deepcopy(base)
	for key, value in fragment.items():
		if value is None:
			out.pop(key, None)
		elif isinstance(value, dict):
			out[key] = merge(out[key] if isinstance(out.get(key), dict) else {}, value)
		else:
			out[key] = copy.deepcopy(value)
	return out


def apply(display: dict, style: Style) -> dict:
	"""`display` with the style's keys set. Every key the style does not name stays as it is."""
	if not style.replace:
		return merge(display, style.data)
	out = copy.deepcopy(display)
	for key, value in style.data.items():
		if value is None:
			out.pop(key, None)
		else:
			out[key] = copy.deepcopy(value)
	return out
