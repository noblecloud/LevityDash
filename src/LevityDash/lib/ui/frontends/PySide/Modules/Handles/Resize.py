from PySide2.QtCore import QObject, QPointF, QRectF, Signal, QTimer
from PySide2.QtWidgets import QGraphicsItem, QGraphicsSceneMouseEvent

from LevityDash.lib.stateful import StateProperty, Stateful

from LevityDash.lib.utils.shared import clamp, disconnectSignal
from LevityDash.lib.utils.geometry import Axis, DisplayPosition, LocationFlag
from LevityDash.lib.ui.frontends.PySide.Modules.Handles import Handle, HandleGroup

__all__ = ['ResizeHandle', 'ResizeHandles', 'Splitter']


class ResizeHandleSignals(QObject):
	action = Signal(QRectF, Axis)


class ResizeHandle(Handle):
	signals: ResizeHandleSignals
	_ratio = None
	parentWasMovable = True

	def __init__(self, *args, **kwargs):
		super(ResizeHandle, self).__init__(*args, **kwargs)
		self.setFlag(QGraphicsItem.ItemIgnoresTransformations)

	def mousePressEvent(self, event) -> None:
		self.parentItem().hideTimer.stop()
		if hasattr(self.surfaceProxy.parent, 'childIsMoving'):
			self.surfaceProxy.parent.childIsMoving = True
			self.parentWasMovable = self.surfaceProxy.parent.movable
			if self.parentWasMovable:
				self.surfaceProxy.parent.setMovable(False)
		event.accept()
		self.surfaceProxy.hold()
		self.surfaceProxy.setFocusProxy(self)
		self.setSelected(True)
		super(Handle, self).mousePressEvent(event)

	def mouseMoveEvent(self, event):
		event.accept()
		self.interactiveResize(event)
		self.parent.updatePosition(exclude=self)
		super(Handle, self).mouseMoveEvent(event)

	def mouseReleaseEvent(self, event):
		if hasattr(self.surfaceProxy.parent, 'childIsMoving'):
			self.surfaceProxy.parent.childIsMoving = False
			if self.parentWasMovable:
				self.surfaceProxy.parent.setMovable(True)
		self.setSelected(False)
		self.surfaceProxy.release()
		self.surfaceProxy.setFocusProxy(None)
		self.parentItem().hideTimer.start()
		super(Handle, self).mouseReleaseEvent(event)

	def interactiveResize(self, mouseEvent: QGraphicsSceneMouseEvent) -> tuple[QRectF, QPointF]:
		rect = self.surface.rect()
		original = self.surface.rect()
		# if self.parent.keepInFrame:
		# 	mousePos = self.mapToFromScene(mouseEvent.scenePos())
		# 	parentRect = self.parent.rect()
		# 	mousePos.setX(min(max(mousePos.x(), 0), parentRect.width()))
		# 	mousePos.setY(min(max(mousePos.y(), 0), parentRect.height()))
		# 	mouseEvent.setPos(self.mapFromParent(mousePos))

		loc = self.location
		mousePos = mouseEvent.scenePos()
		mousePos = self.surface.mapFromScene(mousePos)

		# if self.surface.parentGrid is not None:
		# 	colW = self.surface.parentGrid.columnWidth
		# 	rowH = self.surface.parentGrid.rowHeight
		# 	parentPosition = self.surface.mapToParent(mousePos)
		# 	x = parentPosition.x()
		# 	y = parentPosition.y()
		# 	v = round(x/colW)
		# 	V = round(v*colW)
		# 	if abs(V - x) < 10:
		# 		parentPosition.setX(round(v*colW, 4))
		# 	h = round(y/rowH)
		# 	H = round(h*rowH)
		# 	if abs(H - y) < 10:
		# 		parentPosition.setY(round(h*rowH, 4))
		# 	mousePos = self.surface.mapFromParent(parentPosition)

		# if abs((mousePos.x() % self.surface.parentGrid.columnWidth) - self.surface.parentGrid.columnWidth) < 20:
		# 	x = ((mousePos.x() // self.surface.parentGrid.columnWidth) + 1) * self.surface.parentGrid.columnWidth
		# 	mousePos.setX(x)
		# mousePos = self.mapToItem(self.surface, mouseEvent.pos())
		# mousePos = self.mapToParent(mousePos)
		if loc.isRight:
			rect.setRight(mousePos.x())
		elif loc.isLeft:
			rect.setLeft(mousePos.x())
		if loc.isBottom:
			rect.setBottom(mousePos.y())
		elif loc.isTop:
			rect.setTop(mousePos.y())

		rect = self.surface.mapRectToParent(rect)
		original = self.surface.mapRectToParent(original)
		# flatten array
		similarEdges = [item for sublist in [self.surface.similarEdges(n, rect=rect, singleEdge=loc) for n in self.surface.neighbors] for item in sublist]

		if similarEdges:
			s = similarEdges[0]
			snapValue = s.otherValue.pix
			if loc.isRight:
				rect.setRight(snapValue)
			elif loc.isLeft:
				rect.setLeft(snapValue)
			elif loc.isTop:
				rect.setTop(snapValue)
			elif loc.isBottom:
				rect.setBottom(snapValue)

		# snap handle to surface parent grid

		# rect = self.surface.mapRectFromParent(rect)

		# if any(rect.topLeft().toTuple()):
		# 	p = self.mapToParent(rect.topLeft())
		# 	rect.moveTo(QPointF(0, 0))
		# else:
		# 	p = self.pos()

		# rect = self.surface.mapRectToParent(rect)

		if rect.width() < 20:
			rect.setX(original.x())
			rect.setWidth(20)
		if rect.height() < 20:
			rect.setY(original.y())
			rect.setHeight(20)

		# if rect.width() == startWidth:
		# 	p.setX(pos.x())
		# if rect.height() == startHeight:
		# 	p.setY(pos.y())
		# self.setPos(self.position)
		# self.surface.setPos(QPointF(0, 0))
		# self.surface.setRect(rect)
		self.surface.geometry.setGeometry(rect)

		self.signals.action.emit(rect, self.location.asAxis)

	# self.mapValues(rect)

	def itemChange(self, change, value):
		if change == QGraphicsItem.ItemPositionChange:
			value = self.position
		elif value and change == QGraphicsItem.ItemVisibleHasChanged and self.surface and self.surface.geometry:
			self.updatePosition(self.surface.geometry.absoluteRect())
		return super(ResizeHandle, self).itemChange(change, value)


