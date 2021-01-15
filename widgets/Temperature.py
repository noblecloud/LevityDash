from PySide2 import QtGui

from widgets.Status import StatusObject
from widgets.loudWidget import LoudWidget
from ui.Temperature_UI import Ui_Form

# current_dir = os.path.dirname(os.path.abspath(__file__))
# Form, Base = QUiLoader.loadUiType(os.path.join(current_dir, "widgets/indoorOutdoor.ui"))


class LargeBox(LoudWidget, Ui_Form, StatusObject):
	# layout: QtWidgets.QVBoxLayout
	# title: QtWidgets.QLabel
	# value: DynamicLabel
	# subs: QtWidgets.QHBoxLayout
	#
	# valueFont = QtGui.QFont()
	# valueFont.setPointSize(80)
	#
	# titleFont = QtGui.QFont()
	# titleFont.setPointSize(40)
	#
	# subFont = QtGui.QFont()
	# subFont.setPointSize(20)

	def __init__(self, parent=None):
		super(self.__class__, self).__init__(parent)
		self.setupUi(self)
		# self.SubBValue.setFontSize(self.SubAValue.fontS)
	# def __init__(self, subs, *args, **kwargs):
	# 	super().__init__(*args, **kwargs)
		# loader = QUiLoader()
		# file = QFile("widgets/Temperature.ui")
		# file.open(QFile.ReadOnly)
		# self.ui = loader.load(file, self)

	def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
		print(self)

	# TODO: implement adding list of sub widgets
	# if isinstance(subs, list):
	# 	self.nSubs = len(subs)
	# 	self.subs = subs
	# elif isinstance(subs, int):
	# 	self.

	# def sizeHint(self):
	# 	return QtCore.QSize(200, 120)
