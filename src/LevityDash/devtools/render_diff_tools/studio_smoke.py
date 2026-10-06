"""Does Gauge Studio's preview follow its value slider, and do named sources resolve?

Offscreen. Two checks, because they fail for different reasons:

1. the slider -> `StudioGauge.setValue` -> `gauge.value` -> pixels path;
2. a marker/fill that names a key (`value: environment.temperature.high`), which
   needs `openValueSource` to be the studio's lookup rather than the real plugin
   one. `installSources()` swaps that name on what it thinks is the Gauge module.

    QT_QPA_PLATFORM=offscreen .venv/bin/python src/LevityDash/devtools/render_diff_tools/studio_smoke.py
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
cells = gs.showcaseCells()
label, entry = cells[0]
studio.loadDisplay(copy.deepcopy(entry.get('display') or {}), entry.get('key'), label)
pump()
studio.settle()
pump()
gauge = studio.studio.gauge
print(f'cell: {label}   key: {entry.get("key")}   gauge: {type(gauge).__name__}')
print(f'range: {studio.studio.range}')

print('\n=== 1. does the preview follow the slider? ===')
rows = []
for position in (0, 250, 500, 750, 1000):
	studio.valueSlider.setValue(position)
	pump()
	studio.settle()
	pump()
	rows.append((position, float(gauge.value), pixels()))
	print(f'  slider {position:>4}  gauge.value={rows[-1][1]:>8.2f}  pixels={rows[-1][2]}')
values = [value for _, value, _ in rows]
hashes = [h for _, _, h in rows]
print(f'  value follows slider: {values == sorted(values) and len(set(values)) == len(values)}')
print(f'  pixels follow value : {len(set(hashes)) == len(hashes)}')

print('\n=== 2. does a marker that names a key resolve? ===')
display = copy.deepcopy(entry.get('display') or {})
display['markers'] = [{'value': 'environment.temperature.high', 'label': 'today high'}]
studio.loadDisplay(display, entry.get('key'), label)
pump()
studio.settle()
pump()
gauge = studio.studio.gauge
markers = getattr(gauge, '_markerItems', None)
print(f'  _markerItems: {markers!r}')
resolved = bool(markers)
print(f'  marker resolved: {resolved}')
if not resolved:
	import LevityDash.lib.ui.frontends.PySide.Modules.Displays.Gauge as gauge_module
	import LevityDash.lib.ui.frontends.PySide.Modules.Displays.meter.elements as elements_module
	import LevityDash.lib.ui.frontends.PySide.Modules.Displays as displays
	print(f'  Displays.Gauge is the class: {isinstance(displays.Gauge, type)}')
	print(f'  Gauge.py       openValueSource: {getattr(gauge_module, "openValueSource", None)}')
	print(f'  elements.py    openValueSource: {getattr(elements_module, "openValueSource", None)}')
