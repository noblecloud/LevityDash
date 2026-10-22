"""WeatherUnits is now unitcorn: nothing may import the old name.

LevityDash installs unitcorn itself, not the WeatherUnits forwarding shim, so an
`import WeatherUnits` left over from a branch that predates the rename fails
only when that module is first imported. This finds it at once instead.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD_IMPORT = re.compile(r'^\s*(?:from|import)\s+WeatherUnits\b', re.M)


def test_no_module_imports_weatherunits():
	offenders = [
		f'{path.relative_to(ROOT)}:{source[:match.start()].count(chr(10)) + 1}'
		for folder in ('src', 'tests', 'build-to-app')
		for path in sorted((ROOT / folder).rglob('*.py'))
		for source in [path.read_text(encoding='utf-8', errors='replace')]
		for match in OLD_IMPORT.finditer(source)
	]
	assert not offenders, 'import unitcorn (as wu), not WeatherUnits:\n' + '\n'.join(offenders)
