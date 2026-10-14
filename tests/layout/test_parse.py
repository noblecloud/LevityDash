import pytest

from LevityDash.lib.layout.parse import parse_content_align, parse_item_align, parse_wrap
from LevityDash.lib.layout.types import Alignment, ContentAlign, ItemAlign, Wrap


def test_keywords_ignore_case_underscores_and_spaces():
	assert parse_content_align(' Space_Between ') == Alignment(ContentAlign.space_between)
	assert parse_item_align('flex-end') == Alignment(ItemAlign.flex_end)


def test_safe_and_unsafe_come_before_the_keyword():
	assert parse_item_align('safe center') == Alignment(ItemAlign.center, True)
	assert parse_item_align('unsafe center') == Alignment(ItemAlign.center, False)


def test_a_member_passes_through():
	assert parse_content_align(ContentAlign.center) == Alignment(ContentAlign.center)


def test_a_typo_names_the_allowed_words():
	with pytest.raises(ValueError, match='space-evenly'):
		parse_content_align('space-evenely')
	with pytest.raises(ValueError):
		parse_item_align('safe')


def test_wrap_takes_words_and_booleans():
	assert parse_wrap('wrap-reverse') is Wrap.wrap_reverse
	assert parse_wrap(True) is Wrap.wrap
	assert parse_wrap(False) is Wrap.nowrap
	with pytest.raises(ValueError):
		parse_wrap('sideways')
