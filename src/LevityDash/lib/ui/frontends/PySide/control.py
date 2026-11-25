"""Hand a dashboard file to the running window, over a local socket.

The GUI process owns the socket. A second `levitydash --dashboard PATH` connects to it first, so showing
another dashboard neither starts a second app nor touches `[Display] dashboard` in the config. The wire
connection in `lib/wire/` cannot carry this: it belongs to the backend, the backend may be on another
machine, and the file path is local to the window.

Protocol — one newline-delimited JSON object each way::

    -> {"v": 2, "id": "...", "cmd": "open", "dashboard": "/abs/x.levity", "window": "current"}
    <- {"v": 2, "id": "...", "ok": true, "dashboard": "/abs/x.levity", "window": "Levity Dashboard - x.levity",
        "windows": [{"id": "main", "title": "...", "dashboard": "/abs/x.levity", "screen": "Built-in", "pid": 42}]}

`cmd` is `open`, `status` or `ping`; `list`, `focus`, `close`, `move` and `workspace` are reserved for the
multi-window protocol and answer `not_implemented` until there is something to act on. `window` is `current`
or `main` (the one window this process has); `new` answers `not_implemented` until a second window exists in
one process. Every handler goes through `dispatch`, so anything that wants to drive the window later (the
debug server, a wire relay) calls the same table instead of repeating the lookups.

A failure is never a bare string: `{"ok": false, "error": {"code": ..., "message": ...}}` with `code` one of
`not_found | not_implemented | busy | bad_request`. The CLI turns that code into an exit status
(`EXIT_CODES`), so a script can tell "no such file" from "the window is busy" without parsing English.

This module is Qt-free on purpose: the client half runs before any `QApplication` exists (a handoff exits
without one), so it speaks plain AF_UNIX. The listener lives in `control_server.py`.

The socket path never comes from `$TMPDIR`. A GUI started from Finder has a per-session TMPDIR under
`/var/folders/...`, while a client over ssh usually has none — the two would disagree and the handoff would
silently fail.

Two windows are two processes: the first owns `/tmp/levitydash-<uid>.sock`, a `--new-instance` window owns
`/tmp/levitydash-<uid>-<id>.sock` (`setSocketId`). It registers itself with the primary (`cmd: register`) so
`status` on the primary lists both; a registered window whose process is gone is dropped on the next read.
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

PROTOCOL_VERSION = 2
#: Seconds a client waits for the reply. A large board on a slow machine takes a while to build.
DEFAULT_TIMEOUT_S = 15.0

#: The socket lives here. Not `$TMPDIR` — see the module docstring.
_SOCKET_DIR = '/tmp'
#: Set by `--new-instance` before the app starts; None is the primary window and owns the plain path.
_SOCKET_ID: str | None = None

#: The four protocol error codes, and the exit status each one becomes on the CLI.
EXIT_CODES = {'not_found': 3, 'bad_request': 4, 'not_implemented': 5, 'busy': 6}

#: Windows that registered themselves with this one (`cmd: register`), keyed by window id.
_REGISTERED: dict[str, dict] = {}


class ControlError(Exception):
	"""A request that cannot be carried out, reported to the client instead of raised at it."""

	def __init__(self, message: str, code: str = 'bad_request'):
		super().__init__(message)
		self.code = code


def error(code: str, message: str) -> dict:
	"""One failure, in the shape every reply uses."""
	return {'code': code, 'message': message}


def setSocketId(id: str | None) -> None:
	"""Give this process its own socket (`--new-instance`). `None` returns it to the primary's path."""
	global _SOCKET_ID
	_SOCKET_ID = id or None


def socketId() -> str | None:
	return _SOCKET_ID


def socketPath(id: str | None = None) -> str:
	"""The socket both sides use: one absolute path, computed the same way, never from `$TMPDIR`.

	`LEVITYDASH_CONTROL_SOCKET` wins over everything, which is how tests and a second app on the same machine
	stay apart. `id` (or, when omitted, this process's own id) names a second window; an empty string asks for
	the primary's path explicitly.
	"""
	if override := os.environ.get('LEVITYDASH_CONTROL_SOCKET'):
		return override
	id = _SOCKET_ID if id is None else id
	base = f'{_SOCKET_DIR}/levitydash-{os.getuid()}'
	return f'{base}-{id}.sock' if id else f'{base}.sock'


