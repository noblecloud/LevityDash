"""Scene extraction tests for LevityWeb (lib/web/layout.py).

Two halves:

- The scene half boots its own dashboard scene (module-scoped, ~3s) instead of
  the session fixture: the session scene is resized and refreshed by tests/ui,
  which would make item identities order-dependent. Plugins are never started,
  so every value resolves to None - the *value* branch of diff() is covered
  below with synthetic payloads.
- The diff half is pure dict math over hand-built payloads: text, geometry,
  key, and value changes each count; nothing counts as nothing.
"""
import time

import pytest

from LevityDash.lib.web.layout import _dedupe_keys, _value_payload, diff, snapshot


@pytest.fixture(scope='module')
def scene():
	from LevityDash import LevityDashboard
	from PySide6.QtCore import QTimer

	# The singleton is immutable after init - when an earlier fixture (the
	# session dashboard, from tests/ui or tests/wire) already booted the app,
	# reuse its scene instead of re-booting (which raises TypeError). Booting
	# only happens when this module runs first (tests/web alone).
	if getattr(LevityDashboard, 'scene', None) is not None:
		return LevityDashboard.scene

	LevityDashboard.init()
	LevityDashboard.plugins.load_all()
	app = LevityDashboard.app
	app.init_app()
	QTimer.singleShot(10, LevityDashboard.load_dashboard)
	end = time.monotonic() + 3.0
	while time.monotonic() < end:
		app.processEvents()
		time.sleep(0.005)
	return LevityDashboard.scene


def _named(scene, name):
	for item in snapshot(scene):
		if item['name'] == name:
			return item
	raise KeyError(name)


def test_snapshot_lists_named_items(scene):
	names = [item['name'] for item in snapshot(scene)]
	# The .levity's own skeleton plus the panels auto-generated on load from
	# the seed config's sources (the set varies with detected devices, so
	# assert the stable core).
	assert {'main', 'top', 'bottom', 'precipitation', 'atmosphere', 'temperature', 'clock', 'conditions-sun', 'conditions-left', 'conditions-right'} <= set(names)
	assert {'Indoor', 'Outdoor', 'Wind', 'Condition', 'Details'} <= set(names)


def test_named_item_carries_rect_z_and_type(scene):
	item = _named(scene, 'Outdoor')
	assert isinstance(item['z'], (int, float))
	assert len(item['rect']) == 4
	assert all(isinstance(v, (int, float)) for v in item['rect'])
	assert item['type'] in ('StackedTitledPanel', 'StackedPanel', 'StackedValueStack', 'StackedStack', 'Clock', 'Text')


def test_keys_bubble_from_unnamed_descendants(scene):
	item = _named(scene, 'Outdoor')
	assert 'environment.temperature.temperature' in item['keys']
	assert 'environment.humidity.humidity' in item['keys']


def test_wind_panel_binds_its_whole_value_context(scene):
	item = _named(scene, 'Wind')
	assert 'environment.wind.speed.speed' in item['keys']
	assert 'environment.wind.direction.direction' in item['keys']
	assert 'environment.wind.speed.gust' in item['keys']


def test_duplicate_keys_are_deduplicated():
	assert _dedupe_keys(['a.b', 'a.b', 'a.c']) == ['a.b', 'a.c']


def test_texts_carry_display_strings(scene):
	item = _named(scene, 'Outdoor')
	texts = [t for t in item['texts'] if t.get('text', '').strip()]
	assert texts, 'expected at least one non-empty display string'
	for text in texts:
		assert len(text['rect']) == 4
		assert 'text' in text
	# panel titles may carry no font metadata of their own, but the value
	# displays must - that is what lets the browser match the Qt look. Color
	# is only required when Qt actually has one to report (unstyled brushes
	# come through as NoBrush and are deliberately omitted).
	with_fonts = [t for t in texts if 'font' in t]
	assert with_fonts, 'expected at least one text with font metadata'
	assert all(isinstance(t.get('size', 0), (int, float)) for t in with_fonts)
	assert all(t['color'].startswith('#') for t in with_fonts if 'color' in t)


def test_diff_is_empty_for_identical_snapshots(scene):
	snap = snapshot(scene)
	assert diff(snap, list(snap)) == {}


