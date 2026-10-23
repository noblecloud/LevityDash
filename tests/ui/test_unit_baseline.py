"""`unitPosition: baseline` draws the unit as a smaller run after the value, on its baseline, inside the value's own text."""
import pytest

import LevityDash
from WeatherUnits import Length, Temperature
from WeatherUnits.derived import Wind
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Realtime import MeasurementDisplayProperties
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Label import Label
from LevityDash.lib.ui.Geometry import DisplayPosition
from tests.conftest import pump

BOARD = '''
- type: group
  name: panel
  geometry: {x: 0%, y: 0%, width: 100%, height: 100%}
  items:
    - {type: text, text: "12.5", alignment: Left, geometry: {x: 0%, y: 0%, width: 100%, height: 100%}}
'''


def test_a_word_unit_is_the_tail_and_a_mark_is_not():
	unitTail = MeasurementDisplayProperties.unitTail
	assert unitTail(Length.Mile(7)).strip('. ') in ('mi', 'mile', 'miles')
	assert unitTail(Temperature.Fahrenheit(98)) == ''  # a degree sign stays in the value's run
	assert unitTail(None) == ''
	assert unitTail(7) == ''


def test_baseline_is_a_unit_position():
	assert DisplayPosition['Baseline'] is DisplayPosition.Baseline
	assert DisplayPosition('baseline') is DisplayPosition.Baseline


@pytest.fixture
def labelBox(dashboard, tmp_path):
	panel = LevityDash.LevityDashboard.CENTRAL_PANEL
	target = tmp_path / 'unit-baseline.levity'
	target.write_text(BOARD)
	was = panel.filePath
	panel._load(target)
	pump(dashboard.app, 1.5)
	label = next(i for i in dashboard.scene.items() if isinstance(i, Label) and getattr(i.textBox, 'text', None) == '12.5')
	yield label.textBox
	if was is not None:
		panel._load(was)
		pump(dashboard.app, 1.5)


def test_a_tail_is_drawn_after_the_text_on_its_baseline_and_widens_the_fit(labelBox):
	box = labelBox
	box.updateTransform(updatePath=True, updateShared=False, reason='test')
	bare = box.path().boundingRect()
	bareRect = box._textRect
	box.tailRun = lambda: ('mph', 0.45)
	box.updateTransform(updatePath=True, updateShared=False, reason='test')
	tailed = box.path().boundingRect()
	assert tailed.width() > bare.width() * 1.2, 'the unit adds to the drawn text'
	assert abs(tailed.bottom() - bare.bottom()) < bare.height() * 0.2 + 1, 'the tail shares the value baseline, it does not drop below'
	assert box._textRect.width() > bareRect.width(), 'and to the width the fit and the size group see'
