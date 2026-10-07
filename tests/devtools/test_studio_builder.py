"""The Studio builder's window, driven without a dashboard behind it: tree, bindings, instance diff, save and open."""
import pytest

pytest.importorskip('PySide6')

import LevityDash  # noqa: F401  builds the QApplication
import yaml  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402

from LevityDash.devtools import _studio_builder as sb  # noqa: E402
from LevityDash.devtools import _studio_preset as m  # noqa: E402
from LevityDash.devtools import _studio_state as state  # noqa: E402


class StubEngine:
	"""Stands in for the booted dashboard: reports the layout it was asked for as one rectangle per item."""
	size = (640, 400)

	def __init__(self):
		self.drawn = []

	def resize(self, size):
		self.size = size

	def render(self, items, names):
		self.drawn.append(items)
		image = QImage(640, 400, QImage.Format.Format_ARGB32)
		image.fill(0)
		from PySide6.QtCore import QRectF
		return image, {path: QRectF(10, 10, 100, 50) for path in names.values()}


@pytest.fixture
def builder(tmp_path, monkeypatch):
	monkeypatch.setenv('LEVITYDASH_STUDIO_DIR', str(tmp_path))
	win = sb.Builder(engine=StubEngine())
	win.timer.stop()
	yield win
	win.close()


def test_new_items_go_into_the_selected_container(builder):
	builder.addItem('stack')
	builder.addItem('realtime.text')
	assert builder.selection == (0, 0)
	builder.select(())
	builder.addItem('realtime.bar')
	kinds = [(n['type'], [k['type'] for k in n.get('items', [])]) for n in builder.piece.template['items']]
	assert kinds == [('stack', ['realtime.text']), ('realtime.bar', [])]
	assert 'geometry' not in builder.piece.node((0, 0)), 'a child of a stack is placed by the stack'
	assert 'geometry' in builder.piece.node((1,))
	assert builder.tree.topLevelItemCount() == 1


def test_a_bar_is_born_with_a_fill(builder):
	builder.addItem('realtime.bar')
	assert builder.piece.node((0,))['display']['fill']


def test_bind_new_property_and_unbind(builder, monkeypatch):
	builder.addItem('realtime.gauge')
	monkeypatch.setattr(sb.QInputDialog, 'getText', staticmethod(lambda *a, **k: ('hi', True)))
	builder.editField('display.range.max', 120)
	builder.newPropFrom('display.range.max', 'number')
	node = builder.piece.node((0,))
	assert node['display']['range']['max'] == '$hi'
	assert builder.piece.props['hi'].default == 120
	assert builder.itemTab.rows['display.range.max'].chip.text() == '$hi'
	assert builder.piece.expanded({'hi': 80})['items'][0]['display']['range']['max'] == 80
	builder.unbind('display.range.max')
	assert builder.piece.node((0,))['display']['range']['max'] == 120, 'unbinding keeps what the field showed'
	assert 'hi' in builder.piece.props


def test_instance_shows_only_the_difference(builder, monkeypatch):
	builder.addItem('text')
	monkeypatch.setattr(sb.QInputDialog, 'getText', staticmethod(lambda *a, **k: ('title', True)))
	builder.newPropFrom('text', 'text')
	assert builder.instanceTab.out.toPlainText().strip() == '- preset: new-preset'
	builder.setGiven('title', 'Humidity')
	assert 'title: Humidity' in builder.instanceTab.out.toPlainText()
	builder.setGiven('title', 'Label')
	assert 'props' not in builder.instanceTab.out.toPlainText(), 'the default is not stored'
	builder.setGiven('title', 'Humidity')
	builder.redraw()
	assert builder.engine.drawn[-1][0]['items'][0]['items'][0]['text'] == 'Humidity'


