"""`font-axes`: a label's variable-font axes follow the value it shows."""
import pytest
from PySide6.QtGui import QFont
from PySide6.QtTest import QTest

from LevityDash.lib.ui.font_axes import FontAxes, decodeFontAxes
from LevityDash.lib.ui.frontends.PySide.Modules import Panel
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Text import Text
from unitcorn.temperature import Temperature

SPEC = {'range': ['20°F', '95°F'], 'wght': [500, 800], 'ROND': [0, 100]}


def test_ends_and_middle():
	axes = FontAxes(SPEC)
	assert axes.resolve(Temperature.Fahrenheit(20)) == {'wght': 500, 'ROND': 0}
	assert axes.resolve(Temperature.Fahrenheit(95)) == {'wght': 800, 'ROND': 100}
	mid = axes.resolve(Temperature.Fahrenheit(57.5))
	assert mid == {'wght': 650, 'ROND': 50}


def test_clamped_and_unclamped():
	assert FontAxes(SPEC).resolve(Temperature.Fahrenheit(-40)) == {'wght': 500, 'ROND': 0}
	assert FontAxes({**SPEC, 'clamp': False}).resolve(Temperature.Fahrenheit(132.5))['ROND'] == 150


def test_range_unit_is_converted_to_the_value_unit():
	axes = FontAxes(SPEC)
	assert axes.resolve(Temperature.Celsius(35))['ROND'] == 100  # 95 F
	assert axes.resolve(Temperature.Celsius(-6.6666667))['ROND'] == 0  # 20 F


def test_plain_numbers_and_strings():
	axes = FontAxes({'range': [0, 10], 'weight': [100, 200]})
	assert axes.resolve(5) == {'wght': 150}
	assert axes.resolve('10') == {'wght': 200}


def test_no_number_leaves_font_or_fallback():
	assert FontAxes(SPEC).resolve('n/a') == {}
	assert FontAxes(SPEC).resolve(None) == {}
	assert FontAxes({**SPEC, 'fallback': {'wght': 500}}).resolve(None) == {'wght': 500}


def test_fixed_axis_and_own_range():
	axes = FontAxes({'opsz': 32, 'ROND': {'from': 0, 'to': 100, 'range': [0, 50]}})
	assert axes.resolve(25) == {'opsz': 32, 'ROND': 50}


def test_aliases():
	axes = FontAxes({'range': [0, 1], 'round': [0, 100], 'weight': 400})
	assert axes.resolve(1) == {'ROND': 100, 'wght': 400}


@pytest.mark.parametrize('spec', [
	{}, {'wght': [1, 2]}, {'range': [1, 1], 'wght': [1, 2]}, {'range': [0, 1], 'bogus': [1, 2]},
	{'range': [0, 1], 'wght': [1]}, {'range': [0, 1], 'wght': [1, 2], 'clamp': 'yes'}, 'wght', [1],
])
def test_bad_specs(spec):
	with pytest.raises((ValueError, TypeError)):
		decodeFontAxes(spec)


def test_off():
	assert decodeFontAxes(None) is None and decodeFontAxes(False) is None


@pytest.fixture
def sandbox(dashboard):
	box = Panel(parent=dashboard.scene.base, geometry={'x': '0%', 'y': '0%', 'width': '60%', 'height': '60%'})
	yield box
	if box.scene() is not None:
		box.scene().removeItem(box)


def test_text_font_takes_the_axes(dashboard, sandbox):
	def item(text, **extra):
		return {'type': 'text', 'text': text, 'font-axes': {'range': [0, 100], 'wght': [100, 900], 'ROND': [0, 100]}, **extra}
	sandbox.state = {'items': [item('0'), item('100'), item('50')]}
	for _ in range(6):
		QTest.qWait(20)
		dashboard.app.processEvents()
	got = {i.text: i for i in sandbox.scene().items() if isinstance(i, Text) and sandbox.isAncestorOf(i)}
	assert got['0']._fontAxes is not None
	tag = QFont.Tag
	assert got['0'].font().variableAxisValue(tag('wght')) == 100
	assert got['100'].font().variableAxisValue(tag('wght')) == 900
	assert got['50'].font().variableAxisValue(tag('ROND')) == 50
