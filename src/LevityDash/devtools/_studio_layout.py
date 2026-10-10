"""Dev-only: Studio editors for the CSS layout keys (`flex:` and `grid:`), see docs/config/dashboard/layout.md.

Each key is one popover on the Item tab. The same mapping serves two roles, as it does in the stack code:
`flex:` holds the container options (`justify`, `align-items`, `wrap`) when the item is a stack and the item
options (`grow`, `shrink`, `basis`, ...) when its parent is one; `grid:` likewise for a `type: grid` and its
cells. The form shows the parts that apply. A part left on its default writes nothing, so a stack with nothing
set stays a plain stack, and a save carries only what differs.
"""
from typing import Any, List, Optional

from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel

from LevityDash.devtools import _studio_editors as editors

Editor = editors.Editor

STACK_KINDS = ('stack', 'value-stack')
GRID_KIND = 'grid'

JUSTIFY = ['flex-start', 'flex-end', 'center', 'space-between', 'space-around', 'space-evenly', 'stretch']
ALIGN_ITEMS = ['stretch', 'flex-start', 'flex-end', 'center', 'baseline']
ALIGN_SELF = ['auto'] + ALIGN_ITEMS
WRAP = ['nowrap', 'wrap', 'wrap-reverse']
CONTENT = ['normal', 'start', 'end', 'center', 'stretch', 'space-between', 'space-around', 'space-evenly']
ITEMS = ['stretch', 'start', 'end', 'center', 'baseline']
SELF = ['auto'] + ITEMS
TRACKS = ['1fr', '2fr', '3fr', 'auto', 'min-content', 'max-content', 'minmax(100px, 1fr)', 'fit-content(200px)', '100px', '25%']

FLEX_CONTAINER = ('justify', 'align-items', 'wrap')
FLEX_ITEM = ('grow', 'shrink', 'basis', 'min', 'max', 'cross', 'order', 'align-self')
GRID_CONTAINER = ('columns', 'rows', 'auto-columns', 'auto-rows', 'auto-flow', 'dense', 'gap',
                  'justify-content', 'align-content', 'justify-items', 'align-items')
GRID_ITEM = ('column', 'row', 'column-span', 'row-span', 'justify-self', 'align-self')


def choice(options: List[str], unset: str) -> editors.ChoiceEdit:
	"""A dropdown whose first entry is the default, which saves as nothing."""
	return editors.ChoiceEdit([(unset, None)] + [(o, o) for o in options])


class TrackEdit(editors.ChoiceEdit):
	"""One grid track: pick a common one or type any (`240px`, `minmax(80px, 1fr)`, `repeat(auto-fit, 120px)`)."""

	def __init__(self, unset: str = '1fr'):
		super().__init__([(t, t) for t in TRACKS], editable=True)
		self.combo.setCurrentText(unset)

	def value(self):
		return self.combo.currentText().strip() or None

	def setValue(self, value):
		with QSignalBlocker(self.combo):
			self.combo.setCurrentText('' if value is None else str(value))


class AutoTrackEdit(TrackEdit):
	"""`auto-columns` / `auto-rows`: empty is the default (`1fr`), and saves as nothing."""

	def __init__(self):
		super().__init__()
		self.combo.setCurrentText('')
		self.combo.lineEdit().setPlaceholderText('default (1fr)')


class TrackListEdit(editors.ListEditor):
	"""`columns` / `rows`: one entry per track."""

	def __init__(self, what: str):
		super().__init__(TrackEdit, lambda items: '1fr', f'+ Add {what}', f'No {what}s. Items make their own as they are placed.')


