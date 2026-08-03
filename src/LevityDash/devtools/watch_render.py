#!/usr/bin/env python
"""Dev-only: watch a `.levity` file and keep a PNG preview of it current.

For prototyping one panel/section rather than a whole dashboard - point this
at a small fragment file (a single top-level item, same shape as anything
under `docs/design-references/`) and it becomes a live-updating image: edit,
save, look.

Needs a running `render_service.py` - this script is a thin HTTP client, it
does not boot Qt itself. Start one first:

    poetry run python src/LevityDash/devtools/render_service.py --seed <config-copy>

Then, in another terminal:

    poetry run python src/LevityDash/devtools/watch_render.py \\
        docs/design-references/temperature-column.levity

Open the output PNG (`preview.png` next to the source file, by default) in
**Preview.app**, not Quick Look - Preview watches the file on disk and reloads
it automatically when it changes; Quick Look does not, and you would have to
reopen it after every save. Every edit-save cycle then just re-renders in
place.

Uses `/load` (switch the running service to this file) then `/render`, as two
separate requests with a real pause between them - same reason `/preview` needs
that pause (see its docstring in render_service.py): rendering immediately
after a load can return a black frame before the scene has finished settling.
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_SETTLE = 2.0
DEFAULT_INTERVAL = 0.5


def _post(url: str, payload: dict) -> None:
	body = json.dumps(payload).encode('utf-8')
	request = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json'}, method='POST')
	with urllib.request.urlopen(request, timeout=30) as response:
		response.read()


def _get(url: str) -> bytes:
	with urllib.request.urlopen(url, timeout=30) as response:
		return response.read()


def renderOnce(base: str, path: Path, out: Path, settle: float, scale: float) -> None:
	_post(f'{base}/load', {'path': str(path.resolve())})
	time.sleep(settle)  # let deferred layout/settle work drain - see module docstring
	png = _get(f'{base}/render?scale={scale}')
	out.write_bytes(png)


def main() -> int:
	parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
	parser.add_argument('file', help='the .levity fragment to watch')
	parser.add_argument('--out', help='PNG path (default: preview.png next to the source file)')
	parser.add_argument('--host', default='127.0.0.1')
	parser.add_argument('--port', type=int, default=8670)
	parser.add_argument('--settle', type=float, default=DEFAULT_SETTLE, help='pause between load and render')
	parser.add_argument('--interval', type=float, default=DEFAULT_INTERVAL, help='mtime poll interval')
	parser.add_argument('--scale', type=float, default=1.0)
	args = parser.parse_args()

	source = Path(args.file)
	if not source.exists():
		parser.error(f'no such file: {source}')
	out = Path(args.out) if args.out else source.with_name('preview.png')
	base = f'http://{args.host}:{args.port}'

	try:
		_get(f'{base}/health')
	except (urllib.error.URLError, ConnectionError) as e:
		parser.error(f'no render service at {base} ({e}) - start one first, see this script\'s docstring')

	print(f'watching {source} -> {out}  (ctrl-c to stop)')
	lastMtime = None
	try:
		while True:
			mtime = source.stat().st_mtime
			if mtime != lastMtime:
				lastMtime = mtime
				started = time.monotonic()
				try:
					renderOnce(base, source, out, args.settle, args.scale)
				except (urllib.error.URLError, ConnectionError) as e:
					print(f'  render failed: {e}', file=sys.stderr)
				else:
					print(f'  rendered in {time.monotonic() - started:.2f}s')
			time.sleep(args.interval)
	except KeyboardInterrupt:
		return 0


if __name__ == '__main__':
	raise SystemExit(main())
