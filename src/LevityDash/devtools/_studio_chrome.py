"""Dev-only: the light and dark looks of the Studio's own controls. Shared by every Studio editor.

Not the colour theme a dashboard is drawn in (`_studio_themes.py`); this styles the widgets.
"""
from typing import Dict

from PySide6.QtGui import QColor, QPalette


#
# Both themes set every colour role the widgets read, so no role falls back to the platform's
# own palette (a dark system gave the light theme a mixed palette). The sheet covers what a
# palette cannot reach: combo popups, tooltips, menus and disabled text.

THEMES = {
	'dark': {
		'window': '#161b22', 'text': '#e6edf3', 'base': '#0d1117', 'alt': '#161b22', 'button': '#21262d', 'highlight': '#2f81f7',
		'highlightText': '#ffffff', 'muted': '#8b949e', 'placeholder': '#7d8590', 'disabled': '#6e7681', 'border': '#30363d',
		'tipBase': '#21262d',
	},
	'light': {
		'window': '#f6f8fa', 'text': '#1f2328', 'base': '#ffffff', 'alt': '#eef0f3', 'button': '#e6e9ed', 'highlight': '#0969da',
		'highlightText': '#ffffff', 'muted': '#59636e', 'placeholder': '#6e7781', 'disabled': '#8c959f', 'border': '#d0d7de',
		'tipBase': '#ffffff',
	},
}


def themePalette(t: Dict[str, str]) -> QPalette:
	p = QPalette()
	Role, Group = QPalette.ColorRole, QPalette.ColorGroup
	for role, key in ((Role.Window, 'window'), (Role.WindowText, 'text'), (Role.Base, 'base'), (Role.AlternateBase, 'alt'),
	                  (Role.Text, 'text'), (Role.Button, 'button'), (Role.ButtonText, 'text'), (Role.Highlight, 'highlight'),
	                  (Role.HighlightedText, 'highlightText'), (Role.PlaceholderText, 'placeholder'), (Role.ToolTipBase, 'tipBase'),
	                  (Role.ToolTipText, 'text'), (Role.BrightText, 'text'), (Role.Link, 'highlight')):
		p.setColor(role, QColor(t[key]))
	for role in (Role.WindowText, Role.Text, Role.ButtonText):
		p.setColor(Group.Disabled, role, QColor(t['disabled']))
	p.setColor(Group.Disabled, Role.Base, QColor(t['alt']))
	p.setColor(Group.Disabled, Role.Button, QColor(t['window']))
	for role in (Role.Light, Role.Midlight, Role.Mid, Role.Dark, Role.Shadow):
		p.setColor(role, QColor(t['border']))
	return p


def themeSheet(t: Dict[str, str]) -> str:
	return f"""
QToolTip {{ color: {t['text']}; background-color: {t['tipBase']}; border: 1px solid {t['border']}; padding: 3px; }}
QComboBox QAbstractItemView, QCompleter QAbstractItemView {{ color: {t['text']}; background-color: {t['base']};
	selection-color: {t['highlightText']}; selection-background-color: {t['highlight']}; outline: 0; }}
QMenu {{ color: {t['text']}; background-color: {t['base']}; border: 1px solid {t['border']}; }}
QMenu::item:selected {{ color: {t['highlightText']}; background-color: {t['highlight']}; }}
QMenu::item:disabled {{ color: {t['disabled']}; }}
QToolButton {{ color: {t['text']}; }}
QToolButton:disabled, QLabel:disabled, QCheckBox:disabled {{ color: {t['disabled']}; }}
QLineEdit, QAbstractSpinBox {{ color: {t['text']}; background-color: {t['base']}; selection-color: {t['highlightText']};
	selection-background-color: {t['highlight']}; }}
QLineEdit:disabled, QAbstractSpinBox:disabled {{ color: {t['disabled']}; background-color: {t['alt']}; }}
"""
