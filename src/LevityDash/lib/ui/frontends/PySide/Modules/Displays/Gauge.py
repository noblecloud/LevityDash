"""Gauge: the display class, moved.

The class lives in `meter/gauge.py` now - with the arc it draws and, shortly, the
dial's geometry - and it hands itself to `meter/elements.py` at that module's
foot. This file stays behind so that `from ...Displays.Gauge import Gauge`, which
several modules and tests do, and the star import `Displays/__init__.py` does,
keep working: it re-exports the whole namespace this module had.

The underscore names are here for the same reason - a star import would skip
them, and `_isWholeSteps` arrives through this module in the test that exercises
it.
"""
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.meter.gauge import *  # noqa: F401,F403
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.meter.gauge import (  # noqa: F401
	Gauge, GaugeArc, log, _isWholeSteps, _gaugeKeyName, _UNIT_UNDER_VALUE,
)
