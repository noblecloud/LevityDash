"""Where to cut a printed number so a column of them lines up.

The text is never changed. `split` returns the part that sits left of the alignment edge (the head)
and the part that hangs to its right (the tail), and the two always join back into the input.

`decimal` cuts at the decimal point, so every point in a column falls on one vertical line. A value with
no point is cut after its last digit, as if the point sat there. `end` cuts after the last digit,
which right-aligns the digits and lets the unit hang.
"""

import re

__all__ = ('MODES', 'split')

MODES = ('end', 'decimal')

_POINT = re.compile(r'\.(?=\d)')
_COMMA = re.compile(r'(?<=\d),(?=\d{1,2}(?!\d))')


def _lastDigit(text: str) -> int:
	for i in range(len(text) - 1, -1, -1):
		if text[i].isdigit():
			return i + 1
	return -1


def split(text: str, mode: str) -> tuple[str, str]:
	"""Cut `text` into (head, tail); `head + tail == text`."""
	if not text:
		return '', ''
	end = _lastDigit(text)
	if end < 0:
		return text, ''
	if mode == 'decimal':
		points = list(_POINT.finditer(text))
		if points:
			i = points[-1].start()
			return text[:i], text[i:]
		commas = list(_COMMA.finditer(text))
		if len(commas) == 1 and '.' not in text:
			i = commas[0].start()
			return text[:i], text[i:]
	return text[:end], text[end:]
