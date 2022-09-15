from PySide2.QtCore import QPointF, QRectF, Qt
from PySide2.QtWidgets import QGraphicsItem, QApplication

from LevityDash.lib.stateful import Stateful, StateProperty
from LevityDash.lib.utils import clamp, clearCacheAttr, ScaleFloat
from LevityDash.lib.ui.Geometry import Size, parseSize, LocationFlag, DisplayPosition, RelativeFloat
from LevityDash.lib.ui.frontends.PySide.Modules.Handles import Handle
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Label import TitleLabel
from WeatherUnits import Length


class Splitter(Handle):
	_ratio: float = None
	_inverted: bool = False

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

		self.surface.signals.resized.connect(self.updatePosition)

		self.setFlag(QGraphicsItem.ItemSendsGeometryChanges)

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

		if (primary := self.primary) is not None:
			primary.locked = True
		if (secondary := self.secondary) is not None:
			secondary.locked = True

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
		if (timer := getattr(self.parentItem(), 'hideTimer', None)) is not None:
			timer.stop()
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
		if (timer := getattr(self.parentItem(), 'hideTimer', None)) is not None:
			timer.start()
		self.update()
		super(Handle, self).mouseReleaseEvent(event)

	def interactiveResize(self, mouseEvent):
		eventPosition = self.parent.mapFromScene(mouseEvent.scenePos())
		if self._inverted:
			eventPosition.setY(self.parent.geometry.absoluteHeight - eventPosition.y())
		value = eventPosition.x() if self.location.isVertical else eventPosition.y()
		surfaceSize = float(self.surface.geometry.absoluteWidth if self.location.isVertical else self.surface.geometry.absoluteHeight)
		value /= surfaceSize

		# Snap value to 0.1 increments if within 0.03
		if QApplication.queryKeyboardModifiers() & Qt.ShiftModifier:
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
		return super(Handle, self).itemChange(change, value)

	@property
	def ratio(self) -> ScaleFloat:
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
		value = clamp(self.ratio, 0, 1)
		primary, secondary = self.primary, self.secondary
		primary.setVisible(value != 0)
		secondary.setVisible(value != 1)
		if value in {0, 1}:
			selected = primary if value else secondary
			selected.geometry.setRelativeGeometry(QRectF(0, 0, 1, 1))
			selected.updateFromGeometry()
			return

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


