"""What the right-click Source menu offers once Govee is per-device.

The menu enumerates ``LevityDashboard.get_container(key).values()`` and labels
each entry ``source.name``, so per-device instances change what a user sees
when they right-click a panel and open Source. This pins that behaviour: the
menu needs no Govee-specific knowledge, but the *names* it shows are now
device names, and an identity-scoped key must offer only that device.
"""
import pytest

from LevityDash.lib.plugins.builtin.Govee import Govee
from LevityDash.lib.plugins.categories import CategoryItem
from LevityDash.lib.plugins.govee.config import parse_devices


class FakeConfig(dict):
	def sections(self):
		return [k for k in self if k != 'plugin']


TWO_DEVICES = FakeConfig({
	'plugin': {'enabled': 'True'},
	'devices': {'bedroom': 'GVH5102_6736', 'terrarium': 'GVH5102_527D'},
})

BASE_KEY = 'indoor.temperature.temperature'


def _instances():
	return [Govee(device) for device in parse_devices(TWO_DEVICES)]


class TestSourceMenuLabels:
	"""``SourceMenu.addSources`` renders ``source.name`` per container entry."""

	def test_each_device_is_a_distinct_selectable_label(self):
		# Menus.py:618 - `name = k.name`. Distinct names are what makes the
		# two thermometers separately selectable rather than one ambiguous
		# 'Govee' row.
		labels = sorted(i.name for i in _instances())
		assert labels == ['Govee-bedroom', 'Govee-terrarium']
		assert len(set(labels)) == 2

	def test_labels_say_which_room_not_which_protocol(self):
		# The pre-rewrite menu showed a single 'Govee' entry no matter how
		# many thermometers were configured, so a user could not pick one.
		for instance in _instances():
			assert instance.device.alias in instance.name

	def test_names_survive_a_qt_action_round_trip(self):
		# changeSource (Menus.py:628) re-checks actions with
		# `action.text().startswith(source.name)`. That is a prefix match, so
		# one device name must never prefix another - 'Govee-bed' matching
		# both 'Govee-bedroom' and 'Govee-bedroom2' would tick two radio
		# items in an exclusive group.
		names = [i.name for i in _instances()]
		for name in names:
			matches = [other for other in names if other.startswith(name)]
			assert matches == [name], f'{name!r} prefixes another source name: {matches}'


class TestIdentityScopedKeys:
	"""An identity-scoped key belongs to exactly one device."""

	def test_identity_keys_stay_distinct_per_device(self):
		keys = {
			CategoryItem(BASE_KEY).withIdentity(i.device.alias)
			for i in _instances()
		}
		assert {str(k) for k in keys} == {
			f'{BASE_KEY}#bedroom',
			f'{BASE_KEY}#terrarium',
		}

	def test_identity_is_part_of_key_equality(self):
		# If these collapsed, both thermometers would land in one container
		# and the Source menu would be the only way to tell them apart.
		bedroom = CategoryItem(BASE_KEY).withIdentity('bedroom')
		terrarium = CategoryItem(BASE_KEY).withIdentity('terrarium')
		assert bedroom != terrarium
		assert hash(bedroom) != hash(terrarium)
		assert len({bedroom, terrarium}) == 2

	def test_the_unscoped_key_is_still_a_different_key(self):
		# A dashboard asking for the bare key is not implicitly asking for
		# one device's reading - that is what makes adding a second sensor
		# non-breaking for existing saves.
		assert CategoryItem(BASE_KEY) != CategoryItem(BASE_KEY).withIdentity('bedroom')