def test_diff_detects_a_text_change(scene):
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Text import Text

	target = None
	for item in scene.items():
		if isinstance(item, Text) and getattr(item, 'text', '').strip():
			target = item
			break
	assert target is not None
	original = target.text

	before = snapshot(scene)
	target.text = 'changed-for-test'
	changed = diff(before, snapshot(scene))
	target.text = original  # restore; this scene is reused by later tests

	assert changed, 'a text change must produce an update'
	for payload in changed.values():
		if any(t.get('text') == 'changed-for-test' for t in payload['texts']):
			break
	else:
		pytest.fail('changed text not found in any updated payload')


# -- diff() is pure dict math; exercise the value branch without a scene -----

def _payload(name='Outdoor', text='21.5 °C', value=21.5):
	return {
		'name': name,
		'type': 'StackedTitledPanel',
		'z': 0.0,
		'rect': [12.0, 34.0, 500.0, 300.0],
		'parent': None,
		'keys': ['environment.temperature.temperature'],
		'values': {
			'environment.temperature.temperature': {
				'value': value,
				'formatted': text,
				'source': 'OpenMeteo',
				'key': 'environment.temperature.temperature',
			},
		},
		'texts': [{'rect': [20.0, 40.0, 100.0, 20.0], 'text': text, 'font': 'Nunito', 'size': 22.0, 'weight': 400, 'color': '#ffffff'}],
	}


def test_diff_value_change_counts_even_when_texts_match():
	old, new = _payload(), _payload(text='21.5 °C', value=22.1)
	assert diff([old], [new]) == {'Outdoor': new}


def test_diff_geometry_change_counts():
	old = _payload()
	new = _payload()
	new['rect'] = [12.0, 34.0, 520.0, 300.0]
	assert diff([old], [new]) == {'Outdoor': new}


def test_diff_new_item_counts():
	assert diff([], [_payload()]) == {'Outdoor': _payload()}


def test_diff_ignores_reshuffled_value_payloads_that_did_not_change():
	old = _payload()
	new = _payload()
	assert diff([old], [new]) == {}


def test_diff_matches_by_name_not_by_position():
	old = [_payload('Outdoor', value=21.5), _payload('wind', value=3.0)]
	new = [old[1], old[0]]
	assert diff(old, new) == {}


# -- the live-value path: _value_payload against a real MultiSourceContainer --

def _fake_multisource(key_str, measurement=None):
	"""A real MultiSourceContainer (the dispatcher's type) holding one fake
	per-source Container, the shape the live plugins produce."""
	from types import SimpleNamespace

	from LevityDash.lib.plugins.categories import CategoryItem
	from LevityDash.lib.plugins.dispatcher import MultiSourceContainer

	container = MultiSourceContainer(CategoryItem(key_str))
	if measurement is not None:
		container['FakeSource'] = SimpleNamespace(
			value=SimpleNamespace(value=measurement),
			source=SimpleNamespace(name='FakeSource'),
		)
	return container


def test_value_payload_resolves_a_live_multisource_container(monkeypatch):
	from LevityDash import LevityDashboard

	monkeypatch.setattr(
		LevityDashboard.dispatcher,
		'getContainer',
		lambda key: _fake_multisource(str(key), measurement=21.5),
	)
	payload = _value_payload('environment.temperature.temperature')
	assert payload is not None
	assert payload['value'] == 21.5
	assert payload['formatted'] == '21.5'
	assert payload['source'] == 'FakeSource'
	assert payload['key'] == 'environment.temperature.temperature'
	assert payload['flags']['isTimeseries'] is False


def test_value_payload_is_none_for_an_empty_container(monkeypatch):
	from LevityDash import LevityDashboard

	monkeypatch.setattr(LevityDashboard.dispatcher, 'getContainer', lambda key: _fake_multisource('environment.light.sunrise'))
	assert _value_payload('environment.light.sunrise') is None


def test_value_payload_is_none_when_dispatcher_raises(monkeypatch):
	from LevityDash import LevityDashboard

	def boom(_key):
		raise ValueError('No default container found')

	monkeypatch.setattr(LevityDashboard.dispatcher, 'getContainer', boom)
	assert _value_payload('environment.temperature.temperature') is None
