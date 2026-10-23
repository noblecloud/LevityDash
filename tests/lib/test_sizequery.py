import pytest

from LevityDash.lib.sizequery import SizeQuery


def q(**spec):
	return SizeQuery.parse({key.replace('_', '-'): value for key, value in spec.items()})


def test_width_and_height_limits_include_their_edge():
	query = q(min_width='900px', max_width=1200)
	assert [query.matches(w, 500) for w in (899, 900, 1200, 1201)] == [False, True, True, False]
	query = q(min_height=400, max_height='600px')
	assert [query.matches(1000, h) for h in (399, 400, 600, 601)] == [False, True, True, False]


def test_orientation_calls_a_square_landscape():
	assert q(orientation='landscape').matches(800, 800)
	assert q(orientation='landscape').matches(900, 800)
	assert not q(orientation='landscape').matches(700, 800)
	assert q(orientation='portrait').matches(700, 800)
	assert not q(orientation='portrait').matches(800, 800)


def test_aspect_takes_a_number_or_a_ratio():
	assert q(min_aspect='16:9').matches(1600, 900)
	assert not q(min_aspect='16:9').matches(1500, 900)
	assert q(max_aspect=1.5).matches(1500, 1000)
	assert not q(max_aspect=1.5).matches(1600, 1000)
	assert q(min_aspect='4/3', max_aspect='16:9').matches(1400, 900)


def test_everything_given_must_hold():
	query = q(min_width=900, orientation='portrait')
	assert query.matches(900, 1200)
	assert not query.matches(1300, 1200)
	assert not query.matches(800, 1200)


def test_a_size_with_no_area_matches_nothing():
	assert not q(min_width=0).matches(0, 0)
	assert not q(max_width=5000).matches(100, 0)


def test_scope_defaults_to_the_window_and_carries_and():
	query = q(min_width=1)
	assert query.of == 'window' and query.data is None
	query = q(of='parent', **{'and': 'a.b.c > 1'})
	assert query.of == 'parent' and query.data == 'a.b.c > 1'


@pytest.mark.parametrize('spec,words', [
	({'min-width': '50%'}, 'pixels'),
	({'min-width': 'wide'}, 'pixels'),
	({'min-width': True}, 'pixels'),
	({'min-aspect': 'wide'}, 'ratio'),
	({'orientation': 'sideways'}, 'orientation'),
	({'of': 'screen'}, 'window'),
	({'min-width': 500, 'max-width': 400}, 'nothing can match'),
	({'min-aspect': 2, 'max-aspect': 1}, 'nothing can match'),
	({'minwidth': 5}, 'unknown key'),
])
def test_a_bad_condition_says_what_is_wrong(spec, words):
	with pytest.raises(ValueError, match=words):
		SizeQuery.parse(spec)
