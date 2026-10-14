import importlib
from types import SimpleNamespace

import pytz

realtime = importlib.import_module('LevityDash.lib.ui.frontends.PySide.Modules.Displays.Realtime')

# LevityDash swaps in its own `datetime` module on import, so these come after it.
from datetime import datetime, timezone


def test_a_time_value_is_shown_in_the_configured_zone(monkeypatch):
	"""A sunrise that arrives in UTC (or any zone but the config's) prints in the config's zone."""
	monkeypatch.setattr(realtime, 'userConfig', SimpleNamespace(tz=pytz.timezone('America/Chicago')))
	holder = SimpleNamespace(formatString='%H:%M')
	sunrise = datetime(2026, 10, 14, 12, 30, tzinfo=timezone.utc)
	assert realtime.MeasurementDisplayProperties._textFor(holder, sunrise) == '07:30'
