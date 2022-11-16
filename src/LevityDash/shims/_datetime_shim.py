
import datetime as _datetime_
from platform import system

_strip_char, _strip_char_bad = ('#', '-') if system() == 'Windows' else ('-', '#')

from re import compile as _re_compile, sub as _re_sub

_find_regex = _re_compile(fr'(?<!%%)(?<=%)[{_strip_char_bad}](?=[dmHIMSj])')

class datetime(_datetime_.datetime):
	def strftime(self, fmt):
		fmt = _find_regex.sub(_strip_char, fmt)
		return _datetime_.datetime.strftime(self, fmt)

def __getattr__(name):
	if name == 'datetime':
		return datetime
	return getattr(_datetime_, name)

def install():
	import sys
	sys.modules['datetime'] = sys.modules[__name__]
