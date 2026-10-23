"""Little-endian and signed payload fields, and the H5074 family preset built on them.

The payloads are made with `struct.pack`, so they say exactly what the layout claims; the H5074 offsets follow
govee-ble's description and are not checked against hardware.
"""
import struct

import pytest

from LevityDash.lib.plugins.builtin.Govee import BLEPayloadParser
from LevityDash.lib.plugins.govee.models import detect_model, preset_for


def advert(temperature: float, humidity: float, battery: int) -> bytes:
	return struct.pack('<BhHB', 0, round(temperature * 100), round(humidity * 100), battery) + b'\x00'


def decode(model, payload):
	preset = preset_for(model=model)
	return {field: BLEPayloadParser(field=field, **params)(payload)[field] for field, params in preset.fields.items()}


@pytest.mark.parametrize('temperature,humidity,battery', [
	(21.37, 48.62, 87),
	(0.0, 0.0, 0),
	(-7.5, 99.99, 100),
	(-0.01, 12.34, 1),
	(45.0, 5.0, 127),
])
def test_the_h5074_preset_decodes_what_struct_packed(temperature, humidity, battery):
	values = decode('H5074', advert(temperature, humidity, battery))
	assert values['temperature'] == pytest.approx(temperature, abs=0.005)
	assert values['humidity'] == pytest.approx(humidity, abs=0.005)
	assert values['battery'] == battery


def test_little_endian_reads_the_slice_last_byte_first():
	assert BLEPayloadParser('v', 0, 4, byteOrder='little')(bytes.fromhex('3412'))['v'] == 0x1234
	assert BLEPayloadParser('v', 0, 4)(bytes.fromhex('3412'))['v'] == 0x3412


def test_signed_is_twos_complement_over_the_slice_width():
	assert BLEPayloadParser('v', 0, 4, signed=True)(bytes.fromhex('ffff'))['v'] == -1
	assert BLEPayloadParser('v', 0, 4, signed=True)(bytes.fromhex('7fff'))['v'] == 0x7fff
	assert BLEPayloadParser('v', 0, 2, signed=True)(bytes.fromhex('80'))['v'] == -128
	assert BLEPayloadParser('v', 0, 4, byteOrder='little', signed=True)(bytes.fromhex('00ff'))['v'] == -256


def test_a_bad_byte_order_is_refused():
	with pytest.raises(ValueError):
		BLEPayloadParser('v', 0, 4, byteOrder='middle')


def test_the_family_is_detected_by_name_and_does_not_steal_the_others():
	for name in ('GVH5074_1A2B', 'GVH5051_ABCD', 'Govee_H5052_1234', 'GVH5071_0000'):
		assert detect_model(name).model == 'H5074'
	assert detect_model('GVH5102_6736').model == 'H5102'
	assert detect_model('GVH5075_A1B2').model == 'H5075'
