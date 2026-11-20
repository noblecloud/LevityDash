"""A loopback screenshot server inside the frontend, for a display nobody is looking at.

``screencapture`` run over SSH cannot read another session's windows without a Screen Recording grant, so the
frontend draws its own window instead. Qt needs no OS permission to read its own pixels.

Off by default. Set this in the config, then restart::

	[Debug]
	screenshot-port = 8671

``GET http://127.0.0.1:<port>/screenshot`` answers a PNG. Options: ``?mode=scene`` (default, ``QGraphicsScene.render``,
no GL context involved; glow effects come out flat) or ``?mode=window`` (the real window, ``QWidget.grab``);
``?scale=`` (0.1 to 4, default 1). ``GET /health`` answers 200. The server binds 127.0.0.1 only; reach it from another
machine with ``ssh host curl -s localhost:<port>/screenshot > out.png``.
"""
from concurrent.futures import Future
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import parse_qs, urlparse

from PySide6.QtCore import QBuffer, QByteArray, QObject, QRectF, Qt, Signal, Slot
from PySide6.QtGui import QImage, QPainter


class _Grabber(QObject):
	"""Lives on the GUI thread; a request thread hands it a ``Future`` and waits on that."""
	requested = Signal(object)

	def __init__(self, window):
		super().__init__()
		self.window = window
		self.requested.connect(self._grab, Qt.ConnectionType.QueuedConnection)

	@Slot(object)
	def _grab(self, job):
		future, mode, scale = job
		try:
			future.set_result(self.png(mode, scale))
		except Exception as e:  # noqa: BLE001 - the caller reports it as a 500
			future.set_exception(e)

	def png(self, mode: str, scale: float) -> bytes:
		if mode == 'window':
			image = self.window.grab().toImage()
			if scale != 1.0:
				image = image.scaledToWidth(max(1, round(image.width() * scale)), Qt.TransformationMode.SmoothTransformation)
		else:
			from LevityDash.lib.ui.colors import theme
			scene = self.window.view.scene()
			rect = scene.sceneRect()
			image = QImage((rect.size() * scale).toSize(), QImage.Format.Format_ARGB32)
			image.fill(theme.color('background').QColor)
			painter = QPainter(image)
			painter.setRenderHint(QPainter.RenderHint.Antialiasing)
			scene.render(painter, QRectF(image.rect()), rect)
			painter.end()
		data = QByteArray()
		buffer = QBuffer(data)
		buffer.open(QBuffer.OpenModeFlag.WriteOnly)
		image.save(buffer, 'PNG')
		buffer.close()
		return bytes(data)


def start(window, port: int) -> ThreadingHTTPServer:
	"""Serve ``window`` on ``127.0.0.1:port`` from a daemon thread."""
	grabber = _Grabber(window)

	class Handler(BaseHTTPRequestHandler):
		def log_message(self, *args):  # silence the per-request line
			pass

		def _send(self, code: int, body: bytes, kind: str = 'text/plain'):
			self.send_response(code)
			self.send_header('Content-Type', kind)
			self.send_header('Content-Length', str(len(body)))
			self.end_headers()
			self.wfile.write(body)

		def do_GET(self):
			url = urlparse(self.path)
			if url.path == '/health':
				return self._send(200, b'ok')
			if url.path != '/screenshot':
				return self._send(404, b'try /screenshot')
			query = parse_qs(url.query)
			mode = query.get('mode', ['scene'])[0]
			try:
				scale = min(4.0, max(0.1, float(query.get('scale', ['1'])[0])))
			except ValueError:
				return self._send(400, b'scale must be a number')
			if mode not in ('scene', 'window'):
				return self._send(400, b'mode is scene or window')
			future: Future = Future()
			grabber.requested.emit((future, mode, scale))
			try:
				self._send(200, future.result(timeout=20), 'image/png')
			except Exception as e:  # noqa: BLE001
				self._send(500, f'{type(e).__name__}: {e}'.encode())

	server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
	server.grabber = grabber  # keep the QObject alive as long as the server
	Thread(target=server.serve_forever, name='screenshot', daemon=True).start()
	return server
