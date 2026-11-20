"""Where to cut a printed value so a column of them lines up.

The text is never changed. `split` returns the part that sits left of the alignment edge (the head)
and the part that hangs to its right (the tail), and the two always join back into the input. The first
character of the tail is the anchor: it starts on the edge.

`decimal` cuts at the decimal point, so every point in a column falls on one vertical line. A value with
no point is cut after its last digit, as if the point sat there. `end` cuts after the last digit,
which right-aligns the digits and lets the unit hang.

Three more modes pick the anchor yourself (CSS `text-align: "."` is the model for the first):

- `char:X` cuts before a character, the first one in the text: `char::` lines `9:41` and `12:05` up on the
  colon. `char:X@N` takes the Nth one, and a negative N counts from the end (`char:.@-1`, the last point).
- `nth:N` cuts before the Nth character (1 is the first); a negative N counts from the end (`nth:-1`
  anchors on the last character).
- `special:N` cuts before the Nth special character: one that is not a digit, a letter or a space, so a
  point, comma, colon, slash, `%` or `°`. A leading sign is not counted. `special:-1` is the last one.

A value with no such character falls back to `end`: the cut goes after its last digit, or past the whole
text when it has no digit.
"""

import re

__all__ = ('MODES', 'ANCHORS', 'parse', 'split', 'anchored')

MODES = ('end', 'decimal')
ANCHORS = ('char', 'nth', 'special')

_POINT = re.compile(r'\.(?=\d)')
_COMMA = re.compile(r'(?<=\d),(?=\d{1,2}(?!\d))')


def _lastDigit(text: str) -> int:
	for i in range(len(text) - 1, -1, -1):
		if text[i].isdigit():
			return i + 1
	return -1


_CHAR = re.compile(r'^char:(.)(?:@(-?\d+))?$', re.S)
_INDEX = re.compile(r'^(nth|special):(-?\d+)$')


def parse(spec) -> str:
	"""`spec` as the canonical string `split` takes, or ValueError. Accepts `end`, `decimal`, `char:X`,
	`char:X@N`, `nth:N`, `special:N`, and the mapping forms `{char: '.', occurrence: 1}`, `{nth: 3}` and
	`{special: 2}`."""
	if isinstance(spec, dict):
		if len(keys := [k for k in spec if k in ANCHORS]) != 1:
			raise ValueError(f'number-align takes one of {", ".join(ANCHORS)}, not {spec!r}')
		kind = keys[0]
		value = spec[kind]
		if kind == 'char':
			text = str(value)
			if len(text) != 1:
				raise ValueError(f'number-align char is one character, not {value!r}')
			n = int(spec.get('occurrence', 1))
			return parse(f'char:{text}@{n}' if n != 1 else f'char:{text}')
		return parse(f'{kind}:{int(value)}')
	if not isinstance(spec, str):
		raise ValueError(f'number-align must be a string or mapping, not {spec!r}')
	text = spec if spec.startswith('char:') else spec.strip().lower()
	if text in MODES:
		return text
	if m := _CHAR.match(text):
		n = int(m[2]) if m[2] else 1
		if n == 0:
			raise ValueError('number-align char@N counts from 1 (or -1 for the last)')
		return f'char:{m[1]}' if n == 1 else f'char:{m[1]}@{n}'
	if m := _INDEX.match(text):
		if int(m[2]) == 0:
			raise ValueError(f'number-align {m[1]}:N counts from 1 (or -1 for the last)')
		return f'{m[1]}:{int(m[2])}'
	raise ValueError(
		f'number-align must be one of {", ".join(MODES)}, char:X, nth:N or special:N, or none, not {spec!r}'
	)


def _pick(indexes: list[int], n: int) -> int:
	"""The `n`th of `indexes` (1 is the first, -1 the last), or -1."""
	try:
		return indexes[n - 1] if n > 0 else indexes[n]
	except IndexError:
		return -1


def _specials(text: str) -> list[int]:
	"""Where the special characters are: not a digit, a letter or a space. A sign that opens the text is not one."""
	found = [i for i, c in enumerate(text) if not (c.isalnum() or c.isspace())]
	if found and found[0] == 0 and text[0] in '+-\u2212' and text[1:2].isdigit():
		found.pop(0)
	return found


def _anchor(text: str, mode: str) -> int:
	"""The index of the anchor character `mode` names in `text`, or -1 when there is none."""
	if mode.startswith('char:'):
		m = _CHAR.match(mode)
		char, n = m[1], int(m[2]) if m[2] else 1
		return _pick([i for i, c in enumerate(text) if c == char], n)
	kind, n = mode.split(':')
	n = int(n)
	if kind == 'nth':
		i = n - 1 if n > 0 else len(text) + n
		return i if 0 <= i < len(text) else -1
	return _pick(_specials(text), n)


def anchored(text: str, mode: str) -> bool:
	"""Whether `text` has something to line up on under `mode`: a digit for `decimal` and `end`, the anchor for
	the others (`Noon` has neither, so it keeps its plain placement)."""
	if mode in MODES:
		return any(c.isdigit() for c in text)
	return _anchor(text, mode) >= 0 or any(c.isdigit() for c in text)


def split(text: str, mode: str) -> tuple[str, str]:
	"""Cut `text` into (head, tail); `head + tail == text`."""
	if not text:
		return '', ''
	if mode not in MODES and (i := _anchor(text, mode)) >= 0:
		return text[:i], text[i:]
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
