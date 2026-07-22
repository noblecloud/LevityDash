"""Demonstrates the frozen_time fixture: the clock reads a fixed instant."""


def test_now_is_frozen(dashboard, frozen_time):
	from LevityDash.lib.utils.shared import now, Now

	assert now() == frozen_time
	assert Now.now() == frozen_time
	assert str(Now()) == str(frozen_time)

	# the DateTime clock renders via a (now-frozen) strftime
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays import DateTime
	assert DateTime.strftime("%H:%M") == frozen_time.strftime("%H:%M")


def test_now_unfrozen_outside_fixture(dashboard):
	"""Sanity: without the fixture the clock is live (near real wall-time)."""
	import datetime as dt
	from LevityDash.lib.utils.shared import now

	delta = abs((now() - dt.datetime.now(dt.timezone.utc)).total_seconds())
	assert delta < 5  # live clock, within a few seconds of real time
