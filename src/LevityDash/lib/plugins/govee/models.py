"""Built-in Govee model presets: byte offsets as data, not code-per-model.

Ported from Home Assistant's `govee-ble`_ parser - the *detection table*, not
the library. LevityDash keeps its own config-driven ``BLEPayloadParser``
(hex-slice + math expression) as the per-model definition mechanism, so a
preset is just a named bundle of the same settings a user could write by hand.
Selecting ``GVH5102`` gets you known-good slices instead of deriving them from
a hex dump.

.. _govee-ble: https://github.com/Bluetooth-Devices/govee-ble

**How detection works here.** Upstream matches sequentially on payload length,
then local-name substring, then manufacturer ID, then service UUID. We use the
name substring only: it is the signal that survives LevityDash's config
(devices are configured by advertised name because macOS randomises addresses
per machine), and it is what distinguishes models *within* the shared
``0xEC88``/``0x0001`` manufacturer IDs anyway.

**Offsets are hex-character indices, not byte indices.** ``BLEPayloadParser``
slices ``payload.hex()``, so each byte is two positions: HA's ``data[2:5]`` is
``[4:10]`` here. Preserved rather than "fixed" because it is the format already
in every user's config file.

**Coverage.** The plaintext families whose layout the slice+expression model
can express, centred on the H5102 and H5075 families (the physically tested
hardware). Deliberately absent:

- **H5121-H5130** - encrypted payloads (AES + CRC). Out of scope by decision;
  needs real crypto, not a byte slice.
- **H5074 / H5051 / H5052 / H5071** - little-endian ``struct``-packed. The
  slice model reads big-endian hex runs and cannot express these.
- **H5178 / H5181-H5198** - multi-probe: one advertisement carries several
  sensors distinguished by an in-payload sensor ID, which needs a key per
  probe rather than a key per field.

Unknown models still work - they fall back to the H5102 defaults, which is
what the plugin shipped before presets existed.
"""
from typing import Dict, NamedTuple, Optional, Tuple

__all__ = ['ModelPreset', 'PRESETS', 'DEFAULT_PRESET', 'detect_model', 'preset_for']

#: Advertisements sometimes have this beacon glued onto the end; upstream
#: strips a fixed 25 bytes when the payload is longer than 25 and contains it.
#: Both of the repo's real GVH5102 captures are 31 bytes with this tail.
INTELLI_ROCKS_TAIL = b'INTELLI_ROCKS'
INTELLI_ROCKS_LENGTH = 25


class ModelPreset(NamedTuple):
	"""One model family's payload layout.

	``fields`` maps a schema source key to ``BLEPayloadParser`` kwargs, so a
	preset and a hand-written config section are the same shape - a preset is
	a default, never a separate code path.
	"""

	model: str
	#: Advertised-name substrings that select this preset, upstream's order.
	names: Tuple[str, ...]
	#: Payload lengths in bytes after the INTELLI_ROCKS trim. Advisory: a
	#: length mismatch is logged, not fatal, since the slices may still work.
	lengths: Tuple[int, ...]
	fields: Dict[str, dict]
	notes: str = ''


#: Temperature and humidity share a 3-byte big-endian field: the value encodes
#: tenths of a degree in its upper digits and tenths of a percent in its lower
#: three, so both come from one slice with different arithmetic.
#:
#: `signBit` is a parser flag rather than part of the expression on purpose:
#: `parseMathString` tokenizes bare identifiers as variables, so a hex literal
#: (`0x800000`) parses as a variable named `x800000`, and a conditional turns
#: `if`/`else` into function parameters. Sign handling has to be data.
_TEMP_HUMID_3BYTE = {
	'temperature': {'expression': 'val / 10000', 'signBit': 23},
	'humidity': {'expression': 'payload % 1000 / 1000'},
}

#: Battery is a single byte; the high bit is an error flag upstream, so mask
#: it off rather than reporting a 200% battery on a sensor fault.
_BATTERY = {'expression': 'val % 128'}


