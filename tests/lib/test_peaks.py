"""findPeaksAndTroughs works on plain floats now; it must find exactly what the object-walking original did."""
import random
from datetime import datetime, timedelta, timezone
from math import sin

import pytest
import unitcorn as wu

from LevityDash.lib.plugins.observation import TimeSeriesItem
from LevityDash.lib.utils.data import datetimeDiff, findPeaksAndTroughs, neighbourExtrema
from typing import Any, Dict, Iterable, List, Sequence, Tuple
import time
from math import inf

# --- the original implementation, kept verbatim as the oracle ---------------------------------
log = type('L', (), {'verbose': staticmethod(lambda *a, **k: None)})


class TemporalGroups(object):

	def __init__(self, data: Sequence['TimeAwareValue'], spread: timedelta = timedelta(hours=12), step: int = 1):
		self.data = data
		self.spread = spread
		self.current = 0
		self.step = step

	def __iter__(self) -> Iterable['TimeAwareValue']:
		return self

	def __next__(self) -> Tuple[int, 'TimeAwareValue', List['TimeAwareValue'], List['TimeAwareValue']]:
		i = self.current
		forI = i
		backI = i

		ahead = []
		behind = []
		if self.current >= len(self.data):
			raise StopIteration
		currentV = self.data[i]
		backV = self.data[i - 1]
		while backI > 0 and abs(backV.timestamp - currentV.timestamp) < self.spread:
			if len(behind) == 0:
				behind.append(backV)
			elif abs(behind[-1].value - backV.value) > 0.1:
				behind.append(backV)

			backI -= 1
			backV = self.data[backI]
		if i + 1 >= len(self.data):
			ahead = []
		else:
			forV = self.data[i + 1]
			while forI < len(self.data) - 1 and abs(forV.timestamp - currentV.timestamp) < self.spread:
				if len(ahead) == 0:
					ahead.append(forV)
				elif abs(ahead[-1].value - forV.value) > 0.1:
					ahead.append(forV)
				forI += 1
				forV = self.data[forI]
		i = self.current
		self.current += self.step
		return i, currentV, behind, ahead


def findPeaksAndTroughs(array: Sequence['TimeAwareValue'], spread: timedelta = 12, groupingSize: timedelta | int = 6) -> List['TimeAwareValue']:
	start_time = time.perf_counter()
	peaks = []
	troughs = []
	if isinstance(groupingSize, int):
		groupingSize = timedelta(hours=groupingSize)
	groupGenerator = TemporalGroups(array, spread=spread)
	peak_flat = False
	trough_flat = False
	for i, node, behind, ahead in groupGenerator:
		if not ahead:
			ahead = [array[-1]]
		if not behind:
			behind = [array[0]]

		if float(min(behind).value) >= node <= float(min(ahead).value):
			if troughs and datetimeDiff(troughs[-1].timestamp, node.timestamp) <= groupingSize:
				troughs[-1] += node
				trough_flat = True
			else:
				if trough_flat:
					troughs[-1] = troughs[-1].flattened
					trough_flat = False
				troughs.append(node)

		elif float(max(behind).value) <= node >= float(max(ahead).value):
			if peaks and datetimeDiff(peaks[-1].timestamp, node.timestamp) <= groupingSize:
				peaks[-1] += node
				peak_flat = True
			else:
				if peak_flat:
					peaks[-1] = peaks[-1].flattened
					peak_flat = False
				peaks.append(node)
	log.verbose(f"findPeaksAndTroughs() {time.perf_counter() - start_time: 0.3g}s for {len(array)} items", verbosity=4)

	merged = []
	peaks = sorted(peaks, key=lambda x: x.timestamp)
	troughs = sorted(troughs, key=lambda x: x.timestamp)
	index = 0
	while peaks or troughs:
		toPop = min(peaks, troughs, key=lambda x: x[0].timestamp.timestamp() if x else inf)
		next_ = toPop.pop(0)
		next_.isPeak = toPop is peaks
		next_.index, index = index, index + 1
		merged.append(next_)
	return merged




