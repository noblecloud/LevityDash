from functools import cached_property
from typing import List, Union

from LevityDash.lib.plugins.dispatcher import MultiSourceContainer
from LevityDash.lib.ui.frontends.PySide.Modules.Handles.Incrementer import Incrementer
from LevityDash.lib.ui.frontends.PySide.Modules import Label, Panel
from LevityDash.lib.utils.geometry import LocationFlag, Position, Size
from LevityDash.lib.utils import _Panel


class Attribute:

	def __init__(self, parent: _Panel, key: Union[str, List[str]], ):
		self.parent = parent
		self.key = key

	@property
	def value(self) -> int:
		return getattr(self.parent, self.key)

	@value.setter
	def value(self, value: int):
		setattr(self.parent, self.key, value)


class IntAttribute(Attribute):
	_type = int

	def __init__(self, value: MultiSourceContainer, key: Attribute, default: int = 0, _min: int = None, _max: int = None, step: int = 1):
		super().__init__(value, key)
		self.default = int(self.value)
		self.min = _min
		self.max = _max
		self.step = step

	def increase(self):
		if self.value + self.step > self.max:
			self.value = self.max
		else:
			self.value += self.step

	def decrease(self):
		if self.value - self.step < self.min:
			self.value = self.min
		else:
			self.value -= self.step


class BoolAttribute(Attribute):
	_type = bool

	def __init__(self, value: MultiSourceContainer, key: Attribute, default: bool = False):
		super().__init__(value, key)
		self.default = default

	def toggle(self):
		self.value = not self.value


class IntIncrementer(Incrementer):
	attribute: Attribute

	def __init__(self, parent, attribute: Union[Attribute, str], **kwargs):
		super().__init__(parent, **kwargs)
		if isinstance(attribute, str):
			attribute = IntAttribute(parent, attribute)
		assert isinstance(attribute, IntAttribute)
		self.attribute = attribute

	@cached_property
	def length(self):
		return 10

	@cached_property
	def width(self):
		return 10

	@property
	def surfaceRect(self):
		return self.parentItem().rect()

	@property
	def surface(self):
		return self.parentItem()

	@property
	def incrementValue(self):
		return self.attribute.step

	def increase(self):
		self.attribute.increase()

	def decrease(self):
		self.attribute.decrease()


def BoolChanger(Incrementer):
	attribute: Attribute

	def __init__(self, parent, attribute: Union[Attribute, str], **kwargs):
		super().__init__(parent, **kwargs)
		if isinstance(attribute, str):
			attribute = IntAttribute(parent, attribute)
		assert isinstance(attribute, BoolAttribute)
		self.attribute = attribute


class AttributeEditor(Label):

	def __init__(self, parent: Panel, attribute: Attribute, *args, **kwargs):
		self.attribute = attribute
		self.offset = -10
		super(AttributeEditor, self).__init__(parent=parent, size=Size(100, 50, absolute=True), *args, **kwargs)
		if isinstance(attribute.value, int):
			self.up = IntIncrementer(parent=self, attribute=attribute, location=Position(1, 0.5, relative=True), alignment=LocationFlag.Right)
			self.down = IntIncrementer(parent=self, attribute=attribute, location=Position(0.0, 0.5, relative=True), alignment=LocationFlag.Left)
			self.signals.resized.connect(self.repositionIncrementers)
			self.repositionIncrementers()
			self.margins.left.setAbsolute(40)
			self.margins.right.setAbsolute(40)

	# elif isinstance(attribute.value, bool):
	# 	self.check =

	# self.down.resetAttribute('_shape', '_path')
	# self.down.setPath(self.down._path)

	def repositionIncrementers(self):
		self.up.updatePosition()
		self.down.updatePosition()

	@property
	def text(self):
		return f'{self.attribute.key}: {self.attribute.value}'

	@text.setter
	def text(self, value):
		return

	def shape(self):
		shape = super(AttributeEditor, self).shape()
		shape += self.up.mapFromParent(self.up.shape())
		shape += self.down.mapFromParent(self.down.shape())
		return shape


class AttributeRect(Panel):

	def __init__(self, parent: Panel, attributes: List[Attribute], *args, **kwargs):
		size = parent.geometry.absoluteSize()
		kwargs['geometry'] = {'x': 0, 'y': 0, 'width': size.width + 200, 'height': size.height + 200}
		super(AttributeRect, self).__init__(parent=parent, *args, **kwargs)
		self.attribute = attributes
		for attribute in attributes:
			attr = AttributeEditor(parent=self, attribute=attribute)
			self.signals.resized.connect(attr.repositionIncrementers)
			attr.repositionIncrementers()
