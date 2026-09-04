"""A plugin's class-level `schema` survives being turned into a `Schema`.

`Schema.__init__` treats its `source` as scratch: it pops `ignored`,
`keyMaps`, `dataMaps`, `identityKey`, `calculations` and `aliases` out of it
and replaces the remaining values with `UnitMetaData`. `Plugin.__init__`
passes the plugin *class's* `schema` attribute, which every instance of that
class shares.

With one instance per plugin that was invisible. The Govee multi-device
rewrite made two instances of one class, and the second got a schema with no
dataMaps and no identityKey - so its datagrams had no 'realtime' group and
`__dataParse` died on a KeyError, live, with the first device working fine.
"""
import pytest

from LevityDash.lib.plugins.schema import Schema


class _FakePlugin:
	"""`Schema` only reads `.name` off its plugin, and registers under it."""

	def __init__(self, name):
		self.name = name

	def __hash__(self):
		return hash(self.name)


def _source():
	return {
		'timestamp': {'type': 'datetime', 'sourceUnit': 'epoch', 'sourceKey': 'timestamp'},
		'indoor.temperature.temperature': {'type': 'temperature', 'sourceUnit': 'c', 'sourceKey': 'temperature'},
		'identityKey': '@deviceIdentity',
		'aliases': {'x': 'y'},
		'keyMaps': {'a': 'b'},
		'dataMaps': {'BLEAdvertisementData': {'realtime': ()}},
	}


def test_source_dict_is_not_consumed():
	source = _source()
	Schema(plugin=_FakePlugin('first'), source=source)
	assert source['dataMaps'] == {'BLEAdvertisementData': {'realtime': ()}}
	assert source['identityKey'] == '@deviceIdentity'
	assert source['aliases'] == {'x': 'y'}
	assert source['keyMaps'] == {'a': 'b'}


def test_two_instances_sharing_one_source_get_the_same_schema():
	# The exact live failure: instance two built from instance one's leftovers.
	source = _source()
	first = Schema(plugin=_FakePlugin('first'), source=source)
	second = Schema(plugin=_FakePlugin('second'), source=source)

	assert second.dataMaps == first.dataMaps
	assert second.dataMaps != {}
	assert second.identityKey == first.identityKey == '@deviceIdentity'
	assert second.aliases == first.aliases


def test_value_keys_are_not_replaced_in_the_callers_dict():
	# __init__ also rewrites every remaining dict value into UnitMetaData.
	source = _source()
	Schema(plugin=_FakePlugin('first'), source=source)
	assert isinstance(source['indoor.temperature.temperature'], dict)
	assert source['indoor.temperature.temperature']['sourceKey'] == 'temperature'