class ResizeHandles(HandleGroup):
	handleClass = ResizeHandle
	signals: ResizeHandleSignals

	def __init__(self, *args, **kwargs):
		super(ResizeHandles, self).__init__(*args, **kwargs)
		self.hideTimer = QTimer(interval=5000, timeout=self.hide)
		self.hideTimer.setSingleShot(True)
		scene = self.scene()

	def setEnabled(self, enabled):
		super(ResizeHandles, self).setEnabled(enabled)

	def disable(self):
		self.setEnabled(False)


class Splitter(Handle):
	_ratio: float = None

	def __init__(self, surface, ratio=0.5, splitType: LocationFlag = LocationFlag.Horizontal, *args, **kwargs):

		if isinstance(splitType, str):
			splitType = LocationFlag[splitType.title()]

		self.width = 2.5
		self.length = 10
		self.location = splitType

		primary = kwargs.pop('primary', None)
		if primary is not None and primary.parent is not surface:
			primary.setParentItem(surface)
		secondary = kwargs.pop('secondary', None)
		if secondary is not None and secondary.parent is not surface:
			secondary.setParentItem(surface)

		super(Splitter, self).__init__(surface, location=splitType, *args, **kwargs)

		self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)

		if primary is None or secondary is None:
			surfaceChildren = [child for child in self.surface.childPanels if child is not primary or child is not secondary]
			if len(surfaceChildren) > 2:
				raise Exception("Splitter can only be used with 2 child panels")
			elif len(surfaceChildren) == 2:
				self.primary = surfaceChildren[0]
				self.secondary = surfaceChildren[1]
			elif len(surfaceChildren) == 1:
				self.primary = surfaceChildren[0]
				self.secondary = None
		else:
			self.primary = primary
			self.secondary = secondary

		self.ratio = ratio
		self.setPos(self.position)

	@property
	def primary(self):
		return self.__primary

	@primary.setter
	def primary(self, value):
		self.__primary = value

	@property
	def secondary(self):
		return self.__secondary

	@secondary.setter
	def secondary(self, value):
		self.__secondary = value

	@property
	def position(self) -> QPointF:
		center = self.surface.rect().center()
		if self.location.isVertical:
			center.setX(self.ratio*float(self.surface.geometry.absoluteWidth))
		else:
			center.setY(self.ratio*float(self.surface.geometry.absoluteHeight))
		return center

	def mousePressEvent(self, event) -> None:
		event.accept()
		self.setSelected(True)
		super(Handle, self).mousePressEvent(event)

	def mouseMoveEvent(self, event):
		event.accept()
		self.interactiveResize(event)

	def mouseDoubleClickEvent(self, event):
		event.accept()
		self.swapSurfaces()

	def mouseReleaseEvent(self, event) -> None:
		self.update()
		super(Handle, self).mouseReleaseEvent(event)

	def interactiveResize(self, mouseEvent):
		eventPosition = self.parent.mapFromScene(mouseEvent.scenePos())
		value = eventPosition.x() if self.location.isVertical else eventPosition.y()
		surfaceSize = float(self.surface.geometry.absoluteWidth if self.location.isVertical else self.surface.geometry.absoluteHeight)
		value /= surfaceSize
		# Snap value to 0.1 increments if within 0.03
		valueRounded = round(value, 1)
		if abs(valueRounded - value) < surfaceSize*0.0003:
			value = valueRounded
		self.ratio = value

	def swapSurfaces(self):
		self.primary, self.secondary = self.secondary, self.primary
		if hasattr(self.surface, 'primary'):
			self.surface.primary, self.surface.secondary = self.surface.secondary, self.surface.primary
		self.setGeometries()

	def updatePosition(self, rect: QRectF):
		center = rect.center()
		if self.location.isVertical:
			center.setX(self.ratio*float(self.surface.geometry.absoluteWidth))
		else:
			center.setY(self.ratio*float(self.surface.geometry.absoluteHeight))
		self.setPos(center)

	def itemChange(self, change, value):
		if change == QGraphicsItem.ItemPositionChange:
			value = self.position
			if self.location.isVertical:
				value.setY(self.position.y())
			else:
				value.setX(self.position.x())
		elif change == QGraphicsItem.ItemVisibleChange:
			if value and not self._resizeSignalConnected:
				self.surface.signals.resized.connect(self.updatePosition)
				self._resizeSignalConnected = True
			elif not value and self._resizeSignalConnected:
				disconnectSignal(self.surface.signals.resized, self.updatePosition)
				self._resizeSignalConnected = False
		return super(Handle, self).itemChange(change, value)

	@property
	def ratio(self) -> float:
		# if self.primary is not None and self.secondary is not None and self.primary.isVisible() != self.secondary.isVisible():
		# 	self._ratio = 0
		if self._ratio is None:
			if self.location.isVertical:
				self._ratio = self.pos().x()/float(self.surface.rect().width())
			else:
				self._ratio = self.pos().y()/float(self.surface.rect().height())
		return self._ratio

	@ratio.setter
	def ratio(self, value):
		if self._ratio != value:
			self._ratio = value
			self.updatePosition(self.surface.rect())
			self.setGeometries()

	def setGeometries(self):
		value = clamp(self._ratio, 0, 1)

		if value == 0:
			selected = self.primary if self.primary.isVisible() else self.secondary
			selected.geometry.setRelativeGeometry(QRectF(0, 0, 1, 1))
			selected.updateFromGeometry()
			# self.surface.update()
			return

		primary, secondary = self.primary, self.secondary

		if self.location.isVertical:
			if primary is not None:
				primary.geometry.relativeWidth = value
				primary.geometry.relativeHeight = 1
				primary.geometry.relativeX = 0
				primary.geometry.relativeY = 0
			if secondary is not None:
				secondary.geometry.relativeWidth = 1 - value
				secondary.geometry.relativeHeight = 1
				secondary.geometry.relativeX = value
				secondary.geometry.relativeY = 0
		else:
			if primary is not None:
				primary.geometry.relativeWidth = 1
				primary.geometry.relativeHeight = value
				primary.geometry.relativeY = 0
				primary.geometry.relativeX = 0
			if secondary is not None:
				secondary.geometry.relativeWidth = 1
				secondary.geometry.relativeHeight = 1 - value
				secondary.geometry.relativeY = value
				secondary.geometry.relativeX = 0
		for child in [primary, secondary]:
			if child is not None:
				child.updateFromGeometry()
	# self.surface.update()