def encode(payload: dict) -> bytes:
	return json.dumps(payload, separators=(',', ':')).encode('utf-8') + b'\n'


def primarySocketPath() -> str:
	"""The socket of the window that started first — the one a second instance registers with."""
	return socketPath(id='')


def connect(path: str | None = None, wait: float = 3.0) -> socket.socket | None:
	"""A connected socket to the running window, or None when there is none.

	A socket file that exists but refuses is a window that is starting or stopping: give it `wait` seconds.
	No file at all means no window, and waiting would delay every ordinary launch by the full wait.
	"""
	path = socketPath() if path is None else path
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


def request(payload: dict, timeout: float = DEFAULT_TIMEOUT_S, path: str | None = None, wait: float = 3.0) -> dict | None:
	"""Send one request to a running window and return its reply.

	Returns None when nothing is listening — the caller then starts a normal process. Everything else,
	including a timeout, comes back as a reply with `ok: False`, so the caller has one failure shape.
	"""
	body = {'v': PROTOCOL_VERSION, 'id': str(uuid.uuid4()), **payload}
	sock = connect(path, wait)
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
		return {'v': PROTOCOL_VERSION, 'id': body['id'], 'ok': False, 'error': error('busy', f'no reply within {timeout:.0f}s')}
	except OSError as e:
		return {'v': PROTOCOL_VERSION, 'id': body['id'], 'ok': False, 'error': error('busy', f'the connection failed: {e}')}
	finally:
		sock.close()
	line = buffer.split(b'\n', 1)[0]
	if not line:
		return {'v': PROTOCOL_VERSION, 'id': body['id'], 'ok': False, 'error': error('busy', 'the window closed the connection without a reply')}
	try:
		return json.loads(line)
	except ValueError:
		return {'v': PROTOCOL_VERSION, 'id': body['id'], 'ok': False, 'error': error('bad_request', f'reply was not JSON: {line[:200]!r}')}


def sendOnly(payload: dict, wait: float = 0.5) -> bool:
	"""Write one request and close, without reading the reply — `--no-wait`.

	False when nothing is listening. The write is complete once `sendall` returns: closing an AF_UNIX socket
	keeps what is already in the peer's queue, so the window still acts on it.
	"""
	body = {'v': PROTOCOL_VERSION, 'id': str(uuid.uuid4()), **payload}
	sock = connect(wait=wait)
	if sock is None:
		return False
	try:
		sock.sendall(encode(body))
		try:
			sock.shutdown(socket.SHUT_WR)
		except OSError:
			pass
		return True
	except OSError:
		return False
	finally:
		sock.close()


def targetPanel(window: str | None = None):
	"""The panel a request acts on. Today there is one window; N windows is why this is a function."""
	from LevityDash import LevityDashboard

	if window == 'new':
		raise ControlError('a second window is not available yet; use --new-instance for a second process', 'not_implemented')
	if window not in (None, '', 'current', 'main'):
		raise ControlError(f'window {window!r} is not a window; use "current", "main" or "new"', 'bad_request')
	panel = getattr(LevityDashboard, 'CENTRAL_PANEL', None)
	if panel is None:
		raise ControlError('no dashboard window is open', 'not_found')
	return panel


def _checkDashboard(pathText: str) -> Path:
	"""Validate the file before the window opens it: a bad path must not put a modal box in front of a load."""
	path = Path(pathText).expanduser()
	if not path.is_absolute():
		raise ControlError(f'{pathText!r} is not an absolute path; the client resolves it before sending')
	if not path.is_file():
		raise ControlError(f'{path} is not a file', 'not_found')
	try:
		data = yaml.safe_load(path.read_text(encoding='utf-8'))
	except (OSError, yaml.YAMLError) as e:
		raise ControlError(f'{path} could not be read as YAML: {e}') from e
	if not isinstance(data, (list, dict)):
		raise ControlError(f'{path} is not a dashboard: the top level is {type(data).__name__}, not a list or a mapping')
	return path


