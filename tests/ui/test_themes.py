"""Theme tokens: ``$name`` in colours, fonts and gradients, resolved against the active theme."""
import pytest

from LevityDash.lib.ui.colors import Color, Gradient, theme


@pytest.fixture(autouse=True)
def default_theme():
	theme.reset()
	yield
	theme.reset()


def test_every_shipped_theme_defines_the_standard_tokens():
	for name in theme.available():
		loaded = theme.load(name)
		for group, tokens in theme.STANDARD_TOKENS.items():
			assert set(tokens) <= loaded.names(group), (name, group)


def test_default_theme_keeps_the_original_look():
	assert Color.decode('$text').hex == '#ffffff'
	assert Color.decode('$background').hex == '#000000'
	assert Color.decode('$muted').hex == '#eeeeee'
	assert Color.decode('$series-1').hex == '#ff9aa3'


def test_token_colour_keeps_its_name_for_saving():
	assert str(Color.decode('$accent')) == '$accent'
	assert str(Color('$accent')) == '$accent'
	assert str(Color.decode('#ff8a3d')) == '#ff8a3d'


def test_a_theme_extends_another_and_overrides_tokens():
	theme.activate('paper')
	assert Color.decode('$text').hex == '#1d1b18'
	assert theme.active().mode == 'light'
	assert theme.font('mono') == 'Roboto Mono'  # taken from default


def test_inline_theme_adds_board_level_tokens():
	theme.activate({'extends': 'dusk', 'colors': {'solar': '#ffd400', 'muted': {'color': '$text', 'alpha': 0.5}}})
	assert Color.decode('$solar').hex == '#ffd400'
	assert Color.decode('$muted').alpha == 128
	assert Color.decode('$bad').hex == '#ff5a4a'


def test_modifiers():
	assert Color.decode({'color': '#808080', 'alpha': 0.5}).alpha == 128
	lighter = Color.decode({'color': '#808080', 'lighten': 0.1})
	assert lighter.red > 0x80
	darker = Color.decode({'color': '#808080', 'darken': 0.1})
	assert darker.red < 0x80
	halfway = Color.decode({'color': '#000000', 'mix': {'with': '#ffffff', 'by': 0.5}})
	assert 0x50 < halfway.red < 0xb0


def test_unknown_token_and_cycles_are_reported():
	with pytest.raises(theme.ThemeError, match='no token \\$nope'):
		Color.decode('$nope')
	theme.activate({'colors': {'a': '$b', 'b': '$a'}})
	with pytest.raises(theme.ThemeError, match='refers to itself'):
		Color.decode('$a')


def test_wrong_group_is_reported():
	with pytest.raises(theme.ThemeError, match='is a font, not a color'):
		Color.decode('$mono')


def test_scale_token_is_a_gradient_and_keeps_unit_stops():
	theme.activate('paper')
	gradient = Gradient.decode('$temperature')
	assert isinstance(gradient, Gradient)
	assert '85°F' in gradient
	assert gradient['85°F'].color.hex == '#c2410c'  # $accent of paper, inside the scale


def test_role_colour_follows_the_theme_in_place():
	text = Color.role('text')
	assert text.hex == '#ffffff'
	theme.activate('paper')
	assert text is Color.role('text')
	assert text.hex == '#1d1b18'
	theme.reset()
	assert text.hex == '#ffffff'


def test_override_wins_over_the_dashboard():
	theme.set_override('dusk')
	theme.activate('paper')
	assert theme.active().name == 'dusk'
	theme.set_override(None)
	assert theme.active().name == 'default'


def test_a_theme_can_recolour_a_named_preset():
	before = Gradient.decode('UVIndexGradient')
	theme.activate({'scales': {'UVIndexGradient': {0: '#000000', 10: '#ffffff'}}})
	assert Gradient.decode('UVIndexGradient') is not before
	theme.reset()
	assert Gradient.decode('UVIndexGradient') is before
	assert Gradient.decode('$temperature') is Gradient.decode('TemperatureGradient')
