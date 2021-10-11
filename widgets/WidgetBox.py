from datetime import datetime
from time import strftime

from typing import TYPE_CHECKING

from PySide2.QtCore import Qt, QTimer
from PySide2.QtGui import QMouseEvent, QTransform
from PySide2.QtWidgets import QApplication, QScrollArea, QTabWidget

from src.api import API
from src.observations import ObservationRealtime
from src.utils import Margins
from widgets.Complication import Complication, LocalComplication
from widgets.ComplicationArray import ToolBox, WidgetBox
from widgets.ComplicationCluster import ComplicationCluster
from widgets.Graph import Figure, Graph, GraphScene
from widgets.moon import MoonComplication
from widgets.Wind import WindComplication


class GraphComplication(LocalComplication):
	_pointerPosition: object

	def __init__(self, apis: dict = None, *args, **kwargs):
		super(GraphComplication, self).__init__(*args, **kwargs)
		if apis is None:
			self.APIs = [x for x in QApplication.topLevelWidgets() if 'MainWindow' in x.__class__.__name__][0].APIs
		else:
			self.APIs = apis
		self.layout.removeWidget(self.titleLabel)
		self.titleLabel.hide()
		self.titleLabel.deleteLater()
		self.setWidget(Graph(self))
		self.setAcceptDrops(True)
		self.setMouseTracking(True)

	def mousePressEvent(self, event: QMouseEvent):
		a: GraphScene = self.valueWidget.scene()
		self._pointerPosition = event.pos()
		self.clickStart = event.pos()
		sel = [i for i in a.items() if i.contains(event.pos())]
		if sel:
			print(sel)
			event.ignore()
		else:
			event.accept()
			super(GraphComplication, self).mousePressEvent(event)

	#
	# # def mouseMoveEvent(self, event: QMouseEvent) -> None:
	# # 	if event.buttons() == Qt.LeftButton and self.clickStart:
	# # 		travelFromPress = (event.pos() - self.clickStart).manhattanLength()
	# # 		if travelFromPress > 20:
	# # 			self.mouseHoldTimer.stop()
	# # 	travelFromPress = (event.pos() - self.clickStart).manhattanLength()
	# # 	if travelFromPress > 20:
	# # 		self.mouseHoldTimer.stop()
	# # 	self.mouseHoldTimer.stop()
	#
	# def mouseReleaseEvent(self, event):
	# 	self.clickStart = None
	# 	self.mouseHoldTimer.stop()
	# 	super(GraphComplication, self).mouseReleaseEvent(event)

	def mouseMoveEvent(self, event: QMouseEvent):
		print(event.pos())
		super(GraphComplication, self).mouseMoveEvent(event)
		if event.buttons() == Qt.LeftButton:
			self.valueWidget.scroll(event.pos().x() - self._pointerPosition.x(), 0)
			self._pointerPosition = event.pos()
		super(GraphComplication, self).mouseMoveEvent(event)

	@property
	def state(self):
		print('a')
		return {
				'type':   'LocalComplication',
				'data':   self.valueWidget.state,
				'source': 'local',
				'cell':   {k.strip('_'): v for k, v in vars(self.cell).items() if k != 'item'},
				'class':  self.__class__.__name__
		}

	@state.setter
	def state(self, value: dict):
		graphScene = self.valueWidget.scene()
		figures = value['data']['figures']
		for name, figure in figures.items():

			fig = graphScene.figures.get(name, Figure(graphScene, Margins(**figure['margins'])))
			graphScene.figures[name] = fig
			for datum in figure['data'].values():
				datum['api'] = self.APIs[datum['api']]
				graphScene.addMeasurement(**datum, figure=fig)


class Clock(LocalComplication):

	def __init__(self, *args, **kwargs):
		super(Clock, self).__init__(*args, **kwargs)
		self._subscriptionKey = 'clock'
		self.updateTimer = QTimer(self)
		self.refresh()
		time = datetime.now().time()
		t = 60000 - (time.second * 1000) + int(time.microsecond / 1000)
		self.updateTimer.singleShot(t, self.primeClock)

		self.layout.removeWidget(self.titleLabel)
		self.titleLabel.hide()
		self.titleLabel.deleteLater()

	def refresh(self):
		s = strftime('%-I:%M')
		# self.valueLabel.setText(s)
		self.value = s

	def primeClock(self):
		self.refresh()
		self.updateTimer.setInterval(1000 * 60)
		self.updateTimer.start()
		self.updateTimer.timeout.connect(self.refresh)

	def mouseMoveEvent(self, event):
		event.ignore()


class Tabs(QTabWidget):
	toolboxes = {}
	localComplications = {'WindComplication':    WindComplication,
	                      'MoonComplication':    MoonComplication,
	                      'Clock':               Clock,
	                      'ComplicationCluster': ComplicationCluster,
	                      'GraphComplication':   GraphComplication}

	def __init__(self, *args, **kwargs):
		super(Tabs, self).__init__(*args, **kwargs)
		self.addPrebuilt()
		self.setCurrentIndex(0)

	def addAPI(self, api: 'API'):
		scroll = ScrollingWidgetBox(self, api=api)
		scroll.widget.name = api.name
		self.toolboxes.update({api.name: scroll.widget})
		self.insertTab(0, scroll, api.name)

	def addPrebuilt(self) -> None:
		from widgets.moon import Moon
		scroll = ScrollingWidgetBox(self)
		w = scroll.widget
		for widget in self.localComplications.values():
			w.insert(widget(self))

		w.name = 'local'
		self.toolboxes.update({scroll.widget.name: scroll.widget})
		self.insertTab(0, scroll, w.name.capitalize())


class ScrollingWidgetBox(QScrollArea):
	widget: ToolBox
	last = 0

	def __init__(self, parent, api: API = None):
		super(ScrollingWidgetBox, self).__init__(parent)
		self.setWidgetResizable(True)
		self.widget = ToolBox(self, api)
		self.setWidget(self.widget)

	def resizeEvent(self, event):
		if self.last != self.widget.columns:
			self.last = self.widget.columns
			self.widget.buildGrid()
