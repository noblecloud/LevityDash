"""The Studio builder edits `flex:` and `grid:` on stacks, grids and their items."""
import pytest

pytest.importorskip('PySide6')

import LevityDash  # noqa: F401  builds the QApplication
from LevityDash.devtools import _studio_builder as sb  # noqa: E402
from LevityDash.devtools import _studio_layout as layout  # noqa: E402
from tests.devtools.test_studio_builder import StubEngine  # noqa: E402


@pytest.fixture
def builder(tmp_path, monkeypatch):
	monkeypatch.setenv('LEVITYDASH_STUDIO_DIR', str(tmp_path))
	win = sb.Builder(engine=StubEngine())
	win.timer.stop()
	yield win
	win.close()


def row(builder, field):
	return builder.itemTab.rows[field]


def test_a_stack_edits_its_flex_container_keys(builder):
	builder.addItem('stack')
	edit = row(builder, 'flex').editor
	assert (edit.form.parts['justify'].isVisibleTo(edit.form), edit.form.parts['grow'].isVisibleTo(edit.form)) == (True, False)
	edit.form.parts['justify'].setValue('space-between')
	edit.form._emit()
	assert builder.piece.node((0,))['flex'] == {'justify': 'space-between'}


def test_an_item_in_a_stack_edits_its_flex_item_keys(builder):
	builder.addItem('stack')
	builder.addItem('realtime.text')
	form = row(builder, 'flex').editor.form
	assert form.parts['grow'].isVisibleTo(form) and not form.parts['justify'].isVisibleTo(form)
	form.parts['grow'].setValue(2)
	form.parts['basis'].setValue('auto')
	form._emit()
	assert builder.piece.node((0, 0))['flex'] == {'grow': 2, 'basis': 'auto'}


def test_clearing_every_part_removes_the_key(builder):
	builder.addItem('stack')
	form = row(builder, 'flex').editor.form
	form.parts['wrap'].setValue('wrap')
	form._emit()
	assert 'flex' in builder.piece.node((0,))
	form.parts['wrap'].setValue(None)
	form._emit()
	assert 'flex' not in builder.piece.node((0,))


def test_default_choices_are_not_written(builder):
	builder.addItem('stack')
	form = row(builder, 'flex').editor.form
	form.parts['align-items'].setValue('stretch')
	form.parts['wrap'].setValue('nowrap')
	assert form.value() == {}


def test_a_grid_edits_tracks_and_its_cells_edit_placement(builder):
	builder.addItem('grid')
	form = row(builder, 'grid').editor.form
	form.parts['columns'].setValue(['2fr', '1fr'])
	form.parts['gap'].setValue('8px')
	form.parts['justify-items'].setValue('center')
	form._emit()
	assert builder.piece.node((0,))['grid'] == {'columns': ['2fr', '1fr'], 'gap': '8px', 'justify-items': 'center'}
	builder.addItem('realtime.text')
	assert 'geometry' not in builder.piece.node((0, 0))
	cell = row(builder, 'grid').editor.form
	assert cell.parts['column-span'].isVisibleTo(cell) and not cell.parts['columns'].isVisibleTo(cell)
	cell.parts['column'].setValue(2)
	cell.parts['column-span'].setValue(2)
	cell._emit()
	assert builder.piece.node((0, 0))['grid'] == {'column': 2, 'column-span': 2}


def test_unknown_keys_survive_an_edit(builder):
	builder.addItem('stack')
	builder.piece.node((0,))['flex'] = {'justify': 'center', 'future': 1}
	builder.select((0,))
	edit = row(builder, 'flex').editor
	form = edit.form
	form.setValue(edit.value())  # what opening the popover does
	form.parts['wrap'].setValue('wrap')
	assert form.value() == {'justify': 'center', 'future': 1, 'wrap': 'wrap'}

