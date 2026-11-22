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
	dashboard.wait_until(lambda: not item.path().isEmpty(), message=f'{icon_name} lays out (text={item.text!r}, icon={item.icon!r})')
	return sandbox, item


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
