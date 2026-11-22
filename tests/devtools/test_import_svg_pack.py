"""The SVG folder → glyph map converter."""
import tomllib
from pathlib import Path

from LevityDash.devtools import import_svg_pack


def _svg(body: str, box: str = '0 0 24 24') -> str:
	return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{box}">{body}</svg>'


def test_paths_shapes_and_names_become_a_map(tmp_path):
	source = tmp_path / 'src'
	source.mkdir()
	(source / 'qi-sun.svg').write_text(_svg('<path d="M2 2 L22 2 L22 22 Z" fill="currentColor"/>'))
	(source / 'qi-moon.svg').write_text(_svg('<circle cx="12" cy="12" r="9" fill="currentColor"/>'))
	out = tmp_path / 'out.toml'
	import_svg_pack.main([str(source), str(out), '--prefix', 'x', '--strip', 'qi-'])
	data = tomllib.loads(out.read_text())['x']
	assert data['prefix'] == 'x'
	assert data['default'] == 'line'
	assert data['line']['viewBox'] == '0 0 24 24'
	assert set(data['line']['svg']) == {'sun', 'moon'}, 'the filename prefix is stripped, names lowercased'
	assert data['line']['svg']['sun'].startswith('M2 2')
	assert 'A' in data['line']['svg']['moon'] or data['line']['svg']['moon'].startswith('M3'), 'a circle becomes path data'


def test_a_stroke_only_shape_carries_its_stroke(tmp_path):
	source = tmp_path / 'src'
	source.mkdir()
	(source / 'line.svg').write_text(_svg('<path d="M4 12 H20" fill="none" stroke="currentColor" stroke-width="2"/>'))
	out = tmp_path / 'out.toml'
	import_svg_pack.main([str(source), str(out), '--prefix', 'y'])
	value = tomllib.loads(out.read_text())['y']['line']['svg']['line']
	assert isinstance(value, list), 'a non-uniform glyph is a part list'
	assert value[0]['stroke'] == 2


def test_a_white_shape_becomes_a_cutout_and_a_transform_is_kept(tmp_path):
	source = tmp_path / 'src'
	source.mkdir()
	(source / 'knock.svg').write_text(_svg(
		'<g fill="currentColor"><rect x="2" y="2" width="20" height="20"/>'
		'<circle cx="12" cy="12" r="4" fill="white"/></g>'
		'<path d="M2 2 h4" transform="translate(6 6)"/>'
	))
	out = tmp_path / 'out.toml'
	import_svg_pack.main([str(source), str(out), '--prefix', 'z'])
	parts = tomllib.loads(out.read_text())['z']['line']['svg']['knock']
	roles = [part.get('role') for part in parts if isinstance(part, dict)]
	assert 'cutout' in roles
	transforms = [part.get('transform') for part in parts if isinstance(part, dict)]
	assert 'translate(6 6)' in transforms


def test_a_set_with_two_viewboxes_is_refused(tmp_path):
	source = tmp_path / 'src'
	source.mkdir()
	(source / 'a.svg').write_text(_svg('<path d="M0 0 L4 4" fill="currentColor"/>', '0 0 24 24'))
	(source / 'b.svg').write_text(_svg('<path d="M0 0 L4 4" fill="currentColor"/>', '0 0 16 16'))
	out = tmp_path / 'out.toml'
	try:
		import_svg_pack.main([str(source), str(out), '--prefix', 'q'])
	except SystemExit as error:
		assert 'viewBox' in str(error)
	else:
		raise AssertionError('a mixed-size set must be refused, not silently drawn wrong')


def test_coordinates_are_rounded(tmp_path):
	source = tmp_path / 'src'
	source.mkdir()
	(source / 'p.svg').write_text(_svg('<path d="M10.123456 4.987654 L20.111111 4.222222" fill="currentColor"/>'))
	out = tmp_path / 'out.toml'
	import_svg_pack.main([str(source), str(out), '--prefix', 'r', '--precision', '2'])
	value = tomllib.loads(out.read_text())['r']['line']['svg']['p']
	assert '10.12' in value and '4.99' in value, value
	assert '10.123456' not in value
