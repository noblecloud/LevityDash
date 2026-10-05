"""Dev-only: Gauge Studio's per-user state and the section presets.

State lives in a folder of its own: `QStandardPaths.AppDataLocation` for "Gauge Studio"
(`~/Library/Application Support/Gauge Studio` on macOS). It holds `studio.ini` (pins and
section fold state) and `presets/<section>.yaml` (presets the user saved). Nothing here
reads or writes the LevityDash config or the repository. `LEVITYDASH_STUDIO_DIR` moves the
folder, which is how a test keeps off the real one.

A built-in preset is a data file, `studio_presets/<section>.yaml`: a mapping from preset
name to the `display:` keys it sets. Adding a preset is a data edit.
"""
import copy
import os
from pathlib import Path
from typing import Any, Dict, List, NamedTuple

import yaml
from PySide6.QtCore import QCoreApplication, QSettings, QStandardPaths

BUILTIN_DIR = Path(__file__).resolve().parent / 'studio_presets'

#: The top sections. `paths` are the rows (dotted property paths); `owns` are the top-level
#: `display:` keys a preset of the section may set and "Save current as preset" records.
#: `labels` names a row whose last key alone would be ambiguous here, such as three rows that
#: would all read "enabled".
QUICK: Dict[str, Dict[str, Any]] = {
	'Shape': {
		'paths': ('arc.start-angle', 'arc.end-angle', 'radius', 'arc.weight', 'arc.color', 'arc.cap', 'anchor'),
		'owns': ('arc', 'radius', 'anchor', 'inset'),
		'labels': {'arc.color': 'arc color', 'arc.cap': 'arc cap'},
	},
	'Needle': {
		'paths': ('needle.visible', 'needle.color', 'needle.length', 'needle.width', 'needle.point'),
		'owns': ('needle',),
		'labels': {'needle.visible': 'show needle'},
	},
	'Value': {
		'paths': ('value-label.visible', 'value-label.position', 'value-label.size', 'value-label.format', 'unit-label.visible'),
		'owns': ('value-label', 'unit-label'),
		'labels': {'value-label.visible': 'show value', 'unit-label.visible': 'show unit'},
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


class Preset(NamedTuple):
	name: str
	data: dict
	replace: bool  # a saved snapshot replaces the section's keys; a built-in one merges into them
	user: bool


def stateDir() -> Path:
	env = os.environ.get('LEVITYDASH_STUDIO_DIR')
	if env:
		return Path(env)
	if QCoreApplication.applicationName() == 'Gauge Studio':
		return Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))
	return Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericDataLocation)) / 'Gauge Studio'


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


def presets(title: str) -> List[Preset]:
	found = [Preset(str(name), frag or {}, False, False) for name, frag in _load(BUILTIN_DIR / f'{title.lower()}.yaml').items()]
	for name, entry in _load(stateDir() / 'presets' / f'{title.lower()}.yaml').items():
		if isinstance(entry, dict) and isinstance(entry.get('display'), dict):
			found.append(Preset(str(name), entry['display'], bool(entry.get('replace', True)), True))
	return found


def snapshot(title: str, display: dict) -> dict:
	"""The section's keys as `display` holds them now. A key at its default is `None`."""
	return {key: copy.deepcopy(display.get(key)) for key in QUICK[title]['owns']}


def saveUser(title: str, name: str, display: dict) -> None:
	"""Record the section's current look under `name`, replacing a preset of that name."""
	path = stateDir() / 'presets' / f'{title.lower()}.yaml'
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


def apply(display: dict, preset: Preset) -> dict:
	"""`display` with the preset's keys set. Every key the preset does not name stays as it is."""
	if not preset.replace:
		return merge(display, preset.data)
	out = copy.deepcopy(display)
	for key, value in preset.data.items():
		if value is None:
			out.pop(key, None)
		else:
			out[key] = copy.deepcopy(value)
	return out