def test_the_preview_names_every_item_and_wraps_the_piece_in_a_stage(builder):
	builder.addItem('text')
	builder.redraw()
	[stage] = builder.engine.drawn[-1]
	root = stage['items'][0]
	assert stage['name'] == '_stage' and root['name'] == '_n' and root['items'][0]['name'] == '_n0'
	assert set(builder.stage.rects) == {(), (0,)}


def test_undo_and_redo_restore_the_template_and_the_properties(builder):
	builder.addItem('clock')
	builder.addProp('number')
	assert builder.piece.props and builder.piece.template['items']
	builder.undo()
	assert not builder.piece.props
	builder.undo()
	assert not builder.piece.template['items']
	builder.redo()
	builder.redo()
	assert builder.piece.props and builder.piece.template['items']


def test_dragging_on_the_stage_writes_geometry_in_percent_of_the_parent(builder):
	builder.addItem('realtime.text')
	builder.redraw()
	builder.stage.rects[()] = builder.stage.rects[()].__class__(0, 0, 640, 400)
	builder._dragged((0,), {'x': '25.0%', 'y': '10.0%'})
	node = builder.piece.node((0,))
	assert node['geometry']['x'] == '25.0%' and node['geometry']['width'] == '44%', 'a move leaves the size alone'


def test_save_and_open_round_trip(builder, tmp_path):
	builder.addItem('realtime.gauge')
	builder.addProp('size')
	builder.name.setText('my-dial')
	builder.name.editingFinished.emit()
	builder.save()
	path = state.stateDir() / 'presets' / 'my-dial.yaml'
	data = yaml.safe_load(path.read_text())
	assert set(data) == {'props', 'template'}
	other = sb.Builder(engine=StubEngine())
	other.timer.stop()
	other.openFile(path)
	assert other.piece.name == 'my-dial' and other.piece.asData() == data
	other.close()


def test_a_plain_item_file_opens_as_a_preset_without_properties(builder, tmp_path):
	fragment = tmp_path / 'frag.levity'
	fragment.write_text(yaml.safe_dump([{'type': 'realtime.gauge', 'key': 'environment.humidity.humidity'}]))
	builder.openFile(fragment)
	assert builder.piece.template['key'] == 'environment.humidity.humidity' and not builder.piece.props


def test_the_more_properties_popover_keeps_the_fields_the_item_tab_owns(builder):
	builder.addItem('realtime.gauge')
	builder.editField('display.range.min', 5)
	builder.editField('*', {'display': {'zones': [{'to': 10, 'color': '#f00'}]}, 'title': False})
	node = builder.piece.node((0,))
	assert node['display']['range']['min'] == 5 and node['display']['zones'] and node['title'] is False
	assert sb.restOf(node) == {'display': {'zones': [{'to': 10, 'color': '#f00'}]}, 'title': False}


def test_a_shipped_preset_opens_and_its_instance_stores_only_the_difference(builder):
	builder.openNamed('hero-readings')
	assert builder.piece.name == 'hero-readings' and 'title' in builder.piece.props and builder.path is None
	builder.setGiven('title', 'Indoor')
	assert builder.instanceTab.out.toPlainText().strip() == '- preset: hero-readings\n  props:\n    title: Indoor'
	builder.redraw()
	assert builder.engine.drawn[-1][0]['items'][0]['title']['text'] == 'Indoor', 'the preview draws the library\'s expansion'


def test_a_preset_can_be_added_as_an_item_and_is_expanded_in_the_preview(builder):
	builder.addItem('preset:readout-bar')
	assert builder.piece.node((0,))['preset'] == 'readout-bar'
	assert builder.tree.topLevelItem(0).child(0).text(0) == 'preset: readout-bar'
	builder.redraw()
	inner = builder.engine.drawn[-1][0]['items'][0]['items'][0]
	assert inner['type'] == 'realtime.bar' and 'preset' not in inner


def test_a_use_the_library_refuses_shows_its_reason(builder):
	builder.openNamed('readout-bar')
	builder.given['max'] = 'lots'
	builder.redraw()
	assert 'max' in builder.status.text()
