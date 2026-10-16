import pytest

from LevityDash.lib.plugins.places import normalizePlace, placeContains


def test_normalize_trims_and_lowercases():
	assert normalizePlace('  Home.Upstairs ') == 'home.upstairs'
	assert normalizePlace('') is None
	assert normalizePlace(None) is None


@pytest.mark.parametrize('text', ['home..bedroom', '.home', 'home.', 'home bedroom', 'home/bedroom'])
def test_normalize_rejects_what_is_not_a_dotted_path(text):
	with pytest.raises(ValueError):
		normalizePlace(text)


@pytest.mark.parametrize('query, place, expected', [
	('home.upstairs', 'home.upstairs.bedroom', True),
	('home.upstairs.bedroom', 'home.upstairs.bedroom', True),
	('home', 'home.upstairs.bedroom', True),
	('home.up', 'home.upstairs', False),            # whole segments only
	('home.upstairs.bedroom', 'home.upstairs', False),  # a child does not match its parent
	('bedroom', 'home.upstairs.bedroom', False),    # the match starts at the root
])
def test_place_contains(query, place, expected):
	assert placeContains(query, place) is expected


def test_identities_at_matches_by_place_across_plugins():
	from LevityDash.lib.plugins.places import identitiesAt, placesOf

	class Plugin:
		def __init__(self, places=None):
			self.places = places

	plugins = [
		Plugin({'bedroom': 'home.upstairs.bedroom'}),
		Plugin({'office': 'home.upstairs.office', 'kitchen': 'home.downstairs.kitchen'}),
		Plugin(),      # a plugin with no places is skipped
		object(),
	]
	assert placesOf(plugins) == {'bedroom': 'home.upstairs.bedroom', 'office': 'home.upstairs.office', 'kitchen': 'home.downstairs.kitchen'}
	assert identitiesAt('home.upstairs', plugins) == ['bedroom', 'office']
	assert identitiesAt('home.upstairs.office', plugins) == ['office']
	assert identitiesAt('home.garage', plugins) == []
	assert identitiesAt('', plugins) == []
