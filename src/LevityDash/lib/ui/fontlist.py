"""The short list of font families that pickers offer.

Pickers do not list every installed family. They list the families bundled with
LevityDash, the families in the user fonts folder, a short set of common
families, and any names in `[Fonts] extra` of the config file. Only installed
families appear. A picker still accepts any name typed into it.

This module imports no Qt, so tests and tools can use it freely.
"""

import re
from pathlib import Path
from typing import Iterable

__all__ = ['COMMON_FAMILIES', 'GENERIC_FAMILIES', 'genericFamily', 'curatedFamilies', 'folderFamilies', 'parseExtra']

_FOUNDRY = re.compile(r'\s*\[[^\]]*\]$')  # Qt names some families 'Roboto Mono [GOOG]'

COMMON_FAMILIES: tuple[str, ...] = (
	# cross-platform sans and mono
	'Inter', 'Open Sans', 'Lato', 'Noto Sans', 'Fira Sans', 'Source Sans 3', 'Source Sans Pro',
	'Fira Code', 'JetBrains Mono', 'Source Code Pro', 'DejaVu Sans', 'DejaVu Sans Mono', 'Liberation Sans',
	# macOS
	'Helvetica', 'Helvetica Neue', 'Avenir', 'Avenir Next', 'Futura', 'Gill Sans', 'Menlo', 'Monaco', 'SF Pro', 'SF Mono',
	# Windows
	'Arial', 'Segoe UI', 'Verdana', 'Trebuchet MS', 'Tahoma', 'Consolas', 'Courier New', 'Impact',
	# serif
	'Georgia', 'Times New Roman', 'Palatino', 'Noto Serif', 'Merriweather',
	# linux
	'Ubuntu', 'Cantarell',
)

# Generic names and the bundled family each one stands for. No serif is bundled, so 'serif' falls back to the default font.
GENERIC_FAMILIES: dict[str, str] = {
	'monospace':  'Roboto Mono',
	'mono':       'Roboto Mono',
	'sans-serif': 'Roboto',
	'sans':       'Roboto',
}


def genericFamily(name: str) -> str | None:
	"""The bundled family for a generic name such as 'Monospace', or None when `name` is not generic."""
	return GENERIC_FAMILIES.get(name.strip().lower())


def parseExtra(value: str | None) -> list[str]:
	"""`'Fira Code, Comic Sans MS'` -> `['Fira Code', 'Comic Sans MS']`. Names are separated by commas or new lines."""
	if not value:
		return []
	return [name.strip().strip('\'"') for name in value.replace('\n', ',').split(',') if name.strip().strip('\'"')]


def folderFamilies(*roots: Path) -> list[str]:
	"""Family names guessed from the folder names under each root. The font loader gives the exact names; this is a cheap guess."""
	names: list[str] = []
	for root in roots:
		try:
			names.extend(sorted(p.name for p in Path(root).iterdir() if p.is_dir()))
		except OSError:
			continue
	return names


def curatedFamilies(installed: Iterable[str], bundled: Iterable[str] = (), extra: Iterable[str] = ()) -> list[str]:
	"""The picker list: bundled and extra families first, then the common ones, each only if installed.

	Matching ignores case and a foundry tag such as `[GOOG]`. A family in `extra` that is not installed is dropped.
	The result has no repeats and keeps the order bundled, extra, common.
	"""
	available: dict[str, str] = {}
	for name in installed:
		bare = _FOUNDRY.sub('', name)
		available.setdefault(bare.lower(), bare)
	result: list[str] = []
	seen: set[str] = set()
	for name in (*bundled, *extra, *COMMON_FAMILIES):
		key = name.lower()
		if key in available and key not in seen:
			seen.add(key)
			result.append(available[key])
	return result
