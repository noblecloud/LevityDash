"""The GUI side of the dashboard handoff: listen on the local socket and answer each request.

Split from `control.py` so the client half stays Qt-free — a `--dashboard` handoff exits before any
`QApplication` exists. Owned by `LevityDashApp._startControlServer`; the handlers run in the GUI thread
because the server was created there, so no marshalling is needed (unlike the wire's `_GuiMarshal`).
"""
import json
import os

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from .control import PROTOCOL_VERSION, dispatch, encode, error, socketPath


class ControlServer(QObject):
	"""Listen on the local socket, answer each connection, and report each reply it sent."""

	requestHandled = Signal(dict)

	def __init__(self, parent: QObject | None = None):
		super().__init__(parent)
		self.server = QLocalServer(self)
		self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
		self.server.newConnection.connect(self._accept)
		self._buffers: dict[int, bytes] = {}

	def listen(self) -> bool:
		path = socketPath()
		# Never take the socket from a window that is answering: two instances racing to start would
		# otherwise leave the handoff pointed at whichever one called removeServer last.
		probe = QLocalSocket()
		probe.connectToServer(path)
		if probe.waitForConnected(200):
			probe.abort()
			return False
		probe.abort()
		# A crashed instance leaves its name behind; removing it first is idempotent when there is none.
		QLocalServer.removeServer(path)
		if not self.server.listen(path):
			return False
		try:
			os.chmod(path, 0o600)
		except OSError:
			pass
		return True

	def close(self) -> None:
		self.server.close()
		try:
			os.unlink(socketPath())
		except OSError:
			pass

	def _accept(self) -> None:
		while (socket := self.server.nextPendingConnection()) is not None:
			key = id(socket)
			self._buffers[key] = b''
			socket.readyRead.connect(lambda s=socket, k=key: self._read(s, k))
			socket.disconnected.connect(lambda k=key: self._buffers.pop(k, None))

	def _read(self, socket: QLocalSocket, key: int) -> None:
		self._buffers[key] = self._buffers.get(key, b'') + bytes(socket.readAll().data())
		if b'\n' not in self._buffers[key]:
			return
		line, _, rest = self._buffers[key].partition(b'\n')
		self._buffers[key] = rest
		try:
			payload = json.loads(line)
		except ValueError:
			# An id-less reply: nothing in the line can be trusted, but the shape still has to match.
			reply = {'v': PROTOCOL_VERSION, 'ok': False, 'error': error('bad_request', f'request was not JSON: {line[:200]!r}')}
		else:
			reply = dispatch(payload)
		self.requestHandled.emit(reply)
		socket.write(encode(reply))
		socket.flush()
		socket.disconnectFromServer()
