from PySide2.QtCore import QPointF, QRectF
from PySide2.QtWidgets import QGraphicsItem

from LevityDash.lib.stateful import Stateful, StateProperty
from LevityDash.lib.ui.frontends.PySide.Modules.Handles import Handle
from LevityDash.lib.utils import LocationFlag, disconnectSignal, clamp, DisplayPosition


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
