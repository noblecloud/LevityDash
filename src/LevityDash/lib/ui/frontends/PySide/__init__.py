from PySide2.QtWidgets import QApplication

from ... import UILogger

qtLogger = UILogger.getChild('Qt')


class LevityDashApp(QApplication):

	main_window: 'LevityMainWindow'

	def init_app(self):
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

	def start(self):
		self.init_app()
		QTimer.singleShot(10, LevityDashboard.load_dashboard)

		keyboardModifiers = self.queryKeyboardModifiers()
		if LevityDashboard.plugin_config['Options'].getboolean('enabled'):
			if keyboardModifiers & Qt.AltModifier:
				print('Alt is pressed, plugin auto start disabled')
				return
			connectSignal(self.main_window.centralWidget().loadingFinished, self.start_plugins)

		self.main_window.show()
		return self.exec_()

	def start_plugins(self):
		self.main_window.centralWidget().loadingFinished.disconnect(self.start_plugins)
		QTimer.singleShot(10, LevityDashboard.lib.plugins.start)


LevityDashAppInstance = LevityDashApp()


from LevityDash import LevityDashboard
LevityDashboard.app = LevityDashAppInstance
LevityDashboard.main_thread = LevityDashAppInstance.thread()

from . import utils
from .app import *
from . import Modules

__all__ = ['Modules', 'LevityMainWindow']
