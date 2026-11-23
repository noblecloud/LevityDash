"""Hand a dashboard file to the running window, over a local socket.

The GUI process owns the socket. A second `levitydash --dashboard PATH` connects to it first, so showing
another dashboard neither starts a second app nor touches `[Display] dashboard` in the config. The wire
connection in `lib/wire/` cannot carry this: it belongs to the backend, the backend may be on another
machine, and the file path is local to the window.

Protocol — one newline-delimited JSON object each way::

    -> {"v": 1, "id": "...", "cmd": "open", "dashboard": "/abs/x.levity", "window": "current"}
    <- {"v": 1, "id": "...", "ok": true, "dashboard": "/abs/x.levity", "window": "Levity Dashboard - x.levity"}

`cmd` is `open`, `status` or `ping`. `window` is `current`; `new` is reserved for a second window and
answers "not implemented" until there is one. Every handler goes through `dispatch`, so anything that wants
to drive the window later (the debug server, a wire relay) calls the same table instead of repeating the
lookups.

This module is Qt-free on purpose: the client half runs before any `QApplication` exists (a handoff exits
without one), so it speaks plain AF_UNIX. The listener lives in `control_server.py`.

The socket path never comes from `$TMPDIR`. A GUI started from Finder has a per-session TMPDIR under
`/var/folders/...`, while a client over ssh usually has none — the two would disagree and the handoff would
silently fail.
"""
import json
import os
import socket
import sys
import time
import uuid
from pathlib import Path
from typing import Callable

import yaml

PROTOCOL_VERSION = 1
#: Seconds a client waits for the reply. A large board on a slow machine takes a while to build.
DEFAULT_TIMEOUT_S = 15.0


class ControlError(Exception):
	"""A request that cannot be carried out, reported to the client instead of raised at it."""


def socketPath() -> str:
	"""The socket both sides use: one absolute path, computed the same way, never from `$TMPDIR`."""
	if override := os.environ.get('LEVITYDASH_CONTROL_SOCKET'):
		return override
	return f'/tmp/levitydash-{os.getuid()}.sock'


def encode(payload: dict) -> bytes:
	return json.dumps(payload, separators=(',', ':')).encode('utf-8') + b'\n'


def connect(wait: float = 3.0) -> socket.socket | None:
	"""A connected socket to the running window, or None when there is none.

	A socket file that exists but refuses is a window that is starting or stopping: give it `wait` seconds.
	No file at all means no window, and waiting would delay every ordinary launch by the full wait.
	"""
	path = socketPath()
	deadline = time.monotonic() + wait
	while True:
		sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
		try:
			sock.connect(path)
			return sock
		except OSError:
			sock.close()
		if not Path(path).exists() or time.monotonic() >= deadline:
			return None
		time.sleep(0.1)


def request(payload: dict, timeout: float = DEFAULT_TIMEOUT_S) -> dict | None:
	"""Send one request to a running window and return its reply.

	Returns None when nothing is listening — the caller then starts a normal process. Everything else,
	including a timeout, comes back as a reply with `ok: False`, so the caller has one failure shape.
	"""
	body = {'v': PROTOCOL_VERSION, 'id': str(uuid.uuid4()), **payload}
	sock = connect()
	if sock is None:
		return None
	sock.settimeout(timeout)
	try:
		sock.sendall(encode(body))
		buffer = b''
		while b'\n' not in buffer:
			chunk = sock.recv(65536)
			if not chunk:
				break
			buffer += chunk
	except TimeoutError:
		return {'v': PROTOCOL_VERSION, 'id': body['id'], 'ok': False, 'error': f'no reply within {timeout:.0f}s'}
	except OSError as error:
		return {'v': PROTOCOL_VERSION, 'id': body['id'], 'ok': False, 'error': f'the connection failed: {error}'}
	finally:
		sock.close()
	line = buffer.split(b'\n', 1)[0]
	if not line:
		return {'v': PROTOCOL_VERSION, 'id': body['id'], 'ok': False, 'error': 'the window closed the connection without a reply'}
	try:
		return json.loads(line)
	except ValueError:
		return {'v': PROTOCOL_VERSION, 'id': body['id'], 'ok': False, 'error': f'reply was not JSON: {line[:200]!r}'}


