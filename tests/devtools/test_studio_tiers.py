"""The Studio's tier checks: header above label, label no larger than its value, read from the groups the engine built."""
from types import SimpleNamespace as NS

import pytest

pytest.importorskip('PySide6')

import LevityDash  # noqa: F401  builds the QApplication
from LevityDash.devtools import _studio_groups as sg  # noqa: E402
from LevityDash.devtools import _studio_tiers as tiers  # noqa: E402
from PySide6.QtCore import QRectF  # noqa: E402

from LevityDash.devtools import _studio_builder as sb  # noqa: E402
from tests.conftest import pump  # noqa: E402
from tests.devtools.test_studio_builder import StubEngine  # noqa: E402


def member(font, path=None, role='', text='', rect=None):
	return NS(font=font, path=path, role=role, text=text, rect=rect)


def group(key, *members, unresolved=None):
	return NS(key=key, members=list(members), unresolved=unresolved)


def test_group_keys_name_their_role_whatever_the_scope():
	assert [tiers.role(k) for k in ('head', 'title', 'value', 'hero', 'cap', 'stat', 'nonsense')] == ['header', 'label', 'value', 'hero', 'caption', 'value', None]


def test_a_header_at_or_below_its_labels_is_a_warning_and_a_near_one_a_note():
	found = tiers.check([group('head', member(20)), group('title', member(30)), group('value', member(40))])
	assert [f.severity for f in found] == [tiers.WARN] and 'not larger than labels' in found[0].message
	found = tiers.check([group('head', member(32)), group('title', member(30))])
	assert [f.severity for f in found] == [tiers.NOTE]
	assert tiers.check([group('head', member(40)), group('title', member(30)), group('value', member(36))]) == []


def test_a_label_larger_than_its_value_is_a_warning_and_so_is_a_hero_under_a_value():
	found = tiers.check([group('title', member(50)), group('value', member(30)), group('hero', member(30))])
	assert {f.message.split(' (')[0] for f in found} == {'Labels', 'Heroes'} and all(f.severity == tiers.WARN for f in found)


def test_roles_are_compared_across_groups_and_scopes_and_an_unmatched_scope_is_left_out():
	found = tiers.check([group('title', member(30)), group('title', member(32)), group('head', member(33)), group('head', member(5), unresolved='zzz')])
	assert [f.severity for f in found] == [tiers.NOTE]  # the unresolved group's size does not count


def test_a_label_larger_than_the_value_in_the_same_item_names_the_item():
	g = group('size', member(40, (0, 1), 'label', 'Humidity'), member(30, (0, 1), 'value', '31'), member(20, (0, 2), 'label', 'Wind'), member(30, (0, 2), 'value', '7'))
	found = tiers.check([g])
	assert len(found) == 1 and '[0][1]' in found[0].message and 'Humidity' in found[0].message and len(found[0].members) == 2


BOARD = '''
- type: group
  name: panel
  geometry: {x: 0%, y: 0%, width: 100%, height: 100%}
  shared:
    title: {matchingGroup: {group: global.title, matchAll: true}}
    display: {valueLabel: {matchingGroup: {group: global.value, matchAll: true}}}
  items:
    - {type: realtime.text, key: environment.temperature.temperature, name: t, title: {text: Temp}, geometry: {x: 0%, y: 0%, width: 50%, height: 50%}}
    - {type: realtime.text, key: environment.humidity.humidity, name: h, title: {text: Humid}, geometry: {x: 50%, y: 0%, width: 50%, height: 50%}}
'''


def test_the_engines_texts_are_told_apart_as_labels_and_values(dashboard, tmp_path):
	panel = LevityDash.LevityDashboard.CENTRAL_PANEL
	target = tmp_path / 'tiers.levity'
	target.write_text(BOARD)
	was = panel.filePath
	panel._load(target)
	pump(dashboard.app, 1.5)
	try:
		found = sg.collect(dashboard.scene, {'panel': (0,), 't': (0, 0), 'h': (0, 1)})
		by = {g.key: g for g in found}
		assert {m.role for m in by['title'].members} == {'label'}
		assert {m.role for m in by['value'].members} == {'value'}
		tiers.check(found)  # runs on real groups
	finally:
		if was is not None:
			panel._load(was)
			pump(dashboard.app, 1.5)


def test_the_tab_lists_the_findings_and_a_click_outlines_their_text(builder_with_tiers):
	win = builder_with_tiers
	win.groupsTab.load([
		sg.Group('global.title', 'title', True, [sg.Member((0,), 'Temp', 10, 50.0, QRectF(0, 0, 5, 5))]),
		sg.Group('global.value', 'value', True, [sg.Member((0,), '7', 10, 30.0, QRectF(10, 0, 5, 5))]),
	])
	assert win.groupsTab.checks.count() == 1
	win.groupsTab.checks.setCurrentRow(0)
	assert win.stage.marks == [QRectF(0, 0, 5, 5)]
	win.groupsTab.load([])
	assert win.groupsTab.checks.count() == 0


@pytest.fixture
def builder_with_tiers(tmp_path, monkeypatch):
	monkeypatch.setenv('LEVITYDASH_STUDIO_DIR', str(tmp_path))
	win = sb.Builder(engine=StubEngine())
	win.timer.stop()
	yield win
	win.close()