def _title(panel) -> str:
	"""The window title, which carries the dashboard's file name."""
	try:
		return panel.scene().view.parentWidget().windowTitle()
	except Exception:  # noqa: BLE001 - a reply without a title is still a reply
		return ''


def _screen(panel) -> str | None:
	"""The screen this window is on. A widget with no handle yet has none, and that is not an error."""
	try:
		return panel.scene().views()[0].screen().name()
	except Exception:  # noqa: BLE001 - the offscreen platform has no named screen
		return None


def _loadedPath(panel) -> str | None:
	loaded = getattr(panel, 'loadedFile', None)
	path = panel._path(loaded) if loaded is not None else None
	return str(path) if path is not None else None


def windowInfo(panel, id: str = 'main') -> dict:
	"""One entry of `status`'s `windows`: enough for a client to tell two windows apart."""
	return {'id': id, 'title': _title(panel), 'dashboard': _loadedPath(panel), 'screen': _screen(panel), 'pid': os.getpid()}


def _alive(pid) -> bool:
	"""Whether `pid` names a live process. 0 and negatives mean a process group, not a window, so they are not."""
	try:
		pid = int(pid)
	except (TypeError, ValueError):
		return False
	if pid <= 0:
		return False
	try:
		os.kill(pid, 0)
	except OSError:
		return False
	return True


def _windows() -> list[dict]:
	"""Every window this process knows about: its own, plus the ones that registered with it.

	A registered window whose process is gone is dropped here rather than left to look live forever.
	"""
	from LevityDash import LevityDashboard

	windows = []
	if (panel := getattr(LevityDashboard, 'CENTRAL_PANEL', None)) is not None:
		windows.append(windowInfo(panel))
	for key, info in list(_REGISTERED.items()):
		if _alive(info.get('pid')):
			windows.append(info)
		else:
			_REGISTERED.pop(key, None)
	return windows


def _open(payload: dict) -> dict:
	panel = targetPanel(payload.get('window'))
	path = _checkDashboard(payload.get('dashboard') or '')
	# interactive=False: a caller with no one in front of the window must not be answered with a dialog it
	# cannot dismiss. The checks above make the two dialog paths in `_load` unreachable anyway.
	panel._load(path, interactive=False)
	return {'ok': True, 'dashboard': str(path), 'window': _title(panel), 'windows': _windows()}


def _status(payload: dict) -> dict:
	panel = targetPanel(payload.get('window'))
	windows = _windows()
	return {'ok': True, 'dashboard': _loadedPath(panel), 'window': _title(panel), 'windows': windows}


def _ping(payload: dict) -> dict:
	from LevityDash import LevityDashboard

	return {'ok': True, 'app': 'LevityDash', 'version': str(LevityDashboard.__version__), 'pid': os.getpid()}


def _register(payload: dict) -> dict:
	"""A second instance telling the primary it exists, so the primary's `status` lists it too."""
	info = payload.get('window')
	if not isinstance(info, dict) or not info.get('id'):
		raise ControlError('register needs a window object with an id')
	_REGISTERED[str(info['id'])] = {**info, 'pid': info.get('pid') or os.getpid()}
	return {'ok': True, 'registered': str(info['id'])}


def _reserved(name: str) -> Callable[[dict], dict]:
	"""A verb the multi-window protocol reserves: the name is taken, the work is not done yet."""

	def handler(payload: dict) -> dict:
		raise ControlError(f'{name} is reserved for multi-window support and is not implemented yet', 'not_implemented')

	handler.__name__ = f'_{name}'
	return handler


#: The one table every caller uses: the socket's server, and anything later that wants to drive the window.
COMMANDS: dict[str, Callable[[dict], dict]] = {
	'open': _open,
	'status': _status,
	'ping': _ping,
	'register': _register,
	'list': _reserved('list'),
	'focus': _reserved('focus'),
	'close': _reserved('close'),
	'move': _reserved('move'),
	'workspace': _reserved('workspace'),
}