class TitleValueSplitter(Splitter, Stateful):
	def __init__(self, surface, title, value, position=DisplayPosition.Top, **kwargs):
		kwargs = self.prep_init(kwargs)
		self.__manualText = None
		self.location = LocationFlag.Horizontal
		self.title = title
		self.value = value
		ratio = kwargs.pop('ratio', 0.2)
		self.titlePosition = position
		self.manualText = kwargs.pop('text', None)
		super(TitleValueSplitter, self).__init__(surface, primary=title, secondary=value, ratio=ratio)
		self.setVisibility(kwargs.get('visible', True))

	def _afterSetState(self):
		self.setGeometries()

	@StateProperty(key='text', default=None, singleVal=True, sortOrder=0)
	def manualText(self) -> str:
		return self.__manualText

	@manualText.setter
	def manualText(self, value: str):
		if value is None:
			return
		self.__manualText = str(value)
		self.title.setManualValue(self.__manualText)

	@manualText.condition
	def manualText(self) -> bool:
		return self.title.isVisible()

	def mouseDoubleClickEvent(self, event):
		ratio = abs(1 - self.ratio)
		self.swapSurfaces()
		self.ratio = ratio

	def swapSurfaces(self):
		if self.titlePosition == DisplayPosition.Top:
			self.titlePosition = DisplayPosition.Bottom
		elif self.titlePosition == DisplayPosition.Bottom:
			self.titlePosition = DisplayPosition.Top
		else:
			return
		self.setGeometries()

	@StateProperty(default=0.2, singleVal=True, sortOrder=1, dependencies={'geometry', 'position', 'visible'})
	def ratio(self) -> float:
		pass

	@ratio.encode
	def ratio(value: float) -> float:
		return round(value, 2)

	@ratio.condition
	def ratio(self) -> bool:
		return self.title.isVisible()

	@StateProperty(default=DisplayPosition.Top, key='position', allowNone=False)
	def titlePosition(self) -> DisplayPosition:
		return self._titlePosition

	@titlePosition.setter
	def titlePosition(self, value):
		if isinstance(value, str):
			value = DisplayPosition[value]
		if not isinstance(value, DisplayPosition):
			raise TypeError('titlePosition must be a DisplayPosition')
		self._titlePosition = value
		if self._ratio:
			self.setGeometries()

	@titlePosition.condition
	def titlePosition(self):
		return self.title.isVisible()

	@Splitter.primary.getter
	def primary(self):
		return self.title if self.titlePosition == DisplayPosition.Top else self.value

	@Splitter.secondary.getter
	def secondary(self):
		return self.title if self.titlePosition == DisplayPosition.Bottom else self.value

	def hideTitle(self):
		self.title.hide()
		self.setVisible(False)
		self.setEnabled(False)
		self.value.geometry.setRelativeGeometry(QRectF(0, 0, 1, 1))

	def showTitle(self):
		self.title.show()
		self.setVisible(True)
		self.setEnabled(True)
		self.setGeometries()

	def toggleTitle(self):
		if self.title.isVisible():
			self.hideTitle()
		else:
			self.showTitle()

	def setVisibility(self, visible):
		if visible:
			self.showTitle()
		else:
			self.hideTitle()

	@StateProperty(default=True, singleVal=True, singleForceCondition=lambda v: not v)
	def visible(self) -> bool:
		return self.title.isVisible()

	@visible.setter
	def visible(self, value):
		self.setVisibility(value)

	@visible.condition
	def visible(value: bool) -> bool:
		return not value

	@property
	def enabled(self):
		return self.title.isVisible()


