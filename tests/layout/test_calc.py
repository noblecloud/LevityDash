"""CSS math functions, checked against the rules and examples in css-values-4 section 10."""
import pytest

from LevityDash.lib.layout.calc import evaluate_math, is_math

UNITS = {'px': 1.0, '%': 8.0, 'mm': 4.0}  # 1% of the base is 8px


def px(number, unit):
	return number * UNITS[unit]


def calc(text):
	return evaluate_math(text, px)


def test_is_math_sees_only_math_functions():
	assert is_math('calc(1px + 2px)') and is_math(' clamp(1px, 2px, 3px)')
	assert not is_math('12px') and not is_math('minmax(1px, 2px)') and not is_math(3)


def test_calc_adds_lengths_and_resolves_percent_through_to_px():
	assert calc('calc(100% - 20px)') == 780


def test_calc_precedence_and_grouping():
	assert calc('calc(10px + 2 * 5px)') == 20
	assert calc('calc((10px + 2px) * 5)') == 60
	assert calc('calc(60px / 4 + 1px)') == 16


def test_calc_nested_and_unary():
	assert calc('calc(calc(10px + 10px) - -5px)') == 25
	assert calc('calc(-10px + 30px)') == 20


def test_min_max_clamp():
	assert calc('min(50%, 300px)') == 300
	assert calc('max(10mm, 30px)') == 40
	assert calc('clamp(100px, 50%, 300px)') == 300
	assert calc('clamp(100px, 5%, 300px)') == 100
	assert calc('calc(clamp(10px, 20px, 30px) * 2)') == 40


@pytest.mark.parametrize('text, message', [
	('calc(1px +2px)', 'white space'),
	('calc(1px+ 2px)', 'white space'),
	('calc(1px + 2)', 'length and a number'),
	('calc(2px * 3px)', 'length times a length'),
	('calc(10px / 2px)', 'divide by a length'),
	('calc(10px / 0)', 'division by zero'),
	('calc(3 * 2)', 'a number, not a length'),
	('min(1px, 2)', 'mixes'),
	('clamp(1px, 2px)', 'three values'),
	('calc(1px + )', 'unexpected'),
	('calc(1px', 'expected'),
	('foo(1px)', 'not a math function'),
])
def test_math_names_the_broken_rule(text, message):
	with pytest.raises(ValueError, match=message):
		calc(text)
