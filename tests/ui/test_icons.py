"""Glyph packs: discovery, lookup, and the failures that used to be bare KeyErrors."""
import pytest


def icons():
	from LevityDash.lib.ui import icons as module
	return module


def test_the_registry_holds_the_three_shipped_packs():
	module = icons()
	packs = module.packs()
	assert {'fa', 'mdi', 'wi'} <= set(packs)
	for prefix, pack in packs.items():
		assert pack.prefix == prefix, 'a pack is registered under its own prefix'
		assert pack.styles, f'{prefix} declares no style with glyphs'


def test_the_named_packs_are_the_registry_entries():
	module = icons()
	assert module.fa is module.packs()['fa']
	assert module.mdi is module.packs()['mdi']
	assert module.wi is module.packs()['wi']


def test_the_icon_prefix_is_stripped_and_nothing_else_is():
	module = icons()
	assert module.getIcon('icon:wi:day-sunny').name == 'day-sunny'
	# `lstrip('icon:')` ate any leading i/c/o/n/:, so `cloud` came back as `loud`.
	assert module.getIcon('fa:cloud').name == 'cloud'


def test_a_bare_name_is_found_in_any_pack():
	module = icons()
	assert module.getIcon('home').prefix == 'mdi'
	assert module.getIcon('day-sunny').prefix == 'wi'


def test_a_pack_alias_resolves_to_the_canonical_name():
	module = icons()
	icon = module.getIcon('clear-day')
	assert (icon.prefix, icon.name) == ('wi', 'day-sunny')
	assert module.getIcon('wi:clear-day').name == 'day-sunny'


def test_a_retired_pack_prefix_still_resolves():
	module = icons()
	assert module.getIcon('mdi6:home').name == 'home'


def test_an_unknown_name_raises_a_key_error_with_a_suggestion():
	module = icons()
	with pytest.raises(module.IconNotFound) as caught:
		module.getIcon('wi:day-sunnyy')
	assert isinstance(caught.value, KeyError), 'callers that catch KeyError keep working'
	assert 'day-sunny' in str(caught.value)


def test_an_unknown_pack_names_the_ones_that_exist():
	module = icons()
	with pytest.raises(module.IconPackNotFound) as caught:
		module.getIcon('zz:home')
	for prefix in ('fa', 'mdi', 'wi'):
		assert prefix in str(caught.value)


def test_a_font_only_pack_answers_none_for_svg_instead_of_raising():
	module = icons()
	assert module.wi.getIconSvg('day-sunny') is None
	assert module.mdi.getIconSvg('home') is None
	assert module.fa.getIconSvg('star').startswith('<svg')


def test_every_font_awesome_style_has_its_own_font():
	# `[font-awesome.regular]` was commented out, so `fa:star` with style `regular`
	# silently drew the solid font.
	module = icons()
	fa = module.fa
	assert set(fa.styles) == {'solid', 'regular', 'brands'}
	for style in fa.styles:
		assert style in fa.fonts, f'{style} has no font'
	solid = module.getIcon('fa:star', 'solid').font
	regular = module.getIcon('fa:star', 'regular').font
	assert regular.family() != 'Font Awesome 6 Brands'
	assert regular.styleName() == 'regular'
	assert solid.styleName() == 'solid'


def test_a_lookup_is_cached():
	module = icons()
	assert module.getIcon('wi:rain') is module.getIcon('wi:rain')


def test_every_shipped_pack_validates_clean():
	module = icons()
	for prefix, pack in module.packs().items():
		assert pack.validate() == [], f'{prefix}: {pack.validate()}'


def test_a_broken_map_is_skipped_and_the_rest_still_load(tmp_path, monkeypatch):
	module = icons()
	broken = tmp_path / 'broken.toml'
	broken.write_text('[oops\nprefix = "no"')
	monkeypatch.setattr(module, '_map_dirs', lambda: (tmp_path, module.IconPack.basePath / 'maps'))
	try:
		packs = module.discover(force=True)
		assert {'fa', 'mdi', 'wi'} <= set(packs), 'a bad user map must not take the shipped packs down'
		assert 'no' not in packs
	finally:
		monkeypatch.undo()
		module.discover(force=True)


def test_a_user_map_joins_the_registry(tmp_path, monkeypatch):
	module = icons()
	(tmp_path / 'test-glyphs.toml').write_text(
		'[test-glyphs]\n'
		'prefix = "tg"\n'
		'name = "Test Glyphs"\n'
		'\n'
		'[test-glyphs.regular]\n'
		f'font = "{{__resources__}}/icons/weathericons.ttf"\n'
		'\n'
		'[test-glyphs.regular.chars]\n'
		'mark = "0xf00d"\n'
	)
	monkeypatch.setattr(module, '_map_dirs', lambda: (tmp_path, module.IconPack.basePath / 'maps'))
	try:
		packs = module.discover(force=True)
		assert 'tg' in packs
		icon = module.getIcon('tg:mark')
		assert icon.name == 'mark' and ord(icon.unicode) == 0xF00D
		assert packs['tg'].validate() == []
	finally:
		monkeypatch.undo()
		module.discover(force=True)
