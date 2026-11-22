"""Vector glyphs: a pack of path data, drawn into the same path a text item fills.

A font glyph is a character from an icon font; a vector glyph is `d` data in a map.
Both are `Icon`s, so every item that takes `icon:` accepts either, and the layout
metrics that reserve space for a character reserve the same square for a path.
"""
import pytest

from LevityDash.lib.ui.frontends.PySide.Modules import Panel
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Text import Text


def icons():
	from LevityDash.lib.ui import icons as module
	return module


def test_the_vector_pack_is_discovered_with_the_font_packs():
	module = icons()
	packs = module.packs()
	assert 'vec' in packs
	assert packs['vec'].styles == ('line',)
	assert 'sun' in packs['vec'].names


def test_a_vector_name_answers_a_vector_icon_not_a_character():
	module = icons()
	icon = module.getIcon('vec:sun')
	assert isinstance(icon, module.VectorIcon)
	assert icon.isVector and not module.getIcon('wi:day-sunny').isVector
	assert icon.parts, 'path data comes from the map'
	assert icon.viewBox == (24.0, 24.0)
	assert str(icon) == '', 'a vector glyph has no character'


def test_a_vector_glyph_has_a_square_box_at_any_size():
	module = icons()
	icon = module.getIcon('vec:arrow-up')
	path = icon.painterPath(40.0)
	bounds = path.boundingRect()
	assert path.elementCount() > 3
	assert icon.advance(40.0) == 40.0
	assert bounds.width() <= 40.5 and bounds.height() <= 40.5
	assert bounds.width() > 20 and bounds.height() > 20, 'the glyph fills its box'


def test_the_converted_sets_are_discovered():
	module = icons()
	for prefix, count in (('wiv', 219), ('qw', 507), ('meteo', 519)):
		pack = module.packs()[prefix]
		assert len(pack.names) == count, f'{prefix} has {len(pack.names)} names'
		assert pack.validate() == [], f'{prefix}: {pack.validate()[:3]}'


def test_a_converted_glyph_draws_at_its_viewbox():
	module = icons()
	for name, side in (('wiv:day-sunny', 30.0), ('qw:100', 16.0), ('meteo:clear-day', 128.0)):
		icon = module.getIcon(name)
		assert icon.viewBox == (side, side), f'{name} viewBox {icon.viewBox}'
		bounds = icon.painterPath(64.0).boundingRect()
		assert bounds.width() > 8 and bounds.height() > 8, f'{name} is empty: {bounds}'


def test_a_part_with_a_stroke_is_stroked_and_a_cutout_is_subtracted():
	module = icons()
	icon = module.getIcon('meteo:clear-day')
	strokes = [part for part in icon.parts if part.stroke]
	assert strokes, 'the sun core is a stroked circle in the source'
	assert icon.iconPack.roleToken('body') is None, 'a pack declares a colour only when it wants one'


def test_a_stroke_only_glyph_still_fills():
	# `stroke = 2` in the map is baked into the outline, so one brush draws it.
	module = icons()
	icon = module.getIcon('vec:plus')
	assert icon.stroke == 2.0
	assert icon.painterPath(32.0).contains(icon.painterPath(32.0).boundingRect().center())


def test_a_vector_icon_and_a_font_icon_can_both_be_asked_for():
	module = icons()
	assert module.getIcon('vec:sun').name == 'sun'
	assert module.getIcon('wi:day-sunny').name == 'day-sunny'
	with pytest.raises(module.IconNotFound):
		module.getIcon('vec:nonesuch')


def _text(dashboard, icon_name):
	sandbox = Panel(parent=dashboard.scene.base, geometry={'x': '0%', 'y': '0%', 'width': '30%', 'height': '30%'})
	sandbox.state = {'items': [{
		'type':  'text',
		'name':  'probe',
		'text':  'Hi',
		'icon':  icon_name,
		'margins': '0px',
		'geometry': {'x': '0%', 'y': '0%', 'width': '100%', 'height': '100%'},
	}]}
	dashboard.app.processEvents()
	items = [item for item in sandbox.scene().items() if isinstance(item, Text) and sandbox.isAncestorOf(item)]
	assert items, f'no Text item built for {icon_name}'
	item = items[0]
	icon = item.icon
	assert icon is not None, f'{icon_name}: the item has no icon'
	if icon_name.startswith('vec:'):
		assert getattr(icon, 'isVector', False), f'{icon_name}: item icon is {icon!r}'
		assert item._vectorGlyph() is not None, 'the text item does not see a vector glyph'
	# The dashboard reads state on its own tick; a bare panel needs the pull.
	item.updateTransform(updatePath=True, reason='test')
	dashboard.app.processEvents()
	dashboard.wait_until(
		lambda: not item.path().isEmpty() or item.__dict__.get('_svgItem') is not None,
		message=f'{icon_name} lays out (text={item.text!r}, icon={item.icon!r})',
	)
	return sandbox, item


