"""The meter package: what a gauge and a bar have in common.

`Gauge.py` is one 6,300 line module written for dials. Most of it is not about
dials at all — it is about turning a value into a position on a track, drawing
ticks, fills, needles and labels along it, and laying a panel out around it.
This package is that code, split so a bar can use it too.

See `docs/tasks/meter-survey.md` for the mapping from the old classes to these,
and `docs/tasks/meter-and-bar.md` for the plan.

Nothing here imports `Gauge.py`; that direction is one way, and `Gauge.py` keeps
re-exporting every name the rest of the app imports from it.
"""
