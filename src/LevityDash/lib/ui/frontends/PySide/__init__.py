from PySide6.QtWidgets import QApplication

from ... import UILogger

qtLogger = UILogger.getChild('Qt')


def isNewInstance() -> bool:
	"""Whether this process was started with `--new-instance` (a second window, not the first one)."""
	return bool(getattr(getattr(LevityDashboard, 'parsed_args', None), 'new_instance', False))


def screenshotPort(port: int, newInstance: bool) -> int:
	"""The port the debug screenshot server may use: a second instance gets none.

	`--new-instance` drops the server rather than picking another port: nobody can guess which port the
	second window took, and the server is a debug aid for a window nobody is looking at.
	"""
	return 0 if newInstance else port


class LevityDashApp(QApplication):

	main_window: 'LevityMainWindow'

	def init_app(self):
		from LevityDash.lib.utils.shared import preventAppNap
		preventAppNap()
		self.setQuitOnLastWindowClosed(True)
		# One theme per process, decided before the first dashboard decodes a `$token`: a workspace's `theme:`,
		# else the first window's dashboard theme, which every other window then follows.
		from . import workspace
		workspace.applyTheme()
		self.main_window = LevityMainWindow()
		iconPath = LevityDashboard.resources / 'ui-elements' / 'icon.icns'
		icon = QIcon(iconPath.as_posix())
		QApplication.setWindowIcon(icon)
		QApplication.setApplicationName('LevityDashboard')
		QApplication.setApplicationDisplayName('LevityDash')
		QApplication.setApplicationVersion(LevityDashboard.__version__)
		QApplication.setOrganizationName('LevityDash')
		QApplication.setOrganizationDomain('LevityDash.app')
		connectSignal(self.aboutToQuit, LevityDashboard.plugins.stop)
		connectSignal(self.aboutToQuit, self._finishWorkspace)
		# `close` over the control socket closes this window, deferred past the reply the client is owed.
		from PySide6.QtCore import QTimer
		from .control import setCloseWindow

		setCloseWindow(lambda: QTimer.singleShot(0, self.main_window.close))
		from LevityDash.lib.config import userConfig
		if userConfig.getOrSet('QtOptions', 'keepAwake', False, userConfig.getboolean):
			from LevityDash.lib.utils.keepawake import startKeepAwake, stopKeepAwake
			if startKeepAwake():
				connectSignal(self.aboutToQuit, stopKeepAwake)

	def start(self):
		self.init_app()
		QTimer.singleShot(10, LevityDashboard.load_dashboard)

		keyboardModifiers = self.queryKeyboardModifiers()
		from LevityDash.lib.plugins.dispatcher import backend_mode
		if backend_mode() == 'remote':
			# remote-is-attach-only: data comes from the standalone backend's
			# wire connection; local plugins stay loaded but never started
			qtLogger.info('mode=remote: local plugins are not started; data comes from the backend connection')
		elif LevityDashboard.plugin_config['Options'].getboolean('enabled'):
			if keyboardModifiers & Qt.AltModifier:
				print('Alt is pressed, plugin auto start disabled')
				return
			connectSignal(self.main_window.view.loadingFinished, self.start_plugins)

		self.main_window.show()
		self._startScreenshotServer()
		self._startControlServer()
		return self.exec_()

	def _finishWorkspace(self):
		"""On quit: write this window's geometry back, and, as the primary, ask the windows it started to close.

		The children are asked *first*: each writes its own entry on the way out, so the file's last write has
		every window in it. A window that will not close within 3 s is left running and named in the log.
		"""
		from . import control, workspace

		if control.socketId() is None:
			# Only the process that spawned the children closes them; a child has none.
			workspace.closeChildren()
		try:
			workspace.saveFromWindow(self.main_window)
		except Exception as e:  # noqa: BLE001 - a write-back that fails must never hold up quitting
			qtLogger.warning(f'workspace geometry not written back: {e}')

	def _startControlServer(self):
		"""Own the local socket that lets `levitydash --dashboard PATH` show a file in this window.

		Not owning it is not fatal: a socket left behind by a crashed instance is removed before listening,
		and a machine where `/tmp` is not writable simply has no handoff.
		"""
		from LevityDash.lib.utils.shared import connectSignal
		from .control import socketPath
		from .control_server import ControlServer
		self._controlServer = ControlServer(self)
		if not self._controlServer.listen():
			qtLogger.warning(f'dashboard handoff is off: could not listen on {socketPath()}')
			self._controlServer = None
			return
		connectSignal(self.aboutToQuit, self._controlServer.close)
		qtLogger.info(f'dashboard handoff listening on {socketPath()}')

	def _startScreenshotServer(self):
		from LevityDash.lib.config import userConfig
		try:
			port = int(userConfig.getOrSet('Debug', 'screenshot-port', 0, userConfig.getint))
			newInstance = isNewInstance()
			if port and newInstance:
				qtLogger.warning(f'screenshots: not started in a second instance - port {port} stays the first window\'s')
			port = screenshotPort(port, newInstance)
			if port:
				from .screenshot import start
				self._screenshotServer = start(self.main_window, port)
				qtLogger.warning(f'screenshots: http://127.0.0.1:{port}/screenshot')
		except Exception as e:  # noqa: BLE001 - a debug aid must never stop the display
			qtLogger.error(f'screenshot server not started: {e}')

	def start_plugins(self):
		self.main_window.view.loadingFinished.disconnect(self.start_plugins)
		QTimer.singleShot(10, LevityDashboard.plugins.start)
		# The backend does this for mode=remote; here the plugins run in this process
		from LevityDash.lib.config import userConfig
		from LevityDash.lib.plugins.patrol import Patrol, policyFromConfig
		self.patrol = Patrol(LevityDashboard.plugins, policyFromConfig(userConfig, qtLogger), qtLogger)


def _prepareRenderer():
	"""Canvas Painter draws through QRhi, which a widget only gets when QT_WIDGETS_RHI is set before the
	QApplication exists (on macOS the layer is otherwise blank white and logs `QRhiWidget: No QRhi`)."""
	import os
	name = os.environ.get('LEVITY_RENDERER')
	if name is None:
		try:
			from LevityDash.lib.config import userConfig
			name = userConfig.get('QtOptions', 'renderer', fallback='qpainter')
		except Exception:  # noqa: BLE001 - a config problem shows up later, where it is reported properly
			name = 'qpainter'
	if str(name).strip().lower() == 'canvas':
		os.environ.setdefault('QT_WIDGETS_RHI', '1')


_prepareRenderer()
LevityDashAppInstance = LevityDashApp()


from LevityDash import LevityDashboard
LevityDashboard.app = LevityDashAppInstance
LevityDashboard.main_thread = LevityDashAppInstance.thread()

from . import utils
from .app import *
from . import Modules

__all__ = ['Modules', 'LevityMainWindow']
