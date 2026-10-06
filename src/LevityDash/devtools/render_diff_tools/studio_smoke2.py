"""Does Gauge Studio's preview follow its value slider, and do named sources resolve?

Offscreen. Three checks, because they fail for different reasons:

1. slider -> `StudioGauge.setValue` -> `gauge.value` -> pixels;
2. a fill/marker that names a key (`to: astronomy.sun.hour`) — that path asks
   `openValueSource`, which `installSources()` is supposed to swap for the studio's
   made-up data. It swaps it on `Displays.Gauge`, which the star import in
   `Displays/__init__.py` binds to the *class*, not the module — and since the
   meter split the consumers live in `meter/elements.py` as well.
3. the same question asked directly of the module that consumes it.

    QT_QPA_PLATFORM=offscreen .venv/bin/python src/LevityDash/devtools/render_diff_tools/studio_smoke2.py
"""
import copy
import hashlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
DEVTOOLS = HERE.parent.parent
sys.path.insert(0, str(DEVTOOLS))
import _studio_env  # noqa: E402

_studio_env.prepare()
sys.path.insert(0, str(DEVTOOLS.parent.parent))

import yaml  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from LevityDash.devtools import gauge_studio as gs  # noqa: E402
from LevityDash.devtools import _studio_stage  # noqa: E402

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

print('=== 0. which showcase cell loads? ===')
loaded = None
for index, (label, entry) in enumerate(gs.showcaseCells()):
	try:
		studio.loadDisplay(copy.deepcopy(entry.get('display') or {}), entry.get('key'), label)
		pump()
		studio.settle()
		pump()
		if studio.studio.gauge is not None:
			loaded = (index, label, entry)
			print(f'  cell {index} "{label}" loads')
			break
	except Exception as e:  # noqa: BLE001
		print(f'  cell {index} "{label}" failed: {type(e).__name__}: {str(e)[:70]}')
if loaded is None:
	raise SystemExit('no showcase cell loaded; cannot test')

index, label, entry = loaded
gauge = studio.studio.gauge
print(f'\n=== 1. does the preview follow the slider? (cell {index}, key {entry.get("key")}) ===')
rows = []
for position in (0, 250, 500, 750, 1000):
	studio.valueSlider.setValue(position)
	pump()
	studio.settle()
	pump()
	rows.append((position, float(gauge.value), pixels()))
	print(f'  slider {position:>4}  gauge.value={rows[-1][1]:>8.2f}  pixels={rows[-1][2]}')
values = [v for _, v, _ in rows]
hashes = [h for _, _, h in rows]
print(f'  value tracks slider : {len(set(values)) == len(values)}')
print(f'  pixels track value  : {len(set(hashes)) == len(hashes)}')

print('\n=== 2. a fill that names a key, in the studio ===')
preset_path = Path(DEVTOOLS.parent.parent) / 'docs' / 'design-references' / 'presets' / 'sun-path.levity'
dashboard = yaml.safe_load(preset_path.read_text())
cell = dashboard['items'][0]
display = copy.deepcopy(cell.get('display') or {})
print(f'  preset display: {display}')
try:
	studio.loadDisplay(display, cell.get('key'), 'sun-path')
	pump()
	studio.settle()
	pump()
	gauge = studio.studio.gauge
	fill = getattr(gauge, '_fillItem', None)
	print(f'  fill item built   : {fill is not None}')
	print(f'  fill visible      : {None if fill is None else fill.isVisibleTo(None)}')
except Exception as e:  # noqa: BLE001
	print(f'  loading sun-path failed: {type(e).__name__}: {str(e)[:120]}')

print('\n=== 3. which openValueSource does each module see? ===')
studio_source = getattr(_studio_stage, '_openValueSource', None)
print(f'  the studio\'s own source object: {studio_source!r}')
for name, module in (
	('Displays (the star import)', __import__('LevityDash.lib.ui.frontends.PySide.Modules.Displays', fromlist=['Gauge'])),
	('Gauge.py', __import__('LevityDash.lib.ui.frontends.PySide.Modules.Displays.Gauge', fromlist=['openValueSource'])),
	('meter/elements.py', __import__('LevityDash.lib.ui.frontends.PySide.Modules.Displays.meter.elements', fromlist=['openValueSource'])),
):
	attr = getattr(module, 'Gauge', None) if name == 'Displays (the star import)' else None
	if name == 'Displays (the star import)':
		patched = getattr(attr, 'openValueSource', None)
		print(f'  {name:<28} `Gauge` is a {type(attr).__name__}; its openValueSource = {patched!r}'
		      f' -> {"the studio one" if patched is studio_source else "NOT the studio one"}')
	else:
		patched = getattr(module, 'openValueSource', None)
		print(f'  {name:<28} openValueSource = {patched!r}'
		      f' -> {"the studio one" if patched is studio_source else "NOT the studio one"}')
