"""Gauge Studio offscreen smoke: the showcase cells, keyed items, the slider.

Offscreen, no app boot. The checks fail for different reasons:

0. which of the 30 showcase cells load — each through `loadDisplay` + `settle`,
   the rebuild path a numeric field used to decode against a `None` class;
1. the slider -> `StudioGauge.setValue` -> `gauge.value` -> pixels path;
2. a fill that names a key (`to: environment.temperature.high`) and the
   `sun-path` preset: both ask `openValueSource`, which the studio answers from
   made-up data through the stand-in registered in `lib/valuesource` (see
   `docs/tasks/studio-value-sources.md`);
3. every consumer module reads the one `lib/valuesource.openValueSource`, so the
   stand-in reaches them wherever they live.

    QT_QPA_PLATFORM=offscreen .venv/bin/python src/LevityDash/devtools/render_diff_tools/studio_smoke2.py
"""
import copy
import hashlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
DEVTOOLS = HERE.parent.parent
REPO = DEVTOOLS.parents[2]
sys.path.insert(0, str(DEVTOOLS))
import _studio_env  # noqa: E402

_studio_env.prepare()
sys.path.insert(0, str(REPO / 'src'))

import yaml  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from LevityDash.devtools import gauge_studio as gs  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)


def pump(n=5):
	for _ in range(n):
		app.processEvents()


def pixels() -> str:
	image = studio.studio.render()
	return hashlib.sha256(bytes(image.constBits())).hexdigest()[:12]


studio = gs.Studio()
studio.show()
pump()

print('=== 0. which showcase cells load? ===')
cells = gs.showcaseCells()
loaded, failed = [], []
for index, (label, entry) in enumerate(cells):
	try:
		studio.loadDisplay(copy.deepcopy(entry.get('display') or {}), entry.get('key'), label)
		pump()
		studio.settle()
		pump()
		if studio.studio.gauge is None:
			raise RuntimeError('no gauge after load')
		loaded.append((index, label))
	except Exception as e:  # noqa: BLE001
		failed.append((index, label, type(e).__name__, str(e)[:80]))
for index, label, kind, message in failed:
	print(f'  cell {index} "{label}" failed: {kind}: {message}')
print(f'  {len(loaded)}/{len(cells)} cells load')
if not loaded:
	raise SystemExit('no showcase cell loaded; cannot test the slider')

index, label = loaded[0]
entry = cells[index][1]
print(f'\n=== 1. does the preview follow the slider? (cell {index} "{label}") ===')
rows = []
for position in (0, 250, 500, 750, 1000):
	studio.valueSlider.setValue(position)
	pump()
	studio.settle()
	pump()
	# Re-read the gauge each step: settle() rebuilds it, so a held reference goes stale.
	rows.append((position, float(studio.studio.gauge.value), pixels()))
	print(f'  slider {position:>4}  gauge.value={rows[-1][1]:>8.2f}  pixels={rows[-1][2]}')
values = [value for _, value, _ in rows]
hashes = [hash_ for _, _, hash_ in rows]
print(f'  value tracks slider : {len(set(values)) == len(values)}')
print(f'  pixels track value  : {len(set(hashes)) == len(hashes)}')

print('\n=== 2. items that name a key ===')
studio.loadDisplay({'arc': {'weight': '5%'}, 'fill': {'to': 'environment.temperature.high'}},
                   'environment.temperature.temperature', 'fill-test')
pump()
studio.settle()
pump()
fill = getattr(studio.studio.gauge, '_fillItem', None)
print(f'  keyed fill built   : {fill is not None}')
print(f'  keyed fill visible : {None if fill is None else fill.isVisibleTo(None)}')

preset_path = REPO / 'docs' / 'design-references' / 'presets' / 'sun-path.levity'
dashboard = yaml.safe_load(preset_path.read_text())
cell = dashboard[0]
try:
	studio.loadDisplay(copy.deepcopy(cell.get('display') or {}), cell.get('key'), 'sun-path')
	pump()
	studio.settle()
	pump()
	fill = getattr(studio.studio.gauge, '_fillItem', None)
	print(f'  sun-path fill built: {fill is not None}')
	print(f'  sun-path fill visible: {None if fill is None else fill.isVisibleTo(None)}')
except Exception as e:  # noqa: BLE001
	print(f'  loading sun-path failed: {type(e).__name__}: {str(e)[:120]}')

print('\n=== 3. one lookup: every consumer reads lib/valuesource.openValueSource ===')
from LevityDash.lib import valuesource  # noqa: E402
for name, module in (
	('Gauge.py', 'LevityDash.lib.ui.frontends.PySide.Modules.Displays.Gauge'),
	('meter/elements.py', 'LevityDash.lib.ui.frontends.PySide.Modules.Displays.meter.elements'),
	('meter/bar.py', 'LevityDash.lib.ui.frontends.PySide.Modules.Displays.meter.bar'),
	('Graph.py', 'LevityDash.lib.ui.frontends.PySide.Modules.Displays.Graph'),
	('condition.py', 'LevityDash.lib.ui.frontends.PySide.Modules.condition'),
	('beam/item.py', 'LevityDash.lib.ui.frontends.PySide.Modules.beam.item'),
):
	found = getattr(__import__(module, fromlist=['openValueSource']), 'openValueSource', None)
	print(f'  {name:<20} -> {"the one lookup" if found is valuesource.openValueSource else "NOT the one lookup"}')
print(f'  stand-in installed: {valuesource._standIn is not None}')