def _series(values, step=timedelta(minutes=30)):
	t0 = datetime(2026, 11, 9, tzinfo=timezone.utc)
	return [TimeSeriesItem(wu.temperature.Fahrenheit(v), t0 + step * i) for i, v in enumerate(values)]


def _wave(n, seed, noise):
	rng = random.Random(seed)
	return [60 + 15 * sin(i / rng.choice((6, 9, 14))) + rng.random() * noise for i in range(n)]


def _summary(found):
	return [(float(i.value), i.timestamp, i.isPeak, i.index) for i in found]


@pytest.mark.parametrize('n', [0, 1, 2, 3, 10, 97, 240])
@pytest.mark.parametrize('seed,noise', [(1, 0.0), (2, 0.3), (3, 2.0)])
@pytest.mark.parametrize('spread,group', [(9, 5), (9, 24), (3, 1), (40, 6)])
def test_matches_original(n, seed, noise, spread, group):
	array = _series(_wave(n, seed, noise))
	new = findPeaksAndTroughs(array, spread=timedelta(hours=spread), groupingSize=timedelta(hours=group))
	oldRes = _findOld(array, timedelta(hours=spread), timedelta(hours=group))
	assert _summary(new) == _summary(oldRes)


def test_flat_series_and_plateaus():
	array = _series([50.0] * 30 + [51.0] * 5 + [50.0] * 30)
	new = findPeaksAndTroughs(array, spread=timedelta(hours=9), groupingSize=timedelta(hours=6))
	assert _summary(new) == _summary(_findOld(array, timedelta(hours=9), timedelta(hours=6)))


def test_extrema_windows_fall_back_to_the_ends():
	out = neighbourExtrema([1.0, 2.0, 3.0], [0, 1, 2], 100)
	assert out[0][:2] == (1.0, 1.0)  # nothing behind the first sample: itself
	assert out[-1][2:] == (3.0, 3.0)  # nothing ahead of the last


def _findOld(array: Sequence['TimeAwareValue'], spread: timedelta = 12, groupingSize: timedelta | int = 6) -> List['TimeAwareValue']:
	start_time = time.perf_counter()
	peaks = []
	troughs = []
	if isinstance(groupingSize, int):
		groupingSize = timedelta(hours=groupingSize)
	groupGenerator = TemporalGroups(array, spread=spread)
	peak_flat = False
	trough_flat = False
	for i, node, behind, ahead in groupGenerator:
		if not ahead:
			ahead = [array[-1]]
		if not behind:
			behind = [array[0]]

		if float(min(behind).value) >= node <= float(min(ahead).value):
			if troughs and datetimeDiff(troughs[-1].timestamp, node.timestamp) <= groupingSize:
				troughs[-1] += node
				trough_flat = True
			else:
				if trough_flat:
					troughs[-1] = troughs[-1].flattened
					trough_flat = False
				troughs.append(node)

		elif float(max(behind).value) <= node >= float(max(ahead).value):
			if peaks and datetimeDiff(peaks[-1].timestamp, node.timestamp) <= groupingSize:
				peaks[-1] += node
				peak_flat = True
			else:
				if peak_flat:
					peaks[-1] = peaks[-1].flattened
					peak_flat = False
				peaks.append(node)
	log.verbose(f"findPeaksAndTroughs() {time.perf_counter() - start_time: 0.3g}s for {len(array)} items", verbosity=4)

	merged = []
	peaks = sorted(peaks, key=lambda x: x.timestamp)
	troughs = sorted(troughs, key=lambda x: x.timestamp)
	index = 0
	while peaks or troughs:
		toPop = min(peaks, troughs, key=lambda x: x[0].timestamp.timestamp() if x else inf)
		next_ = toPop.pop(0)
		next_.isPeak = toPop is peaks
		next_.index, index = index, index + 1
		merged.append(next_)
	return merged


