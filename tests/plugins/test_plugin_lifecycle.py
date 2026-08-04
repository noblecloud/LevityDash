"""Regression test for the future/loop cached_property reset bug.

Every builtin plugin's bootstrap() closure does `del self.loop` on shutdown so
the next start() gets a fresh event loop (`loop` is a `cached_property`).
`future` is built from that loop (`self.loop.create_future()`) and is also a
`cached_property` - but stop()/asyncStop() only ever *resolve* it
(`future.set_result(True)`), never delete it. Without a matching
`del self.future`, the same already-resolved Future survives every later
start(), so `await self.future` inside asyncStart() returns instantly and the
plugin appears to shut itself down the moment it starts - real-world repro was
the plugin control-plane's stop/start wire commands: a plugin that had been
stopped once could never be started again for the rest of the process's life.
"""
from LevityDash.lib.plugins.plugin import Plugin


def _bare_plugin() -> Plugin:
	"""A Plugin instance with none of the config/schema machinery run - only
	the loop/future cached_property behavior under test needs to exist."""
	return object.__new__(Plugin)


def test_future_is_recreated_and_rebound_after_del():
	plugin = _bare_plugin()

	first_loop = plugin.loop
	first_future = plugin.future
	assert not first_future.done()
	assert first_future.get_loop() is first_loop

	# Mirrors a real stop(): asyncStop() resolves the future, bootstrap()'s
	# cleanup deletes both cached properties so the next start() is fresh.
	first_future.set_result(True)
	del plugin.loop
	del plugin.future

	second_loop = plugin.loop
	second_future = plugin.future

	assert second_loop is not first_loop
	assert second_future is not first_future
	assert not second_future.done()
	assert second_future.get_loop() is second_loop


def test_future_left_undeleted_would_still_be_resolved():
	"""Pins the failure mode this guards against: deleting `loop` alone is not
	enough. If `future` survives a stop, the *next* start's `await
	self.future` resolves immediately, because it's the same completed Future
	from the first stop."""
	plugin = _bare_plugin()
	original_future = plugin.future
	original_future.set_result(True)

	del plugin.loop  # loop resets ...

	# ... but future was never deleted, so it's still the resolved original.
	assert plugin.future is original_future
	assert plugin.future.done()
