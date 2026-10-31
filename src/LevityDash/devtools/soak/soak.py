#!/usr/bin/env python
"""Soak test for remote mode: backend and frontend as real processes on a warped clock, fed by fake data.

    python soak.py --hours 72 --speed 30 --out /tmp/soak

See ``--help``. Writes ``backend.out``, ``frontend.out``, the probe files and ``report.md`` into ``--out``.
Exit status is 0 only when every check passed.
"""
import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
REPO_DASHBOARD = HERE.parents[3] / 'docs' / 'tasks' / 'lambda-cross-section.levity'


def freePort() -> int:
	with socket.socket() as s:
		s.bind(('127.0.0.1', 0))
		return s.getsockname()[1]


def waitForPort(port: int, timeout: float, process: subprocess.Popen) -> bool:
	deadline = time.monotonic() + timeout
	while time.monotonic() < deadline:
		if process.poll() is not None:
			return False
		with socket.socket() as s:
			s.settimeout(0.2)
			if s.connect_ex(('127.0.0.1', port)) == 0:
				return True
		time.sleep(0.2)
	return False


def parseArgs(argv=None):
	p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
	p.add_argument('--hours', type=float, default=24, help='virtual hours to run (default 24)')
	p.add_argument('--speed', type=float, default=12, help="virtual seconds per real second (default 12)")
	p.add_argument('--start', default='2026-10-31T18:00', help='virtual start, local time (default the evening before the US fall-back); none leaves the clock alone')
	p.add_argument('--tz', default='America/New_York')
	p.add_argument('--out', type=Path, default=Path('soak-out'))
	p.add_argument('--dashboard', type=Path, default=REPO_DASHBOARD)
	p.add_argument('--jump', action='append', default=[], metavar='AT:DELTA',
		help='step the wall clock DELTA seconds once AT virtual seconds have passed, e.g. 21600:+3720 (a laptop waking up); repeatable')
	p.add_argument('--probe-every', type=float, default=300, help='virtual seconds between probe samples (default 300)')
	p.add_argument('--fault-every', type=int, default=0, help='make every Nth feed request a 500 (default off)')
	p.add_argument('--govee-period', type=float, default=10, help='virtual seconds between Govee advertisements (default 10)')
	p.add_argument('--keep-running', action='store_true', help='skip the final checks and leave the children up (debugging)')
	return p.parse_args(argv)


def main(argv=None) -> int:
	args = parseArgs(argv)
	out = args.out.resolve()
	if out.exists():
		shutil.rmtree(out)
	out.mkdir(parents=True)
	seed = out / 'seed'
	shutil.copytree(HERE / 'seed', seed)
	(seed / 'saves' / 'dashboards').mkdir(parents=True)
	shutil.copy(args.dashboard, seed / 'saves' / 'dashboards' / 'default.levity')

	port = freePort()
	env = {
		**os.environ,
		'LEVITYDASH_CONFIG_DEBUG': '1', 'LEVITYDASH_CONFIG_SEED': str(seed), 'QT_QPA_PLATFORM': 'offscreen',
		'LEVITYDASH_BACKEND_HOST': '127.0.0.1', 'LEVITYDASH_BACKEND_PORT': str(port),
		'LEVITYDASH_BACKEND_URL': f'ws://127.0.0.1:{port}/ws', 'PYTHONUNBUFFERED': '1',
		'LEVITYDASH_SOAK_OUT': str(out), 'LEVITYDASH_SOAK_SPEED': str(args.speed), 'LEVITYDASH_SOAK_START': '' if args.start == 'none' else args.start,
		'LEVITYDASH_SOAK_TZ': '' if args.start == 'none' else args.tz, 'LEVITYDASH_SOAK_JUMPS': ','.join(args.jump),
		'LEVITYDASH_SOAK_PROBE_EVERY': str(args.probe_every), 'LEVITYDASH_SOAK_FAULT_EVERY': str(args.fault_every),
		'LEVITYDASH_SOAK_GOVEE_PERIOD': str(args.govee_period),
	}
	env.pop('LEVITYDASH_BACKEND_MODE', None)

	def spawn(role: str, extra: dict) -> subprocess.Popen:
		log = open(out / f'{role}.out', 'wb')
		return subprocess.Popen(
			[sys.executable, str(HERE / '_child.py'), role], env={**env, **extra}, stdout=log, stderr=subprocess.STDOUT, cwd=out,
		)

	real0 = time.time()
	backend = spawn('backend', {'LEVITYDASH_PROCESS_ROLE': 'backend'})
	if not waitForPort(port, 90, backend):
		print(f'backend did not come up; see {out / "backend.out"}', file=sys.stderr)
		return 2
	frontend = spawn('frontend', {'LEVITYDASH_PROCESS_ROLE': 'frontend', 'LEVITYDASH_BACKEND_MODE': 'remote'})

	import psutil
	children = {'backend': psutil.Process(backend.pid), 'frontend': psutil.Process(frontend.pid)}
	duration = args.hours * 3600 / args.speed
	print(f'soak: {args.hours:g} virtual hours at x{args.speed:g} = {duration / 60:.1f} real minutes; out {out}', flush=True)
	died = None
	with open(out / 'procs.jsonl', 'a') as procs:
		for p in children.values():
			p.cpu_percent(None)
		deadline = time.time() + duration
		while time.time() < deadline:
			time.sleep(10)
			row = {'real': round(time.time() - real0, 1)}
			for name, proc in children.items():
				if proc.poll() if hasattr(proc, 'poll') else False:
					pass
			for name, popen in (('backend', backend), ('frontend', frontend)):
				if popen.poll() is not None:
					died = (name, popen.returncode)
					row[name] = {'exited': popen.returncode}
					continue
				try:
					row[name] = {
						'rssMB': round(children[name].memory_info().rss / 2 ** 20, 1), 'cpu': children[name].cpu_percent(None),
						'threads': children[name].num_threads(),
					}
				except psutil.Error:
					row[name] = {'gone': True}
			procs.write(json.dumps(row) + '\n')
			procs.flush()
			if died:
				print(f'soak: {died[0]} exited with {died[1]}', file=sys.stderr, flush=True)
				break
			if int(row['real']) % 300 < 10:
				print(f'soak: real +{row["real"]:.0f}s {json.dumps({k: v for k, v in row.items() if k != "real"})}', flush=True)

	if args.keep_running:
		print('soak: children left running', backend.pid, frontend.pid)
		return 0
	for popen in (frontend, backend):
		if popen.poll() is None:
			popen.send_signal(signal.SIGTERM)
	for popen in (frontend, backend):
		try:
			popen.wait(30)
		except subprocess.TimeoutExpired:
			popen.kill()

	import analyze
	return analyze.run(out, args, died)


if __name__ == '__main__':
	raise SystemExit(main())
