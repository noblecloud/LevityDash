"""Round numbers for a value axis. Qt-free."""
from math import ceil, floor, log10, isfinite
from typing import Sequence

__all__ = ['niceTicks', 'formatTick']


def _niceStep(raw: float) -> float:
	"""The 1, 2, 2.5, 5 or 10 times a power of ten nearest `raw`, by ratio."""
	power = 10 ** floor(log10(raw))
	return min((f * power for f in (1, 2, 2.5, 5, 10)), key=lambda step: abs(log10(step / raw)))


def niceTicks(low: float, high: float, count: int = 4) -> list[float]:
	"""About `count` round values inside `low`..`high`, low to high.

	The step is the round one (1, 2, 2.5, 5 times a power of ten) nearest the even split, so a 0 to 100 span asked for 4 marks gives 0, 50, 100 and never 0, 33.3, 66.7, 100.
	An empty or backwards span, or a non-finite end, gives nothing.
	"""
	if count < 1 or not (isfinite(low) and isfinite(high)) or high <= low:
		return []
	step = _niceStep((high - low) / max(count - 1, 1))
	first = ceil(low / step - 1e-9)
	last = floor(high / step + 1e-9)
	return [round(i * step, 10) for i in range(first, last + 1)]


def formatTick(value: float, spec: str | None, step: float | None = None) -> str:
	"""`value` through `spec` (a `format` spec such as `{:.0f}` or `.1f`); with none, as few decimals as the step needs."""
	if spec:
		return spec.format(value) if '{' in spec else format(value, spec)
	if step is not None and step < 1:
		places = next((d for d in range(1, 6) if abs(round(step, d) - step) < 1e-9), 4)
		return f'{value:.{places}f}'
	return f'{value:.0f}' if float(value).is_integer() else f'{value:g}'
