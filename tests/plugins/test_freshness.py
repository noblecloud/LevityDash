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
