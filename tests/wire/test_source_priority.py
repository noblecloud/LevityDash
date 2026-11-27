"""Which source answers when several publish the same key.

OpenWeatherMap proved the least accurate source, so it is demoted by ``priority``; a source whose
live reading has gone quiet (a dead sensor) yields the key to a fresh one (``maxAge``).
"""
from datetime import datetime, timedelta, timezone

import unitcorn as wu

from LevityDash.lib.plugins.categories import CategoryItem
from LevityDash.lib.plugins.dispatcher import MultiSourceContainer, _isStale, _rank
from LevityDash.lib.wire.containers import ContainerFlags, RemoteSource

KEY = CategoryItem('environment.temperature.visibility')


def _add(multi, name, *, age=timedelta(0), **kw):
	source = RemoteSource(name=name, **kw)
	container = source.getOrCreate(KEY)
	container._update(
		value=wu.Temperature.Fahrenheit(60),
		flags=ContainerFlags(isRealtime=True),
		timestamp=datetime.now(tz=timezone.utc) - age,
	)
	multi[name] = container
	return container


def test_priority_beats_registration_order_and_defaultFor_count():
	multi = MultiSourceContainer(KEY)
	owm = _add(multi, 'OpenWeatherMap', priority=-10, defaultFor={'a', 'b', 'c'})  # registered first, claims most
	pirate = _add(multi, 'PirateWeather', priority=10)
	assert _rank(pirate.source) > _rank(owm.source)
	assert multi.getRealtimeContainer() is pirate


def test_defaultFor_still_breaks_ties():
	multi = MultiSourceContainer(KEY)
	_add(multi, 'OpenMeteo', priority=10)
	pirate = _add(multi, 'PirateWeather', priority=10, defaultFor={'temperature'})
	assert multi.getRealtimeContainer() is pirate


def test_a_quiet_source_yields_to_a_fresh_one():
	multi = MultiSourceContainer(KEY)
	station = _add(multi, 'WeatherFlow', priority=20, maxAge=timedelta(minutes=30), age=timedelta(hours=3))
	model = _add(multi, 'OpenMeteo', priority=10)
	assert _isStale(station) and not _isStale(model)
	assert multi.getRealtimeContainer() is model


def test_a_fresh_station_still_beats_the_models():
	multi = MultiSourceContainer(KEY)
	station = _add(multi, 'WeatherFlow', priority=20, maxAge=timedelta(minutes=30), age=timedelta(minutes=2))
	_add(multi, 'OpenMeteo', priority=10)
	assert multi.getRealtimeContainer() is station


def test_a_stale_source_is_better_than_nothing():
	multi = MultiSourceContainer(KEY)
	station = _add(multi, 'WeatherFlow', priority=20, maxAge=timedelta(minutes=30), age=timedelta(hours=3))
	assert multi.getRealtimeContainer() is station


def test_default_config_file_is_named_for_the_class_not_a_property():
	"""Govee's `name` is a property, so `Govee.name` is a property object: it must not name a file."""
	import inspect
	from LevityDash.lib.plugins.builtin.Govee import Govee
	from LevityDash.lib.plugins.plugin import Plugin
	assert not isinstance(Govee.name, str)
	assert 'cls.name}' not in inspect.getsource(Plugin.getDefaultConfig)