def targetPanel(window: str | None = None):
	"""The panel a request acts on. Today there is one window; N windows is why this is a function."""
	from LevityDash import LevityDashboard

	if window not in (None, '', 'current'):
		raise ControlError(f'window {window!r} is not available yet; only "current" is implemented')
	panel = getattr(LevityDashboard, 'CENTRAL_PANEL', None)
	if panel is None:
		raise ControlError('no dashboard window is open')
	return panel


def _checkDashboard(pathText: str) -> Path:
	"""Validate the file before the window opens it: a bad path must not put a modal box in front of a load."""
	path = Path(pathText).expanduser()
	if not path.is_absolute():
		raise ControlError(f'{pathText!r} is not an absolute path; the client resolves it before sending')
	if not path.is_file():
		raise ControlError(f'{path} is not a file')
	try:
		data = yaml.safe_load(path.read_text(encoding='utf-8'))
	except (OSError, yaml.YAMLError) as error:
		raise ControlError(f'{path} could not be read as YAML: {error}') from error
	if not isinstance(data, (list, dict)):
		raise ControlError(f'{path} is not a dashboard: the top level is {type(data).__name__}, not a list or a mapping')
	return path


def _title(panel) -> str:
	"""The window title, which carries the dashboard's file name."""
	try:
		return panel.scene().view.parentWidget().windowTitle()
	except Exception:  # noqa: BLE001 - a reply without a title is still a reply
		return ''


def _open(payload: dict) -> dict:
	panel = targetPanel(payload.get('window'))
	path = _checkDashboard(payload.get('dashboard') or '')
	# interactive=False: a caller with no one in front of the window must not be answered with a dialog it
	# cannot dismiss. The checks above make the two dialog paths in `_load` unreachable anyway.
	panel._load(path, interactive=False)
	return {'ok': True, 'dashboard': str(path), 'window': _title(panel)}


def _status(payload: dict) -> dict:
	panel = targetPanel(payload.get('window'))
	loaded = getattr(panel, 'loadedFile', None)
	path = panel._path(loaded) if loaded is not None else None
	return {'ok': True, 'dashboard': str(path) if path is not None else None, 'window': _title(panel)}


def _ping(payload: dict) -> dict:
	from LevityDash import LevityDashboard

	return {'ok': True, 'app': 'LevityDash', 'version': str(LevityDashboard.__version__), 'pid': os.getpid()}


#: The one table every caller uses: the socket's server, and anything later that wants to drive the window.
COMMANDS: dict[str, Callable[[dict], dict]] = {'open': _open, 'status': _status, 'ping': _ping}


def dispatch(payload: dict) -> dict:
	"""Carry out one request and return the reply. Never raises: the reply is how a failure is reported."""
	reply = {'v': PROTOCOL_VERSION, 'id': payload.get('id')}
	try:
		command = COMMANDS.get(payload.get('cmd') or '')
		if command is None:
			raise ControlError(f'unknown command {payload.get("cmd")!r}; known: {", ".join(sorted(COMMANDS))}')
		reply.update(command(payload))
	except ControlError as error:
		reply.update(ok=False, error=str(error))
	except Exception as error:  # noqa: BLE001 - the window's state is not worth crashing the socket for
		reply.update(ok=False, error=f'{type(error).__name__}: {error}')
	return reply


#: The name the app's entry point uses for the client call; it is a plain request.
handOff = request


def resolveDashboardArgument(text: str) -> Path:
	"""Resolve `--dashboard` against the *client's* working directory.

	The running window has its own working directory, so a relative path sent as-is would be read against
	the wrong place.
	"""
	return Path(text).expanduser().resolve()


def main(argv: list[str] | None = None) -> int:
	"""`python -m LevityDash.lib.ui.frontends.PySide.control status` — a small probe for scripts and agents."""
	argv = list(sys.argv[1:] if argv is None else argv)
	command = argv[0] if argv else 'status'
	payload = {'cmd': command}
	if command == 'open':
		if len(argv) < 2:
			print('usage: control open PATH', file=sys.stderr)
			return 2
		payload['dashboard'] = str(resolveDashboardArgument(argv[1]))
	reply = request(payload)
	if reply is None:
		print(f'no running LevityDash window on {socketPath()}', file=sys.stderr)
		return 1
	print(json.dumps(reply, indent=2))
	return 0 if reply.get('ok') else 1


if __name__ == '__main__':
	raise SystemExit(main())
