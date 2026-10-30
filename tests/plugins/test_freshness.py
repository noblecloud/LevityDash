from datetime import timedelta

from LevityDash.lib.plugins.freshness import DEFAULT_STALE_AFTER, RefreshEstimator


def feed(estimator, *times):
	for t in times:
		estimator.observe(t)


def test_nothing_learned_uses_default():
	assert RefreshEstimator().staleAfter() == DEFAULT_STALE_AFTER


def test_one_update_has_no_period():
	e = RefreshEstimator()
	e.observe(100)
	assert e.period is None


def test_fast_source_is_missed_soon_but_not_before_the_floor():
	e = RefreshEstimator()
	feed(e, 0, 20, 40, 60, 80)
	assert e.period == timedelta(seconds=20)
	assert e.staleAfter() == timedelta(seconds=60)


def test_hourly_poll_is_fresh_at_forty_minutes():
	e = RefreshEstimator()
	feed(e, 0, 3600, 7200, 10800)
	assert e.staleAfter() > timedelta(minutes=40)


def test_declared_period_wins_when_longer():
	e = RefreshEstimator()
	feed(e, 0, 20, 40)
	assert e.staleAfter(declared=timedelta(hours=1)) == timedelta(hours=2, minutes=30)


def test_one_outage_does_not_move_the_median():
	e = RefreshEstimator()
	feed(e, 0, 30, 60, 90, 5000, 5030, 5060)
	assert e.period == timedelta(seconds=30)


def burst(start, count=43, step=0.2):
	"""One poll that publishes `count` keys in a row."""
	return [start + i * step for i in range(count)]


def test_a_burst_of_keys_is_one_update():
	e = RefreshEstimator(burst=timedelta(seconds=5))
	for poll in (0, 900, 1800, 2700):
		feed(e, *burst(poll))
	assert e.period == timedelta(seconds=900)
	assert e.staleAfter() == timedelta(seconds=2250)


def test_without_burst_grouping_the_same_feed_collapses_to_the_step():
	e = RefreshEstimator()
	for poll in (0, 900, 1800, 2700):
		feed(e, *burst(poll))
	assert e.period < timedelta(seconds=1)
	assert e.staleAfter() == timedelta(seconds=60)


def test_a_source_that_never_pauses_still_learns_a_period():
	e = RefreshEstimator(burst=timedelta(seconds=5))
	feed(e, *[i * 3.0 for i in range(100)])
	assert e.period is not None
	assert timedelta(seconds=25) <= e.period <= timedelta(seconds=35)
