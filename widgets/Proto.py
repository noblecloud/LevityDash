from typing import Optional, Union

from PyQt5.QtGui import QFont, QPainter
from PySide2.QtCore import QSize, Qt, Signal, Slot
from PySide2.QtWidgets import QBoxLayout, QLabel, QSizePolicy, QWidget
from WeatherUnits import Measurement

from ui.fonts import rounded, weatherGlyph
from utils import Logger, randomColor
from widgets.DynamicLabel import DynamicLabel


@Logger
class ComplicationPrototype(QWidget):
	_direction: QBoxLayout.Direction = None
	_title: Optional[str] = None
	_widget: QWidget = None
	_glyphTitle: Optional[str] = None
	_value: Union[Measurement, float, int, QWidget, None] = None
	_titleOnTop: Optional[bool] = None
	_showTitle: bool
	_showUnit: bool
	_text: str
	_font: QFont
	_isGrid: bool = False
	_square: bool = False
	_subscriptionKey: str = None
	valueWidget: Optional[QWidget]
	valueLabel: Optional[DynamicLabel]
	titleLabel: Optional[DynamicLabel]
	updateSignal = Signal(Measurement)

	def __init__(self, *args, title: str = None,
	             value: Union[Measurement, float, int] = None,
	             widget: QWidget = None,
	             direction: QBoxLayout.Direction = None,
	             showTitle: bool = True,
	             glyphTitle: str = None,
	             showUnit: bool = False,
	             miniature: bool = False,
	             square: bool = False,
	             subscriptionKey: str = None,
	             **kwargs):

		self._title = title
		self._value = value
		self._widget = widget
		self._glyphTitle = glyphTitle
		self._showTitle = showTitle
		self._showUnit = showUnit
		self._direction = direction
		self._square = square
		self._subscriptionKey = subscriptionKey

		local = [item[1:] for item in ComplicationPrototype.__dict__.keys() if item[0:2] != '__' and item[0] == '_']
		super(ComplicationPrototype, self).__init__(*args, **{key: item for key, item in kwargs.items() if key not in local})
		# self.setAttribute(Qt.WA_TranslucentBackground, True)
		# self.setAttribute(Qt.WA_NoSystemBackground, True)
		# self.valueLabel.setAttribute(Qt.WA_NoSystemBackground, True)
		# self.valueLabel.setAttribute(Qt.WA_TranslucentBackground, True)
		# self.title.setAttribute(Qt.WA_NoSystemBackground, True)
		# self.title.setAttribute(Qt.WA_TranslucentBackground, True)
		self.updateSignal.connect(self.updateValueSlot)
		policy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
		policy.setHeightForWidth(True)
		self.setSizePolicy(policy)

	# self.setAttribute(Qt.WA_StyledBackground, True)
	# self.setStyleSheet(f"background: {randomColor()}")

	def resizeEvent(self, event):
		if self._square:
			new_size = QSize(10, 10)
			new_size.scale(event.size(), Qt.KeepAspectRatio)
			self.resize(new_size)
		super(ComplicationPrototype, self).resizeEvent(event)

	def heightForWidth(self, width):
		return width

	@property
	def subscriptionKey(self):
		return self._subscriptionKey if self._subscriptionKey is not None else self.title.lower()

	@subscriptionKey.setter
	def subscriptionKey(self, value):
		self._subscriptionKey = value

	@property
	def canBalance(self):
		return self.valueLabel.isVisible() and not self._isGrid

	@property
	def shouldBeShown(self):
		t = [self.value]
		return any(t)

	@property
	def isEmpty(self):
		t = [self.value]
		return not self.valueLabel.text

	def update(self):
		if self.shouldBeShown:
			self.show()
		else:
			self.hide()
		if self._showTitle and self.title:
			if self.titleLabel.isGlyph:
				self.titleLabel.setGlyph(self.title)
			else:
				self.titleLabel.setText(self.title)
			self.titleLabel.show()
		else:
			self.titleLabel.hide()

		if isinstance(self.value, QWidget):
			self.valueWidget.show()
			self.valueLabel.hide()
			self.layout.removeWidget(self.valueWidget)
			self.valueWidget = self.value
			self.layout.addWidget(self.valueWidget)
		elif isinstance(self.value, str):
			self.valueLabel.setText(self.value)
			self.valueLabel.show()
			self.valueWidget.hide()
		else:
			pass
		self.valueLabel.update()
		super().update()

	@property
	def glyphTitle(self):
		return self._glyphTitle

	@glyphTitle.setter
	def glyphTitle(self, glyph):
		self._title = None
		self._glyphTitle = glyph
		self.titleLabel.setGlyph(glyph)
		self.update()

	@property
	def showTitle(self) -> bool:
		return self._showTitle

	@showTitle.setter
	def showTitle(self, value: bool):
		self._showTitle = value
		if value:
			self.titleLabel.show()
		else:
			self.titleLabel.hide()

	@property
	def title(self):
		title: Optional[str] = self._title if self._glyphTitle is None else self._glyphTitle
		if isinstance(self._value, str):
			return title
		elif title is None and hasattr(self._value, 'title'):
			title = self._value.title
		return title

	@title.setter
	def title(self, title: str):
		self._title = title
		self._glyphTitle = None
		self.titleLabel.setFont(rounded)
		self.update()

	@property
	def value(self) -> Union[str, QWidget, None, Measurement]:
		if isinstance(self._value, Measurement):
			return self._value
		# return self._value.withUnit if self._showUnit else str(self._value)
		elif isinstance(self._value, QWidget):
			return self._value
		elif self._value is None:
			return None
		else:
			return str(self._value)

	@value.setter
	def value(self, value):
		self.valueLabel.value = value
		self.valueWidget.hide()
		self._value = value
		self.update()

	@property
	def widget(self):
		return self._widget

	@widget.setter
	def widget(self, value):
		oldWidget = self._widget
		self._widget = value
		self.layout.replaceWidget(oldWidget, value)
		self._widget.show()
		del oldWidget

	@property
	def showUnit(self) -> bool:
		return self._showUnit

	@showUnit.setter
	def showUnit(self, value: bool):
		self._showUnit = value
		self.update()

	@property
	def layout(self) -> QBoxLayout:
		return super().layout()

	@property
	def direction(self):
		return self._direction

	@direction.setter
	def direction(self, value):
		self._direction = value

	@property
	def maxFontSize(self):
		return self.valueLabel.maxSize if self.valueLabel.maxSize is not None else 30

	@property
	def maxFontSizeTitle(self):
		return self.titleLabel.maxSize if self.valueLabel.maxSize is not None else 20

	@Slot(Measurement)
	def updateValueSlot(self, value):
		self.value = value
		# print(f'{self} updated with {value}')
		if hasattr(self.parent(), 'valueChangedSignal'):
			self.parent().valueChangedSignal.emit(self)
	# print(value)
	# if not self._customTitle:
	# 	self_title(f"{value.title} ({value.unit})" if self.showUnit else value.title)
	# self.valueLabel.setText(str(value))