def dispatch(payload: dict) -> dict:
	"""Carry out one request and return the reply. Never raises: the reply is how a failure is reported."""
	reply = {'v': PROTOCOL_VERSION, 'id': payload.get('id')}
	try:
		command = COMMANDS.get(payload.get('cmd') or '')
		if command is None:
			raise ControlError(f'unknown command {payload.get("cmd")!r}; known: {", ".join(sorted(COMMANDS))}')
		reply.update(command(payload))
	except ControlError as e:
		reply.update(ok=False, error=error(e.code, str(e)))
	except Exception as e:  # noqa: BLE001 - the window's state is not worth crashing the socket for
		reply.update(ok=False, error=error('busy', f'{type(e).__name__}: {e}'))
	return reply


def exitCode(reply: dict | None) -> int:
	"""The process status a reply means: 0 for success, the code's number for a failure, 1 for anything else."""
	if reply is None:
		return 1
	if reply.get('ok'):
		return 0
	failure = reply.get('error')
	code = failure.get('code') or '' if isinstance(failure, dict) else ''
	return EXIT_CODES.get(code, 1)


#: The name the app's entry point uses for the client call; it is a plain request.
handOff = request


def announceSecondary(window: dict) -> bool:
	"""Tell the primary this window exists. False when there is no primary, or it did not answer.

	Never called from the primary itself: it would be asking its own socket from the thread that answers it.
	"""
	primary = primarySocketPath()
	if primary == socketPath():
		return False
	reply = request({'cmd': 'register', 'window': window}, timeout=2.0, path=primary, wait=0.2)
	return bool(reply and reply.get('ok'))


def announceSecondaryInBackground(window: dict) -> None:
	"""Register this window with the primary off the GUI thread: the primary may be busy building a board.

	`window` is built by the caller on the GUI thread (it reads Qt widgets); only the socket write happens here.
	"""
	from threading import Thread

	def run():
		try:
			announceSecondary(window)
		except Exception:  # noqa: BLE001 - a window that cannot announce itself is still a window
			pass

	Thread(target=run, daemon=True, name='control-register').start()


def otherWindowHasOpen(path) -> bool:
	"""Whether another live window reports `path` as loaded — the check behind the shared-save log line.

	Two directions: a window that registered with this one (this process is the primary), and the primary
	itself, which a second instance asks over its socket because that is the only way it can see its
	siblings. From the primary, the second half is always False: the socket is answered by the thread that
	would be asking.
	"""
	target = str(Path(path).absolute())
	# This window's own registration would otherwise match a file it just saved itself.
	if any(
		info.get('dashboard') == target and info.get('pid') != os.getpid() and _alive(info.get('pid'))
		for info in _REGISTERED.values()
	):
		return True
	primary = primarySocketPath()
	if primary == socketPath():
		return False
	reply = request({'cmd': 'status'}, timeout=0.75, path=primary, wait=0.1)
	if not reply or not reply.get('ok'):
		return False
	return any(w.get('dashboard') == target and w.get('pid') != os.getpid() for w in reply.get('windows') or ())


def resolveDashboardArgument(text: str) -> Path:
	"""Resolve `--dashboard` against the *client's* working directory.

	The running window has its own working directory, so a relative path sent as-is would be read against
	the wrong place.
	"""
	return Path(text).expanduser().resolve()


def main(argv: list[str] | None = None) -> int:
	"""`python -m LevityDash.lib.ui.frontends.PySide.control status` — a small probe for scripts and agents."""
	argv = list(sys.argv[1:] if argv is None else argv)
	noWait = '--no-wait' in argv
	argv = [arg for arg in argv if arg != '--no-wait']
	command = argv[0] if argv else 'status'
	payload = {'cmd': command}
	if command == 'open':
		if len(argv) < 2:
			print('usage: control open PATH', file=sys.stderr)
			return 2
		payload['dashboard'] = str(resolveDashboardArgument(argv[1]))
	if noWait:
		# Fire and forget: a slow board must not hold a script up, and the reply is not wanted.
		if not sendOnly(payload):
			print(f'no running LevityDash window on {socketPath()}', file=sys.stderr)
			return 1
		return 0
	reply = request(payload)
	if reply is None:
		print(f'no running LevityDash window on {socketPath()}', file=sys.stderr)
		return 1
	print(json.dumps(reply, indent=2))
	return exitCode(reply)


if __name__ == '__main__':
	raise SystemExit(main())
