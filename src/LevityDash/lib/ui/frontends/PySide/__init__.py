from PySide6.QtWidgets import QApplication

from ... import UILogger

qtLogger = UILogger.getChild('Qt')


class LevityDashApp(QApplication):

	main_window: 'LevityMainWindow'

	def init_app(self):
		from LevityDash.lib.utils.shared import preventAppNap
		preventAppNap()
		self.setQuitOnLastWindowClosed(True)
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
		return self.exec_()

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
