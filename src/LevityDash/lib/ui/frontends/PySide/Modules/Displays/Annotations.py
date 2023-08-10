import re
from PySide6.QtCore import QRectF, QPointF, QPoint
from PySide6.QtGui import QBrush
from abc import abstractmethod
from datetime import datetime
from numbers import Number
from typing import Any, TypeVar, ClassVar, Type, Callable, Dict

from LevityDash.lib.stateful import Stateful, StateProperty, DefaultGroup
from LevityDash.lib.stateful_mixins import ColorGradientMixin
from LevityDash.lib.ui import UILogger, Color
from LevityDash.lib.ui.Geometry import Size, DisplayPosition, Alignment, AlignmentFlag, Dimension, getDPI, LineWeight
from LevityDash.lib.ui.frontends.PySide.Modules.Displays import Text, Surface
from LevityDash.lib.ui.frontends.PySide.utils import SoftShadow
from LevityDash.lib.utils import numberRegex, Unset, Axis
from LevityDash.lib.utils.protocols import GraphItem, HasWeight
from WeatherUnits import Length, Percentage, Measurement
from WeatherUnits.length import Centimeter, Millimeter, Inch

log = UILogger.getChild('Annotations')


class AnnotationText(Text):
	textSize: Length | Size.Height
	shadow = SoftShadow
	labelGroup: 'AnnotationLabels'
	value: Any
	timestamp: datetime
	scaleToFit: bool = True

	# Section Annotation Text
	def __init__(self, labelGroup: 'AnnotationLabels' = None, **kwargs):
		if labelGroup is None:
			raise TypeError('labelGroup must be passed as a keyword argument')
		self.labelGroup = labelGroup
		if (scaleToFit := kwargs.pop('scaleToFit', None)) is not None:
			self.scaleToFit = scaleToFit
		try:
			super(AnnotationText, self).__init__(parent=labelGroup.surface, **kwargs)
		except TypeError as e:
			raise AttributeError(f'Error initializing {self.__class__.__name__}: {e}')

	# self.setCacheMode(QGraphicsItem.ItemCoordinateCache)

	def setZValue(self, z: float) -> None:
		z = max(i.graphic.zValue() for i in self.figure.plots) + 10
		super(Text, self).setZValue(z)

	@property
	def value(self):
		return self._value

	@value.setter
	def value(self, value):
		self._value = value
		self.refresh()

	@property
	def surface(self):
		return self.labelGroup.surface

	@property
	def allowedWidth(self):
		return 400

	def getTextPosition(self, limitRect: QRectF = None) -> QPointF:
		return QPoint(0, 0)

	def scaleSelection(self, x, y):
		if self.scaleToFit:
			if y * self._sizeHintRect.width() > self.allowedWidth and y > x:
				return x
		return y

	@property
	def limitRect(self) -> QRectF:
		viewScale = self.scene().viewScale
		rect = QRectF(0, 0, self.allowedWidth / viewScale.x, self.labelGroup.textSize_px / viewScale.y)
		rect.moveCenter(QPointF(0, 0))
		return rect

	@property
	def displayPosition(self) -> DisplayPosition:
		return self.labelGroup.position

	def containingRect(self) -> QRectF:
		return self.surface.rect()

	@property
	def offset(self) -> float:
		return self.labelGroup.offset_px

	@property
	def x(self) -> float:
		return self.pos().x()

	@property
	def y(self) -> float:
		return self.pos().y()

	@property
	def position(self) -> QPointF:
		return QPointF(self.x, self.y)

	@position.setter
	def position(self, value):
		self.setPos(value)

	def delete(self):
		if scene := self.scene():
			scene.removeItem(self)
			self._actionPool.delete()
			del self._actionPool
			return
		if groupRemove := getattr(self.labelGroup, 'removeItem', None) is not None:
			groupRemove(self)
			return


AnnotationTextVar = TypeVar('AnnotationTextVar', bound=AnnotationText)