class BasisEdit(Editor):
	"""`basis`: not set, `auto` (sized by the text it shows), or a size."""

	def __init__(self):
		super().__init__()
		box = QHBoxLayout(self)
		box.setContentsMargins(0, 0, 0, 0)
		box.setSpacing(4)
		self.mode = QComboBox()
		self.mode.addItem('not set', None)
		self.mode.addItem('by its text', 'auto')
		self.mode.addItem('a size', 'size')
		self.mode.activated.connect(self._moded)
		box.addWidget(self.mode)
		self.size = editors.SizeEdit(nullable=False, ref='full')
		self.size.changed.connect(self._emit)
		box.addWidget(self.size, 1)
		self.size.setVisible(False)

	def _moded(self, _):
		self.size.setVisible(self.mode.currentData() == 'size')
		self._emit()

	def setValue(self, value):
		with QSignalBlocker(self.mode):
			if value is None:
				self.mode.setCurrentIndex(0)
			elif str(value).casefold() in ('auto', 'content'):
				self.mode.setCurrentIndex(1)
			else:
				self.mode.setCurrentIndex(2)
				self.size.setValue(value)
		self.size.setVisible(self.mode.currentData() == 'size')

	def value(self):
		match self.mode.currentData():
			case 'auto':
				return 'auto'
			case 'size':
				return self.size.value()
		return None


class LayoutForm(editors._Form):
	"""The parts of a `flex:` or `grid:` mapping. `container` and `item` say which roles to show."""

	keys: tuple = ()
	containerKeys: tuple = ()
	itemKeys: tuple = ()

	def __init__(self):
		super().__init__()
		self.hint = QLabel()
		self.hint.setWordWrap(True)
		self.hint.setStyleSheet('color: palette(placeholder-text); font-size: 11px;')
		self.heads: dict = {}

	def head(self, key: str, text: str):
		"""A small heading above the part named `key`."""
		label = QLabel(f'<b>{text}</b>')
		self.grid.addWidget(label, self._r, 0, 1, 2)
		self._r += 1
		self.heads[key] = label

	def roles(self, container: bool, item: bool):
		for key in self.containerKeys:
			self.showPart(key, container)
		for key in self.itemKeys:
			self.showPart(key, item)
		for key, label in self.heads.items():
			label.setVisible(container if key in self.containerKeys else item)

	def setValue(self, value):
		spec = dict(value or {})
		self._extra = {k: v for k, v in spec.items() if k not in self._known}
		for key, part in self.parts.items():
			with QSignalBlocker(part):
				part.setValue(spec.get(key))

	def value(self):
		out = dict(self._extra)
		for key, part in self.parts.items():
			v = part.value()
			if v is not None and v is not False and v != []:
				out[key] = v
		return out


class FlexForm(LayoutForm):
	containerKeys, itemKeys = FLEX_CONTAINER, FLEX_ITEM

	def __init__(self):
		super().__init__()
		self.head('justify', 'This stack lays out its items like CSS flexbox')
		self.part('justify', 'justify', choice(JUSTIFY, 'not set'), 'justify-content: where the items sit along the stack. Any container option turns the engine on.')
		self.part('align-items', 'align items', choice(ALIGN_ITEMS, 'stretch'), 'align-items: where the items sit across the stack.')
		self.part('wrap', 'wrap', choice(WRAP, 'nowrap'), 'flex-wrap: start a new line when the items do not fit.')
		self.head('grow', 'This item in a flex stack')
		self.part('grow', 'grow', editors.NumberEdit(autoText='default', lo=0, hi=10, step=0.5, decimals=2), 'flex-grow: the share of the free space it takes.')
		self.part('shrink', 'shrink', editors.NumberEdit(autoText='default (1)', lo=0, hi=10, step=0.5, decimals=2), 'flex-shrink: the share of the overflow it gives back.')
		self.part('basis', 'basis', BasisEdit(), 'flex-basis: the size before growing and shrinking.')
		self.part('min', 'min', editors.SizeEdit(nullable=True, autoText='none', ref='full'), 'Smallest size along the stack.')
		self.part('max', 'max', editors.SizeEdit(nullable=True, autoText='none', ref='full'), 'Largest size along the stack.')
		self.part('cross', 'cross size', editors.SizeEdit(nullable=True, autoText='fill', ref='full'), 'Size across the stack; by default the item fills it.')
		self.part('order', 'order', editors.NumberEdit(autoText='as written', lo=-5, hi=5, integer=True), 'Items sort by order, then as written.')
		self.part('align-self', 'align self', choice(ALIGN_SELF[1:], 'auto'), 'Overrides the stack\'s align items for this item.')

	def value(self):
		out = super().value()
		if out.get('wrap') == 'nowrap':
			del out['wrap']
		if out.get('align-items') == 'stretch':
			del out['align-items']
		return out


