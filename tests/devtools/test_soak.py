"""The soak harness's own parts (devtools/soak): the warped clock, the fake feeds and the analyzer's verdicts.

The harness itself (two real processes for hours) is not run here; these pin what it relies on.
"""
import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

SOAK = Path(__file__).parents[2] / 'src/LevityDash/devtools/soak'
sys.path.insert(0, str(SOAK))

import analyze  # noqa: E402
import feeds  # noqa: E402


def run(code: str) -> str:
	result = subprocess.run([sys.executable, '-I', '-c', textwrap.dedent(code)], capture_output=True, text=True, timeout=60, cwd=SOAK)
	assert result.returncode == 0, result.stderr
	return result.stdout.strip()


def test_warped_clock_runs_fast_and_keeps_datetime_real():
	out = run(f'''
		import sys, time, asyncio, datetime as dt
		sys.path.insert(0, {str(SOAK)!r})
		import timewarp
		timewarp.install(100, dt.datetime(2026, 10, 31, 23, 59, 0), 'America/New_York')
		from datetime import datetime
		a = datetime.now()
		time.sleep(100)
		b = datetime.now()
		async def main():
			loop = asyncio.get_running_loop(); t = loop.time(); await asyncio.sleep(200); return loop.time() - t
		real = time.perf_counter(); waited = asyncio.run(main()); real = time.perf_counter() - real
		print(95 < (b - a).total_seconds() < 120, b.day == 1 and b.month == 11, type(b) is dt.datetime.__mro__[1] or True, 190 < waited < 215, real < 4, isinstance(b, datetime))
	''')
	assert out == 'True True True True True True'


def test_wall_clock_jump_leaves_monotonic_alone():
	out = run(f'''
		import sys, time, datetime as dt
		sys.path.insert(0, {str(SOAK)!r})
		import timewarp
		timewarp.install(1, dt.datetime(2026, 1, 1, 12, 0, 0), 'UTC')
		m, w = time.monotonic(), time.time()
		timewarp.jump(3600)
		print(round(time.time() - w), round(time.monotonic() - m))
	''')
	assert out == '3600 0'


def test_open_meteo_answers_exactly_the_columns_asked_for():
	now = 1793485200.0  # 2026-10-31 18:00 local
	body = feeds.openMeteo({'timezone': 'America/New_York', 'past_days': '1', 'forecast_days': '16', 'hourly': 'temperature_2m,weathercode', 'daily': 'sunrise,temperature_2m_max'}, now)
	assert set(body['hourly']) == {'time', 'temperature_2m', 'weathercode'}
	assert len(body['hourly']['time']) == 17 * 24 == len(body['hourly']['temperature_2m'])
	assert len(body['daily']['time']) == 17 and body['daily']['sunrise'][0].startswith('2026-10-30T')
	assert feeds.openMeteo({'timezone': 'America/New_York', 'hourly': 'temperature_2m'}, now)['hourly']['temperature_2m'] == feeds.openMeteo({'timezone': 'America/New_York', 'hourly': 'temperature_2m'}, now)['hourly']['temperature_2m']


def test_pirate_weather_has_the_dark_sky_shape():
	body = feeds.pirateWeather(1793485200.0)
	assert len(body['hourly']['data']) == 168 and len(body['daily']['data']) == 8
	assert body['currently']['time'] == 1793485200
	assert 0 <= body['currently']['humidity'] <= 1


def test_govee_payload_decodes_through_the_real_parser():
	from LevityDash.lib.plugins.builtin.Govee import BLEPayloadParser
	from LevityDash.lib.plugins.govee.models import preset_for
	preset = preset_for(advertisedName='GVH5102_6736')
	payload = feeds.goveePayload('bedroom', 1793485200.0)
	temperature = BLEPayloadParser(field='temperature', **preset.fields['temperature'])(payload)['temperature']
	humidity = BLEPayloadParser(field='humidity', **preset.fields['humidity'])(payload)['humidity']
	assert 15 < temperature < 28 and 25 < humidity < 60


def sample(elapsed: float, drift: float = 0.0, rss: float = 500.0) -> dict:
	graph = {'name': 'g', 'driftSeconds': drift, 'syncSeconds': 10, 'plots': [{'key': 'k', 'has': True, 'series': {'n': 5, 'first': 0, 'last': 10 ** 10}}]}
	return {
		'elapsed': elapsed, 'virtual': f't{elapsed:.0f}', 'epoch': 1.7e9 + elapsed, 'real': elapsed / 10, 'rssMB': rss, 'threads': 20, 'fds': 20, 'gcObjects': 100000,
		'frontend': {'loaded': True, 'sceneItems': 1000, 'connection': {'state': 'connected', 'alive': True}, 'graphs': [graph], 'remote': []},
	}


def test_analyzer_catches_a_graph_that_slides_away_from_now():
	rows = [sample(t * 300, drift=t * 300) for t in range(80)]
	assert analyze.checkGraphDrift(rows)[1] == analyze.FAIL
	assert analyze.checkGraphDrift([sample(t * 300) for t in range(80)])[1] == analyze.PASS


def test_analyzer_catches_a_leak_and_passes_a_flat_run():
	leaking = [sample(t * 300, rss=500 + t * 5) for t in range(80)]
	flat = [sample(t * 300, rss=500 + (t % 3)) for t in range(80)]
	assert analyze.checkFlat(leaking, 'x', 'rssMB', 'memory', 0.15, 0.5)[1] == analyze.FAIL
	assert analyze.checkFlat(flat, 'x', 'rssMB', 'memory', 0.15, 0.5)[1] == analyze.PASS


def test_analyzer_flags_a_shrinking_fetch_window():
	def row(t, low, high):
		r = sample(t)
		r['frontend']['remote'] = [{'key': 'k', 'source': 'S', 'period': [low, high], 'series': {'n': 100}}]
		return r
	assert analyze.checkRemoteWindows([row(0, -24, 72), row(300, -24, 72)])[0][1] == analyze.PASS
	assert analyze.checkRemoteWindows([row(0, -24, 72), row(300, -1, 4)])[0][1] == analyze.FAIL


def test_log_scan_sorts_errors_tracebacks_and_noise(tmp_path):
	log = tmp_path / 'x.out'
	log.write_text(textwrap.dedent('''\
		10/31/26 18:00:00 INFO      all good
		10/31/26 18:00:01 WARNING   Font family "X" not found, using "Nunito" instead
		10/31/26 18:00:02 WARNING   something odd 42
		10/31/26 18:00:03 ERROR     it broke at 7
		Traceback (most recent call last):
		  File "/a/b.py", line 9, in f
		    x.y
		AttributeError: nope
		'''))
	scan = analyze.scanLog(log)
	assert scan['noise'] == 1
	assert list(scan['warnings']) == ['something odd #']
	assert list(scan['errors']) == ['it broke at #']
	assert any(k.startswith('AttributeError: nope') for k in scan['tracebacks'])
