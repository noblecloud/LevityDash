"""Protocol tests for LevityWeb messages (lib/web/messages.py).

Pure encode/decode round trips - no Qt, no scene. The layout *content* is
layout.py's job; here we pin the wire shape itself: version tag, type tags,
viewport/hello validation, and that a layout/update/heartbeat all survive
JSON round trips unchanged.
"""
import json

import pytest

from LevityDash.lib.web.messages import (
	WIRE_VERSION,
	encode_heartbeat,
	encode_layout,
	encode_update,
	parse_hello,
)

ITEM = {
	'name': 'Outdoor',
	'type': 'StackedTitledPanel',
	'z': 0.0,
	'rect': [12.0, 34.0, 500.0, 300.0],
	'parent': None,
	'keys': ['environment.temperature.temperature'],
	'values': {
		'environment.temperature.temperature': {
			'value': 21.5,
			'formatted': '21.5 °C',
			'source': 'OpenMeteo',
			'key': 'environment.temperature.temperature',
		},
	},
	'texts': [{'rect': [20.0, 40.0, 100.0, 20.0], 'text': '21.5 °C', 'font': 'Nunito', 'size': 22.0, 'weight': 400, 'color': '#ffffff'}],
}


def _round_trip(message: dict) -> dict:
	return json.loads(json.dumps(message))


def test_wire_version_is_one():
	assert WIRE_VERSION == 1


def test_layout_message_shape_and_round_trip():
	message = encode_layout(viewport={'w': 1800, 'h': 1090, 'dpr': 1.0}, items=[ITEM])
	message = _round_trip(message)
	assert message['v'] == 1
	assert message['type'] == 'layout'
	assert message['viewport'] == {'w': 1800, 'h': 1090, 'dpr': 1.0}
	assert message['items'] == [ITEM]


def test_update_message_shape():
	message = encode_update(items={'Outdoor': ITEM, 'wind': {'name': 'wind'}})
	message = _round_trip(message)
	assert message['type'] == 'update'
	assert message['items']['Outdoor'] == ITEM
	assert message['items']['wind'] == {'name': 'wind'}


def test_heartbeat_shape():
	message = _round_trip(encode_heartbeat(seq=7, uptime=12.5))
	assert message['type'] == 'heartbeat'
	assert message['seq'] == 7
	assert message['uptime'] == 12.5


def test_parse_hello_accepts_a_valid_viewport():
	assert parse_hello({'type': 'hello', 'w': 1920, 'h': 1080, 'dpr': 2.0}) == {'w': 1920, 'h': 1080, 'dpr': 2.0}


def test_parse_hello_defaults_dpr():
	assert parse_hello({'type': 'hello', 'w': 800, 'h': 600})['dpr'] == 1.0


@pytest.mark.parametrize(
	'message, fragment',
	[
		({'type': 'hello', 'h': 600}, 'w'),
		({'type': 'hello', 'w': 800}, 'h'),
		({'type': 'hello', 'w': 'wide', 'h': 600}, 'w'),
		({'type': 'hello', 'w': 800, 'h': -1}, 'h'),
		({'type': 'hello', 'w': 800, 'h': 600, 'dpr': 0}, 'dpr'),
		({'type': 'nope', 'w': 800, 'h': 600}, 'hello'),
	],
)
def test_parse_hello_rejects_garbage(message, fragment):
	with pytest.raises(ValueError, match=fragment):
		parse_hello(message)


def test_parse_hello_rejects_fractional_pixels():
	with pytest.raises(ValueError):
		parse_hello({'type': 'hello', 'w': 800.5, 'h': 600})