class TitleValueSplitter(Splitter, Stateful):
	def __init__(self, surface, title, value, position=DisplayPosition.Top, **kwargs):
		kwargs = self.prep_init(kwargs)
		self.__manualText = None
		self.location = LocationFlag.Horizontal
		self.__title = title
		self.value = value
		ratio = kwargs.pop('ratio', 0.2)
		super(TitleValueSplitter, self).__init__(surface, primary=title, secondary=value, ratio=ratio)
		self.titlePosition = position
		self.setVisibility(kwargs.pop('visible', True))
		if kwargs:
			self.state = kwargs

	def _afterSetState(self):
		self.setGeometries()

	@property
	def state(self):
		return Stateful.state.fget(self)

	@state.setter
	def state(self, value):
		titleKeys = TitleLabel.statefulKeys - {'visible'}

		titleState = {key: value[key] for key in titleKeys if key in value}
		ownState = {key: value[key] for key in value if key not in titleKeys}

		if ownState:
			Stateful.state.fset(self, ownState)
		if titleState:
			self.title.state = titleState
		if ownState or titleState:
			self.setGeometries()

	@StateProperty(unwrap=True, default=Stateful)
	def title(self) -> TitleLabel:
		return self.__title

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

	@StateProperty(key='rotate', default=False, sortOrder=2)
	def rotation(self) -> bool:
		return getattr(self, '_rotation', False)

	@rotation.setter
	def rotation(self, value: bool):
		self._rotation = value
		self.setGeometries()

	@StateProperty(key='size', default=0.2, singleVal=True, sortOrder=1, dependencies={'geometry', 'position', 'visible'})
	def ratio(self) -> ScaleFloat | float | None:
		if self.height is not None:
			if self.location.isVertical:
				r = sorted((0, float(self.height_px)/float(self.surface.geometry.absoluteWidth), 1))[1]
			else:
				r = sorted((0, float(self.height_px)/float(self.surface.geometry.absoluteHeight), 1))[1]
			return r if self.primary is self.title else 1 - r
		return Splitter.ratio.fget(self)

	@ratio.encode
	def ratio(value: float) -> float:
		return round(value, 2)

	@ratio.condition
	def ratio(self) -> bool:
		return self.title.isVisible() and self.height is None

	@StateProperty(default=None, singleVal=True, sortOrder=1, dependencies={'geometry', 'position', 'visible'})
	def height(self) -> Size.Height | Length | None:
		return getattr(self, '_height', None)

	@height.setter
	def height(self, value: Size.Height | Length | None):
		self._height = value
		self.setGeometries()

	@height.decode
	def height(self, value: str | int | float) -> Size.Height | Length:
		return parseSize(value, type(self).height.default(self))

	@height.encode
	def height(self, value: Size.Height | Length) -> str | None:
		return str(value) if value is not None else None

	@property
	def height_px(self) -> float:
		height: Size.Height = self._height
		match height:
			case Size.Height(absolute=True):
				return height.value
			case Size.Height(relative=True):
				if (self._relativeTo or self.value.localGroup) is None:
					raise ValueError('RelativeTo is not set')
				return height.toAbsolute(self._relativeTo.absoluteHeight)
			case Length(), _:
				dpi = self.surface.scene().view.screen().physicalDotsPerInchY()
				return float(height.inch)*dpi
			case _:
				return None

	def parseLength(self, value: str | int | float) -> Size.Height | Length:
		if isinstance(value, str):
			return Length(value)
		else:
			return Size.Height(value)

	@StateProperty(default=DisplayPosition.Top, key='position', allowNone=False)
	def titlePosition(self) -> DisplayPosition:
		return getattr(self, '_titlePosition', DisplayPosition.Top)

	@titlePosition.setter
	def titlePosition(self, value):
		if isinstance(value, str):
			value = DisplayPosition[value]
		if not isinstance(value, DisplayPosition):
			raise TypeError('titlePosition must be a DisplayPosition')
		flipped = value is self.titlePosition.getOpposite()
		self._titlePosition = value

		if self._titlePosition is DisplayPosition.Hidden:
			self.hideTitle()
		elif not self.title.isVisible():
			self.showTitle()

		if self._titlePosition.value.casefold() in {'left', 'right'}:
			self.location = LocationFlag.Vertical
			clearCacheAttr(self, 'cursor')
			self.resetPath()
		if flipped:
			self.ratio = abs(1 - self.ratio)
		else:
			self.setGeometries()

	@titlePosition.condition
	def titlePosition(self):
		return self.title.isVisible()

	def setTitlePosition(self, position: DisplayPosition):
		self.titlePosition = position

	@Splitter.primary.getter
	def primary(self):
		if self.location.isHorizontal:
			return self.title if self.titlePosition == DisplayPosition.Top else self.value
		else:
			return self.title if self.titlePosition == DisplayPosition.Left else self.value

	@Splitter.secondary.getter
	def secondary(self):
		if self.location.isHorizontal:
			return self.value if self.titlePosition == DisplayPosition.Top else self.title
		else:
			return self.value if self.titlePosition == DisplayPosition.Left else self.title

	def hideTitle(self):
		self._previousHeight = self.ratio
		self.ratio = 1 if self.title is self.secondary else 0
		self.setVisible(False)
		self.setEnabled(False)

	def showTitle(self):
		if (previousRatio := getattr(self, '_previousHeight', None)) is not None:
			self.ratio = previousRatio
		self.setVisible(True)
		self.setEnabled(True)

	# self.setGeometries()

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

	@visible.condition(method='get')
	def visible(value: bool) -> bool:
		return not value

	@property
	def enabled(self):
		return self.title.isVisible()

	def setGeometries(self):
		title = self.title
		title.setTransformOriginPoint(title.rect().center())
		title.setRotation(0)
		super().setGeometries()
		if self.location.isVertical and self.title.isVisible():
			if self.rotation and title.rect().width() < title.rect().height():
				ratio = (1 - (title.rect().width()/title.rect().height()))*2
				title.setTransformOriginPoint(title.rect().center())
				angle = sorted((0, (90*ratio), 90))[1]
				if angle > 70:
					angle = 90
				title.setRotation(angle + 0.01)
				super().setGeometries()


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
		elif self.displayProperties.unitPosition in {'floating', 'float-under'}:
			self.unit.show()
			self.unit.unlock()
			self.value.geometry.setRelativeGeometry(QRectF(0, 0, 1, 1))
			self.hide()
			self.setEnabled(False)
			if self.displayProperties.unitPosition == 'float-under':
				self.fitUnitUnder()
			return
		self.unit.show()
		self.setEnabled(True)
		self.updatePosition(self.surface.rect())
		self.setGeometries()

	def fitUnitUnder(self):
		self.unit.unlock()
		self.value.geometry.setRelativeGeometry(QRectF(0, 0, 1, 1))
		self.unit.geometry.setRelativeGeometry(QRectF(0, 0, 1, 1))
		space = self.value.unitSpace
		unitSize = self.displayProperties.valueUnitRatio
		if isinstance(unitSize, RelativeFloat):
			unitSize = float(unitSize*self.surface.rect().height())
		if space.height() > unitSize:
			space.setHeight(unitSize)
		# pos = space.topLeft()
		# self.unit.geometry.setAbsoluteRect(space)
		# self.unit.setRect(space.normalized())
		self.unit.contentsRect = space
		# self.unit.setPos(pos)
		self.unit.textBox.refresh()

		totalRect = self.unit.textBox.sceneBoundingRect() | self.value.textBox.sceneBoundingRect()
		offset = self.surface.sceneBoundingRect().center() - totalRect.center()
		self.unit.moveBy(*offset.toTuple())
		self.value.moveBy(*offset.toTuple())

	@property
	def _ratio(self):
		if self.displayProperties.unitPosition in {'hidden', 'inline', 'floating' 'fit'}:
			return 1
		if self.unit is self.secondary:
			return 1 - self.displayProperties.valueUnitRatio
		return self.displayProperties.valueUnitRatio

	# else:
	# 	return 1 - self.displayProperties.valueUnitRatio

	def interactiveResize(self, mouseEvent):
		if self.displayProperties.unitPosition in ['hidden', 'inline', 'floating']:
			return
		if self.primary is self.value:
			self.ratio = 1 - mouseEvent.pos().x()/self.surface.rect().width()
		super().interactiveResize(mouseEvent)
		self.updatePosition(self.surface.rect())
		self.setGeometries()

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
		return self.value if self.displayProperties.unitPosition in DisplayPosition.secondaryPositions else self.unit

	@Splitter.secondary.getter
	def secondary(self):
		return self.unit if self.displayProperties.unitPosition in DisplayPosition.secondaryPositions else self.value

	def __decideAuto(self):
		surfaceRect = self.surface.rect()
		if self.displayProperties.splitDirection == LocationFlag.Horizontal:
			if surfaceRect.width() > surfaceRect.height():
				value = 0.75
			else:
				value = 0.90
			self.ratio = self.displayProperties.valueUnitRatio or value