PRESETS: Dict[str, ModelPreset] = {
	# --- H5100 family: 3-byte temp/humid at byte 2 ---------------------------
	# Upstream groups these into one handler (data[2:6]); one preset covers
	# all of them. Includes the GVH5102 this plugin was originally written for.
	'H5102': ModelPreset(
		model='H5102',
		names=(
			'H5100', 'H5101', 'H5102', 'H5103', 'H5104', 'H5105',
			'H5108', 'H5110', 'H5174', 'H5177', 'GV5179', 'H5179',
		),
		lengths=(6, 8),
		fields={
			'temperature': {'startingByte': 4, 'endingByte': 10, **_TEMP_HUMID_3BYTE['temperature']},
			'humidity': {'startingByte': 4, 'endingByte': 10, **_TEMP_HUMID_3BYTE['humidity']},
			'battery': {'startingByte': 10, 'endingByte': 12, **_BATTERY},
		},
		notes='Tested against real GVH5102 captures (tests/plugins/test_govee.py).',
	),

	# --- H5072 family: same layout shifted one byte earlier ------------------
	'H5075': ModelPreset(
		model='H5075',
		names=('H5072', 'H5075', 'H5129'),
		lengths=(6,),
		fields={
			'temperature': {'startingByte': 2, 'endingByte': 8, **_TEMP_HUMID_3BYTE['temperature']},
			'humidity': {'startingByte': 2, 'endingByte': 8, **_TEMP_HUMID_3BYTE['humidity']},
			'battery': {'startingByte': 8, 'endingByte': 10, **_BATTERY},
		},
		notes='Untested against hardware; offsets follow govee-ble data[1:5].',
	),

	# --- H5127 presence sensor ----------------------------------------------
	# No temperature at all; listed so a name match does not silently fall
	# through to a thermometer preset and report nonsense degrees.
	'H5127': ModelPreset(
		model='H5127',
		names=('H5127',),
		lengths=(6,),
		fields={},
		notes='Presence/motion only - no thermometer fields. Not yet wired to a schema key.',
	),
}

#: What an unrecognised device gets. The H5102 family is both the most common
#: and what the plugin hardcoded before presets, so this preserves prior
#: behaviour for anything the table does not name.
DEFAULT_PRESET = PRESETS['H5102']


def trim_payload(payload: bytes) -> bytes:
	"""Strip the INTELLI_ROCKS beacon some firmware appends.

	Length-guarded exactly as upstream: a genuine long payload without the
	marker is left alone.
	"""
	if len(payload) > INTELLI_ROCKS_LENGTH and INTELLI_ROCKS_TAIL in payload:
		return payload[:-INTELLI_ROCKS_LENGTH]
	return payload


def detect_model(advertisedName: Optional[str]) -> Optional[ModelPreset]:
	"""Find the preset whose name substrings match ``advertisedName``.

	Returns ``None`` rather than the default when nothing matches, so callers
	can tell "recognised" from "assumed" - the plugin logs the difference.
	"""
	if not advertisedName:
		return None
	name = str(advertisedName).upper()
	for preset in PRESETS.values():
		for candidate in preset.names:
			# Tolerate the GV/GVH prefix variance in advertised names
			# ('GVH5102_6736' vs 'GV5179_1A2B') by matching the digits.
			if candidate.upper() in name or candidate.upper().lstrip('GVH') in name:
				return preset
	return None


def preset_for(model: Optional[str] = None, advertisedName: Optional[str] = None) -> ModelPreset:
	"""Resolve a preset from an explicit model, else the advertised name.

	Explicit configuration wins over detection: a user who wrote
	``model = H5075`` has said something the advertisement cannot contradict.
	"""
	if model:
		key = str(model).upper().lstrip('GVH').lstrip('GV')
		for name, preset in PRESETS.items():
			if name.upper().lstrip('H') == key.lstrip('H'):
				return preset
		if (detected := detect_model(str(model))) is not None:
			return detected
	if (detected := detect_model(advertisedName)) is not None:
		return detected
	return DEFAULT_PRESET