class MeasurementUnitSplitter(Splitter, Stateful):

	def __init__(self, value, unit, *args, **kwargs):
		self.value = value
		self.unit = unit
		properties: 'MeasurementDisplayProperties' = kwargs['surface'].displayProperties
		kwargs = self.prep_init(kwargs)
		kwargs['splitType'] = properties.splitDirection or LocationFlag.Horizontal
		kwargs['ratio'] = properties.valueUnitRatio
		super(MeasurementUnitSplitter, self).__init__(*args, **kwargs, primary=value, secondary=unit)

		self.value.textBox.signals.changed.connect(self.updateUnitDisplay)
		self.unit.signals.resized.connect(self.updateUnitDisplay)
		self.hide()

	def updateUnitDisplay(self):
		if self.displayProperties.unitPosition == 'auto':
			self.__decideAuto()
		elif self.displayProperties.unitPosition in ['hidden', 'inline']:
			self.unit.hide()
			self.value.geometry.setRelativeGeometry(QRectF(0, 0, 1, 1))
			self.hide()
			self.setEnabled(False)
			return
		elif self.displayProperties.unitPosition == 'floating':
			self.unit.show()
			self.unit.unlock()
			self.value.geometry.setRelativeGeometry(QRectF(0, 0, 1, 1))
			self.hide()
			self.setEnabled(False)
			return
		self.unit.show()
		self.setEnabled(True)
		self.updatePosition(self.surface.rect())
		self.setGeometries()

	@property
	def _ratio(self):
		if self.displayProperties.unitPosition in ['hidden', 'inline', 'floating']:
			return 1
		elif self.primary is self.unit:
			return self.displayProperties.valueUnitRatio
		else:
			return 1 - self.displayProperties.valueUnitRatio

	@_ratio.setter
	def _ratio(self, value):
		self.displayProperties.valueUnitRatio = value

	@StateProperty(key='valueUnitRatio')
	def ratio(self):
		pass

	@property
	def displayProperties(self) -> 'MeasurementDisplayProperties':
		return self.surface.displayProperties

	def swapSurfaces(self):
		if self.displayProperties.unitPosition == 'above':
			self.displayProperties.unitPosition = DisplayPosition.Below
		elif self.displayProperties.unitPosition == 'below':
			self.displayProperties.unitPosition = DisplayPosition.Above
		else:
			return
		self.updateUnitDisplay()
		self.setGeometries()

	@Splitter.primary.getter
	def primary(self):
		return self.value if self.displayProperties.unitPosition in ['below', 'auto', 'hidden', 'inline'] else self.unit

	@Splitter.secondary.getter
	def secondary(self):
		return self.unit if self.displayProperties.unitPosition in ['below', 'auto', 'hidden', 'inline'] else self.value

	def __decideAuto(self):
		surfaceRect = self.surface.rect()
		if surfaceRect.width() > surfaceRect.height():
			value = 0.75
		else:
			value = 0.90
		self.ratio = self.displayProperties.valueUnitRatio or value