class AnnotationLabels(list[AnnotationTextVar], Stateful, ColorGradientMixin, tag=...):
	__typeCache__: ClassVar[dict[Type[AnnotationTextVar], Type[list[AnnotationTextVar]]]] = {}
	__labelClass: ClassVar[Type[AnnotationTextVar]] = AnnotationText

	source: Any
	surface: Surface

	enabled: bool
	position: DisplayPosition
	labelHeight: Length | Size.Height
	offset: Length | Size.Height

	_enabled: bool

	def __class_getitem__(cls, item: Type[AnnotationText]):
		if not issubclass(item, AnnotationText):
			raise TypeError('item must be a subclass of PlotLabels')
		if item not in cls.__typeCache__:
			cls.__typeCache__[item] = type(f'{item.__name__}Labels', (cls,), {'__labelClass': item})
		return cls.__typeCache__[item]

	def pre_init(self, source, surface, **kwargs) -> dict:
		self.source = source
		self.surface = surface
		kwargs = self.prep_init(kwargs)
		return kwargs

	def __init__(self, source: Any, surface: Surface, *args, **kwargs):
		kwargs = self.pre_init(source, surface, **kwargs)
		super(AnnotationLabels, self).__init__()
		self.post_init(**kwargs)
		self.setItemState(kwargs)

	def post_init(self, **state: dict):
		pass

	# ======= abstract methods ======== #
	@abstractmethod
	def refresh(self):
		...

	@abstractmethod
	def onDataChange(self, axis: Axis):
		...

	""" Called when the data of the axis changes. """

	@abstractmethod
	def onAxisTransform(self, axis: Axis):
		...

	""" 
	Called when the axis transform changes.
	For example, when the graph timeframe window changes. 
	"""

	@abstractmethod
	def labelFactory(self, **kwargs) -> 'AnnotationText':
		...

	""" Creates labels for the data."""

	# ======= shared methods ======== #
	def resize(self, newSize: int):
		currentSize = len(self)
		if newSize > currentSize:
			self.extend([self.labelFactory() for _ in range(newSize - currentSize)])
		elif newSize < currentSize:
			for _ in range(currentSize - newSize):
				self.pop().delete()

	def parseSize(self, value: str | float | int, default) -> Length | Size.Height | Size.Width:
		match value:
			case str(value):
				unit = ''.join(re.findall(r'[^\d\.\,]+', value)).strip(' ')
				match unit:
					case 'cm':
						value = Centimeter(float(value.strip(unit)))
						value.precision = 3
						value.max = 10
						return value
					case 'mm':
						value = Millimeter(float(value.strip(unit)))
						value.precision = 3
						value.max = 10
						return value
					case 'in':
						value = Inch(float(value.strip(unit)))
						value.precision = 3
						value.max = 10
						return value
					case 'pt' | 'px':
						return Size.Height(float(value.strip(unit)), absolute=True)
					case '%':
						return Size.Height(float(value.strip(unit)) / 100, relative=True)
					case 'lw':
						match self.source:
							case GraphItem(graphic=HasWeight(weight_px=_)):
								value = float(value.strip(unit))
								return LineWeight(value, relative=True)
							case _:
								return value
					case _:
						try:
							return Centimeter(float(value))
						except Exception as e:
							log.error(e)
							return Centimeter(1)
			case float(value) | int(value):
				return Centimeter(float(value))
			case _:
				log.error(f'{value} is not a valid value for labelHeight.  Using default value of 1cm for now.')
				return default

	# Section .properties
	# ======= state properties ======== #

	# ----------- enabled ------------- #
	@StateProperty(default=True, allowNone=False, singleVal=True)
	def enabled(self) -> bool:
		return getattr(self, '_enabled', True)

	@enabled.setter
	def enabled(self, value):
		self._enabled = value

	@enabled.after
	def enabled(self) -> Callable:
		return self.refresh

	# ----------- format ------------- #
	@StateProperty(key='format', default=None, allowNone=False)
	def format_spec(self) -> str | dict:
		return getattr(self, '_format_spec', None)

	@format_spec.setter
	def format_spec(self, value: str | dict):
		self._format_spec = value

	def format_value(self, value: Measurement) -> str:
		format_spec = self.format_spec
		if format_spec is not None:
			if isinstance(value, Measurement):
				match format_spec:
					case str():
						return value.__format__(format_spec)
					case dict():
						return value.__format__('', **format_spec)
		elif value is None:
			return "⋯"
		return str(value)

	# ----------- opacity ------------- #
	@StateProperty(default=DefaultGroup('100%', 1.0), allowNone=False, after=refresh)
	def opacity(self) -> float:
		return self._opacity

	@opacity.setter
	def opacity(self, value: float):
		if getattr(self, '_opacity', 1) != value:
			list(map(lambda x: x.setOpacity(value), self))
		self._opacity = value

	@opacity.decode
	def opacity(value: int | str) -> float:
		if isinstance(value, str):
			number = float((numberRegex.search(value) or {'number': 1})['number'])
			if '%' in value:
				value = (number or 100) / 100
				value = sorted((value, 0, 1))[1]
			else:
				value = number
		if value > 100:
			value /= 255
		if value >= 100:
			value /= 100
		value = sorted((0, value, 1))[1]
		return value

	@opacity.encode
	def opacity(value: float) -> str:
		return f'{value * 100:.4g}%'

	@property
	def fill_brush(self) -> Dict[Number, QBrush]:
		values = self._ticks.tick_values
		if (gradient := self.gradient) is not None:
			return {value: QBrush(gradient.get_color_for_value(value).QColor) for value in values}
		return {value: QBrush(self.color.QColor) for value in values}

	def _set_fill_brush(self, brushes: Dict[Number, QBrush]):
		for label in self:
			label.setBrush(brushes[label.value])

	def get_label_color(self, label: AnnotationText) -> Color:
		if (gradient := self.gradient) is not None:
			return gradient.get_color_for_value(label.value)
		return self.color

	# ---------- position ------------ #
	@StateProperty(default=DisplayPosition.Auto, allowNone=False, singleVal=True)
	def position(self) -> DisplayPosition:
		return getattr(self, '_position', Unset) or type(self).position.default(type(self))

	@position.setter
	def position(self, value: DisplayPosition):
		self._position = value

	@position.decode
	def position(self, value: str) -> DisplayPosition:
		return DisplayPosition[value]

	# ----------- height ------------- #
	@StateProperty(key='height', default=Centimeter(0.5), allowNone=False)
	def labelHeight(self) -> Length | Size.Height:
		value = getattr(self, '_labelHeight', Unset) or type(self).labelHeight.default(type(self))
		return value

	@labelHeight.setter
	def labelHeight(self, value: Length | Size.Height):
		self._labelHeight = value

	@labelHeight.decode
	def labelHeight(self, value: str | float | int) -> Length | Size.Height:
		return self.parseSize(value, type(self).labelHeight.default(type(self)))

	@labelHeight.encode
	def labelHeight(self, value: Length | Size.Height) -> str:
		if isinstance(value, Length) or hasattr(value, 'precision'):
			return f'{value:.3f}'
		return value

	@labelHeight.after
	def labelHeight(self) -> Callable:
		return self.refresh

	# ----------- offset ------------- #m
	@StateProperty(default=Size.Height(5, absolute=True), allowNone=False)
	def offset(self) -> Length | Size.Height | Percentage:
		if (offset := getattr(self, '_offset', Unset)) is not Unset:
			return offset
		return type(self).offset.default(type(self))

	@offset.setter
	def offset(self, value: Length | Size.Height | Percentage):
		self._offset = value

	@offset.decode
	def offset(self, value: str | float | int) -> Length | Size.Height:
		return self.parseSize(value, type(self).offset.default(type(self)))

	@offset.encode
	def offset(self, value: Length | Size.Height) -> str:
		if isinstance(value, Length) or hasattr(value, 'precision'):
			return f'{value:.3f}'
		return value

	@offset.after
	def offset(self) -> Callable:
		return self.refresh

	# --------- alignment ------------ #
	@StateProperty(default=None, allowNone=True)
	def alignment(self) -> Alignment | None:
		return getattr(self, '_alignment', Unset) or type(self).alignment.default(type(self)) or self.alignmentAuto

	@alignment.setter
	def alignment(self, value: Alignment | None):
		self._alignment = value

	@alignment.decode
	def alignment(value: str | int | tuple[AlignmentFlag, AlignmentFlag] | AlignmentFlag) -> Alignment:
		if isinstance(value, (str, int)):
			alignment = AlignmentFlag[value]
		elif value is None:
			alignment = AlignmentFlag.Center
		elif isinstance(value, tuple):
			return Alignment(*value)
		else:
			alignment = AlignmentFlag.Center
		return Alignment(alignment)

	# ======= label properties ======= #
	@property
	def textSize_px(self) -> float:
		textHeight = self.labelHeight
		if isinstance(textHeight, Dimension):
			if textHeight.absolute:
				textHeight = float(textHeight)
			else:
				textHeight = float(textHeight.toAbsolute(self.text_size_relative_to))
		elif isinstance(textHeight, Length):
			dpi = getDPI(self.surface.scene().view.screen())
			# dpi = 1080 / Centimeter(13.5).inch
			textHeight = float(textHeight.inch) * dpi
		return textHeight

	@property
	def text_size_relative_to(self) -> Length | Size.Height | float:
		return self.surface.boundingRect().height()

	@property
	def offset_px(self) -> float:
		offset = self.offset
		match offset, self.source:
			case LineWeight(), GraphItem(graphic=HasWeight(weight_px=_) as p):
				offset = offset.toAbsoluteF(p.weight_px)
			case Dimension(absolute=True), _:
				offset = float(offset)
			case Dimension(relative=True), _:
				offset = float(offset.toAbsolute(self.offset_relative_to))
			case Length(), _:
				dpi = getDPI(self.surface.scene().view.screen())
				offset = float(offset.inch) * dpi
			case Percentage(), _:
				offset = float(offset) * self.offset_relative_to
			case _, _:
				offset = float(offset)
		return offset

	@property
	def offset_relative_to(self) -> Length | Dimension:
		return self.surface.boundingRect().height()

	@property
	def alignmentAuto(self) -> Alignment:
		match self.position:
			case DisplayPosition.Top:
				return Alignment(AlignmentFlag.TopCenter)
			case DisplayPosition.Bottom:
				return Alignment(AlignmentFlag.BottomCenter)
			case DisplayPosition.Left:
				return Alignment(AlignmentFlag.CenterRight)
			case DisplayPosition.Right:
				return Alignment(AlignmentFlag.CenterLeft)
			case DisplayPosition.Center | DisplayPosition.Auto:
				return Alignment(AlignmentFlag.Center)