TWO_TONE = '''
[tg]
prefix = "tg"
name = "Test two-tone"
default = "line"
colors = { accent = "$accent" }

[tg.line]
viewBox = "0 0 24 24"

[tg.line.svg]
badge = [
  { d = "M2 2 H22 V14 H2 Z" },
  { d = "M2 18 H22 V22 H2 Z", role = "accent" },
]
'''


def _with_pack(tmp_path, monkeypatch, module, body=TWO_TONE):
	(tmp_path / 'test-two-tone.toml').write_text(body)
	monkeypatch.setattr(module, '_map_dirs', lambda: (tmp_path, module.IconPack.basePath / 'maps'))
	return module.discover(force=True)


def test_roles_are_separate_paths(tmp_path, monkeypatch):
	module = icons()
	try:
		pack = _with_pack(tmp_path, monkeypatch, module)['tg']
		icon = pack.getIcon('badge')
		assert set(icon.unitRoles) == {'body', 'accent'}
		paths = icon.rolePaths(48.0)
		assert set(paths) == {'body', 'accent'}
		assert paths['body'].boundingRect().height() > 5
		assert paths['accent'].boundingRect().height() > 5
		assert icon.paintRoles == ('body', 'accent')
	finally:
		monkeypatch.undo()
		module.discover(force=True)


def test_a_role_colour_comes_from_the_pack_then_the_theme(tmp_path, monkeypatch):
	from LevityDash.lib.ui.colors import theme
	from LevityDash.lib.ui.colors.color import Color

	module = icons()
	try:
		pack = _with_pack(tmp_path, monkeypatch, module)['tg']
		assert pack.roleColor('accent').QColor == Color.role('accent').QColor, 'the pack names $accent'
		assert pack.roleColor('body').QColor == Color.role('text').QColor, 'an unnamed body takes $text'

		theme.activate({'name': 'glyph-test', 'extends': 'default', 'glyphs': {'tg': {'accent': '#00ff00'}}})
		assert pack.roleColor('accent').QColor.name() == '#00ff00', 'a theme recolours a pack by name'
	finally:
		theme.activate(None)
		monkeypatch.undo()
		module.discover(force=True)


def test_a_two_tone_glyph_draws_its_accent_as_its_own_item(dashboard, tmp_path, monkeypatch):
	from LevityDash.lib.ui.colors.color import Color

	module = icons()
	try:
		_with_pack(tmp_path, monkeypatch, module)
		sandbox, item = _text(dashboard, 'tg:badge')
		try:
			children = item.__dict__.get('_partItems') or []
			assert len(children) == 1, 'the accent band is a child with its own brush'
			assert children[0].brush().color() == Color.role('accent').QColor

			item.setGlyphColorMode('mono')
			item.updateTransform(updatePath=True, reason='test')
			dashboard.app.processEvents()
			assert not item.__dict__.get('_partItems'), 'mono drops the per-role items'
			assert item.path().boundingRect().height() > 10, 'and the accent band is part of one path'
			assert item.glyphColorMode == 'mono'
		finally:
			if sandbox.scene() is not None:
				sandbox.scene().removeItem(sandbox)
	finally:
		monkeypatch.undo()
		module.discover(force=True)


def test_an_animated_glyph_hosts_a_renderer_and_advances(dashboard):
	module = icons()
	glyph = module.getIcon('mxn:clear-day')
	assert glyph.isAnimated
	renderer = glyph.renderer('#ffffff')
	assert renderer.isValid() and renderer.animated(), 'the file animates itself'
	assert renderer.animationDuration() > 0

	sandbox, item = _text(dashboard, 'mxn:clear-day')
	try:
		svg_item = item.__dict__.get('_svgItem')
		timer = item.__dict__.get('_svgTimer')
		assert svg_item is not None, 'the animated glyph is a child item'
		assert timer is not None and timer.isActive(), 'frames are advanced by a timer'
		start = item._svgFrame
		dashboard.wait_until(lambda: item._svgFrame != start, timeout=3, message='the animation advances')
	finally:
		if sandbox.scene() is not None:
			sandbox.scene().removeItem(sandbox)


def test_a_static_pack_does_not_start_a_timer(dashboard):
	sandbox, item = _text(dashboard, 'vec:sun')
	try:
		assert item.__dict__.get('_svgTimer') is None
		assert item.__dict__.get('_svgItem') is None
	finally:
		if sandbox.scene() is not None:
			sandbox.scene().removeItem(sandbox)


def test_a_vector_icon_lays_out_where_a_font_icon_does(dashboard):
	vector_box, vector = _text(dashboard, 'vec:sun')
	font_box, font = _text(dashboard, 'wi:day-sunny')
	try:
		vector_path, font_path = vector.path(), font.path()
		assert vector_path.elementCount() > 4, 'the path is the glyph, not an empty string'
		assert font_path.elementCount() > 0
		# Both are square-ish icon boxes: within a third of each other, neither collapsed.
		short, tall = sorted((vector_path.boundingRect().height(), font_path.boundingRect().height()))
		assert short > 0
		assert tall / short < 3.0, f'vector {vector_path.boundingRect()} vs font {font_path.boundingRect()}'
	finally:
		for box in (vector_box, font_box):
			if box.scene() is not None:
				box.scene().removeItem(box)