class GridForm(LayoutForm):
	containerKeys, itemKeys = GRID_CONTAINER, GRID_ITEM

	def __init__(self):
		super().__init__()
		self.head('columns', 'This grid')
		self.part('columns', 'columns', TrackListEdit('column'), 'grid-template-columns')
		self.part('rows', 'rows', TrackListEdit('row'), 'grid-template-rows')
		self.part('auto-columns', 'auto columns', AutoTrackEdit(), 'The size of a column the items need and the list does not give.')
		self.part('auto-rows', 'auto rows', AutoTrackEdit(), 'The size of a row the items need and the list does not give.')
		self.part('auto-flow', 'auto flow', choice(['column'], 'row'), 'Which way items fill the cells.')
		self.part('dense', 'dense', editors.ChoiceEdit([('off', None), ('on', True)]), 'Back-fill holes with later items.')
		self.part('gap', 'gap', editors.SizeEdit(nullable=True, autoText='spacing', ref='full'), 'Between tracks, both ways. Unset takes the stack\'s spacing.')
		self.part('justify-content', 'justify content', choice(CONTENT[1:], 'normal'), 'Where the tracks sit across the width when they do not fill it.')
		self.part('align-content', 'align content', choice(CONTENT[1:], 'normal'), 'Where the tracks sit down the height when they do not fill it.')
		self.part('justify-items', 'justify items', choice(ITEMS[1:], 'stretch'), 'How each item sits in its cell across.')
		self.part('align-items', 'align items', choice(ITEMS[1:], 'stretch'), 'How each item sits in its cell down.')
		self.head('column', 'This item in a grid')
		self.part('column', 'column', editors.NumberEdit(autoText='auto', lo=1, hi=12, integer=True), 'Which column it starts in, counted from 1.')
		self.part('row', 'row', editors.NumberEdit(autoText='auto', lo=1, hi=12, integer=True), 'Which row it starts in, counted from 1.')
		self.part('column-span', 'column span', editors.NumberEdit(autoText='1', lo=1, hi=12, integer=True))
		self.part('row-span', 'row span', editors.NumberEdit(autoText='1', lo=1, hi=12, integer=True))
		self.part('justify-self', 'justify self', choice(SELF[1:], 'auto'), 'Overrides the grid\'s justify items for this item.')
		self.part('align-self', 'align self', choice(SELF[1:], 'auto'), 'Overrides the grid\'s align items for this item.')

	def value(self):
		out = super().value()
		for key in ('justify-items', 'align-items', 'justify-content', 'align-content'):
			if out.get(key) in ('stretch', 'normal'):
				del out[key]
		return out


class _LayoutPopover(editors._Popover):
	formClass: type = LayoutForm
	noun = ''

	def __init__(self):
		super().__init__(self.formClass())

	def setRoles(self, container: bool, item: bool):
		self.form.roles(container, item)
		self._roles = (container, item)

	def summary(self) -> str:
		spec = self._value if isinstance(self._value, dict) else {}
		if not spec:
			return f'{self.noun}: not set'
		return f'{self.noun}: ' + ', '.join(f'{k} {v}' for k, v in spec.items())[:60]


class FlexEdit(_LayoutPopover):
	formClass, noun, title = FlexForm, 'Flex', 'Flex'


class GridEdit(_LayoutPopover):
	formClass, noun, title = GridForm, 'Grid', 'Grid'
