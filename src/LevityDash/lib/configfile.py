"""Reading, writing and migrating the TOML config files. Qt-free, no LevityDash imports.

The settings stay shaped like the INI files they replace: sections of ``key = value`` where every value
is a string once loaded (``LevityConfig`` still answers ``getboolean``/``getint``/``getfloat`` from it).
What changes is the file on disk: ``config.toml``, ``plugins/plugins.toml``, ``plugins/<Name>.toml``.

Mapping between the two:

- TOML booleans and numbers load as ``True``/``False`` and their ``str()``; arrays as ``a, b, c``.
- A nested table loads as dotted keys (``[Fonts.default] weight = "Medium"`` is ``default.weight``),
  except under ``[UnitProperties]``, where ``mmHg = { precision = 2, digit_budget = 4 }`` is the
  ``precision=2, digit_budget=4`` line unitcorn reads.
- On write a value goes out as a TOML number or boolean only when that reads back as the same text,
  otherwise as a string, so nothing changes shape on a round trip.
"""
import json
import re
import tomllib
from configparser import ConfigParser
from logging import getLogger
from pathlib import Path
from shutil import copy2
from typing import Any, Iterable, Mapping, Optional

log = getLogger('LevityConfig')

#: Sections whose values are ``name=value, name=value`` lines, written as inline tables.
PAIR_SECTIONS = frozenset({'UnitProperties'})

_BARE_KEY = re.compile(r'[A-Za-z0-9_-]+')
_INT = re.compile(r'-?(0|[1-9][0-9]*)')
_FLOAT = re.compile(r'-?(0|[1-9][0-9]*)\.[0-9]+')


def _text(value: Any) -> str:
	return str(value)


def _flatten(prefix: str, value: Any, out: dict[str, str]) -> None:
	if isinstance(value, Mapping):
		for key, sub in value.items():
			_flatten(f'{prefix}.{key}' if prefix else str(key), sub, out)
	elif isinstance(value, (list, tuple)):
		out[prefix] = ', '.join(_text(v) for v in value)
	else:
		out[prefix] = _text(value)


def fromToml(data: Mapping[str, Any], source: str = '<toml>') -> dict[str, dict[str, str]]:
	"""Parsed TOML as ``{section: {key: str}}``. A top-level value that is not a table is an error."""
	sections: dict[str, dict[str, str]] = {}
	for name, section in data.items():
		if not isinstance(section, Mapping):
			raise ValueError(f'{source}: top-level key {name!r} must be a [section]')
		converted: dict[str, str] = {}
		for key, value in section.items():
			if name in PAIR_SECTIONS and isinstance(value, Mapping):
				converted[key] = ', '.join(f'{prop}={_text(propValue)}' for prop, propValue in value.items())
			else:
				_flatten(str(key), value, converted)
		sections[name] = converted
	return sections


def readToml(path: Path | str) -> dict[str, dict[str, str]]:
	path = Path(path)
	with path.open('rb') as file:
		return fromToml(tomllib.load(file), source=str(path))


# --------------------------------------------------------------------------- writing

def _key(name: str) -> str:
	return name if _BARE_KEY.fullmatch(name) else json.dumps(name, ensure_ascii=False)


def _scalar(raw: Optional[str]) -> str:
	"""One value as TOML: a bool or number when it reads back identical, otherwise a string."""
	if raw is None:
		return '""'
	raw = str(raw)
	if raw in ('True', 'False'):
		return raw.lower()
	if _INT.fullmatch(raw) and str(int(raw)) == raw:
		return raw
	if _FLOAT.fullmatch(raw) and str(float(raw)) == raw:
		return raw
	return json.dumps(raw, ensure_ascii=False)


def _pairs(raw: str) -> Optional[str]:
	"""``a=1, b=2`` as an inline table, or None when it is not that shape."""
	parts = [part.strip() for part in raw.split(',') if part.strip()]
	if not parts or any(part.count('=') != 1 for part in parts):
		return None
	table = []
	for part in parts:
		name, _, value = part.partition('=')
		if not name.strip():
			return None
		table.append(f'{_key(name.strip())} = {_scalar(value.strip())}')
	return '{ ' + ', '.join(table) + ' }'


def dumpToml(sections: Iterable[tuple[str, Mapping[str, Optional[str]]]]) -> str:
	"""``(name, values)`` pairs as TOML text, in order. An empty section is still written, so it survives."""
	lines: list[str] = []
	for name, values in sections:
		lines.append(f'[{_key(name)}]')
		for key, raw in values.items():
			if name in PAIR_SECTIONS and raw and (table := _pairs(str(raw))) is not None:
				lines.append(f'{_key(key)} = {table}')
			else:
				lines.append(f'{_key(key)} = {_scalar(raw)}')
		lines.append('')
	return '\n'.join(lines)


# --------------------------------------------------------------------------- migration

def parseIni(path: Path | str) -> dict[str, dict[str, Optional[str]]]:
	"""An INI file as raw ``{section: {key: str}}``: no interpolation, case kept, ``[DEFAULT]`` just a section."""
	parser = ConfigParser(interpolation=None, allow_no_value=True, strict=False, default_section='\0 none')
	parser.optionxform = str
	parser.read(path, encoding='utf-8')
	return {name: dict(parser[name]) for name in parser.sections()}


def backupFor(ini: Path) -> Path:
	"""``config.ini`` -> ``config.ini.bak``; ``.bak-2``, ``.bak-3`` ... when that is taken."""
	target = ini.with_name(ini.name + '.bak')
	n = 2
	while target.exists():
		target = ini.with_name(f'{ini.name}.bak-{n}')
		n += 1
	return target


def migrateIni(ini: Path) -> Optional[Path]:
	"""Write ``<name>.toml`` beside ``<name>.ini`` and move the INI to a ``.bak``. Returns the TOML path.

	Does nothing, and returns None, when the TOML exists already (it wins; the INI is left alone) or the
	INI cannot be read or the TOML cannot be written. The INI then stays where it is and keeps being read.
	"""
	toml = ini.with_suffix('.toml')
	if toml.exists() or not ini.is_file():
		return None
	try:
		text = dumpToml(parseIni(ini).items())
		tomllib.loads(text)  # never replace a file with one we cannot read back
		toml.write_text(text, encoding='utf-8')
		backup = backupFor(ini)
		copy2(ini, backup)
		ini.unlink()
	except Exception as e:  # noqa: BLE001 - the INI keeps working as the fallback
		log.error(f'Could not migrate {ini} to TOML ({e}); keeping the INI file')
		try:
			if toml.exists() and ini.exists():
				toml.unlink()
		except OSError:
			pass
		return None
	log.warning(f'Migrated {ini.name} to {toml.name}; the old file is kept as {backup.name}')
	return toml


def legacyIniFiles(root: Path) -> list[Path]:
	"""Every INI file the app used to read under a config directory."""
	found = []
	if (main := root / 'config.ini').is_file():
		found.append(main)
	plugins = root / 'plugins'
	if plugins.is_dir():
		found.extend(sorted(p for p in plugins.glob('*.ini') if p.is_file()))
		found.extend(sorted(p for p in plugins.glob('*/config.ini') if p.is_file()))
	return found


def migrateConfigDir(root: Path | str) -> list[Path]:
	"""Migrate each INI file in a config directory. Returns the TOML files written."""
	return [t for ini in legacyIniFiles(Path(root)) if (t := migrateIni(ini)) is not None]
