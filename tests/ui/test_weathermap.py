"""The weather map: tile geometry, palettes, parsing the two services' answers, and the item loading and painting."""
import json
import math
import time

import numpy as np
import pytest

from LevityDash.lib.ui.frontends.PySide.Modules.Displays.weathermap import data, field, geo, palette


# -- geometry ------------------------------------------------------------------------------------------------------

def test_world_and_lonlat_are_inverses():
	for lat, lon, z in ((40.7, -74.0, 5), (-33.9, 151.2, 3.5), (0.0, 0.0, 1), (66.5, 25.0, 7)):
		x, y = geo.toWorld(lat, lon, z)
		back = geo.toLonLat(x, y, z)
		assert back == pytest.approx((lat, lon), abs=1e-9)


def test_zoom_zero_is_one_tile_with_greenwich_in_the_middle():
	assert geo.toWorld(0, 0, 0) == pytest.approx((0.5, 0.5))
	assert geo.toWorld(0, -180, 0)[0] == pytest.approx(0.0)


def test_the_centre_projects_to_the_middle_and_north_is_up():
	vp = geo.Viewport(40.0, -88.0, 5, 800, 600)
	assert vp.project(40.0, -88.0) == pytest.approx((400, 300))
	assert vp.project(45.0, -88.0)[1] < 300
	assert vp.project(40.0, -80.0)[0] > 400
	assert vp.unproject(400, 300) == pytest.approx((40.0, -88.0))


def test_tiles_cover_the_viewport_with_no_gaps():
	for zoom in (3, 4.4, 5, 6.6):
		vp = geo.Viewport(40.0, -88.0, zoom, 900, 500)
		spots = vp.tiles()
		assert min(s.left for s in spots) <= 0 and max(s.left + s.size for s in spots) >= 900
		assert min(s.top for s in spots) <= 0 and max(s.top + s.size for s in spots) >= 500
		assert len({s.key for s in spots}) == len(spots)


def test_tile_zoom_is_capped_and_the_tile_stretches():
	vp = geo.Viewport(40.0, -88.0, 10, 512, 512)
	spots = vp.tiles(limit=7)
	assert {s.z for s in spots} == {7}
	assert all(s.size == pytest.approx(256*8) for s in spots)


def test_tiles_wrap_across_the_date_line():
	vp = geo.Viewport(0.0, 179.0, 3, 800, 400)
	assert all(0 <= s.x < 8 for s in vp.tiles())
	assert {0, 7} <= {s.x for s in vp.tiles()}


def test_a_grid_is_even_in_pixels_so_a_field_lands_with_a_plain_stretch():
	vp = geo.Viewport(40.0, -88.0, 5, 800, 600)
	grid = vp.grid(5, 4)
	assert len(grid) == 4 and len(grid[0]) == 5
	for r, row in enumerate(grid):
		for c, (lat, lon) in enumerate(row):
			assert vp.project(lat, lon) == pytest.approx((800*c/4, 600*r/3), abs=1e-6)


# -- palette -------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize('name', sorted(palette.RAMPS))
def test_ramps_are_inside_the_gamut_and_start_clear(name):
	table = palette.lut(palette.RAMPS[name])
	assert table.shape == (256, 4) and table.dtype == np.uint8
	assert table[0, 3] == 0
	assert table[-1, 3] > 150


def test_the_precipitation_ramp_gets_more_opaque_with_intensity():
	alpha = palette.lut(palette.PRECIP)[:, 3].astype(int)
	assert (np.diff(alpha[:200]) >= 0).all()


def test_the_precipitation_ramp_runs_from_cyan_through_violet_to_a_warm_core():
	light, mid, heavy, top = (palette.ramp(palette.PRECIP, t) for t in (0.16, 0.52, 0.7, 1.0))
	assert light[2] > light[0]  # blue or cyan
	assert mid[2] > mid[1]  # blue-violet
	assert heavy[0] > heavy[1]  # magenta: red over green
	assert top[0] > top[2]  # warm


@pytest.mark.parametrize('scheme', list(palette.SCHEMES))
def test_every_scheme_gets_more_opaque_with_intensity(scheme):
	alpha = palette.lut(palette.precipRamp(scheme))[:, 3].astype(int)
	assert alpha[0] == 0 and alpha[-1] > 200
	assert (np.diff(alpha) >= 0).all()


def test_dark_sky_rain_is_blue_and_its_storms_are_warm():
	stops = palette.precipRamp('darksky')
	light, moderate, heavy = (palette.ramp(stops, t) for t in (0.16, 0.45, 0.9))
	assert light[2] > light[0] and light[2] > light[1]
	assert moderate[2] > moderate[0] and moderate[2] > moderate[1]
	assert heavy[0] > heavy[2] and heavy[0] > heavy[1]


def test_the_schemes_differ_and_an_unknown_one_falls_back_to_dark_sky():
	light = {name: palette.swatch(palette.precipRamp(name), 5)[1] for name in palette.SCHEMES}
	assert len(set(light.values())) == len(light)
	assert palette.precipRamp('nope') == palette.precipRamp('darksky')


def test_hue_turns_the_short_way():
	assert palette._mix_hue(350, 10, 0.5) == pytest.approx(0)
	assert palette._mix_hue(10, 350, 0.5) == pytest.approx(0)
	assert palette._mix_hue(100, 200, 0.5) == pytest.approx(150)


def test_colorize_makes_nan_clear_and_scales_opacity():
	table = palette.lut(palette.CLOUDS)
	out = palette.colorize(np.array([[np.nan, 100.0]]), table, 0, 100)
	assert out[0, 0, 3] == 0 and out[0, 1, 3] == table[-1, 3]
	half = palette.colorize(np.array([[100.0]]), table, 0, 100, opacity=0.5)
	assert half[0, 0, 3] == pytest.approx(table[-1, 3]*0.5, abs=1)


def test_temperature_ramp_slides_with_the_comfort_range():
	stops, lo, hi = palette.temperatureRamp(12, 22)
	assert (lo, hi) == (-30, 52)
	narrow, nlo, nhi = palette.temperatureRamp(18, 24)
	assert nlo > lo  # the cold end moved up with the low edge
	# 20 °C is inside the default band and above the narrow one: a different colour on each
	a = palette.ramp(stops, (20 - lo)/(hi - lo))
	b = palette.ramp(narrow, (20 - nlo)/(nhi - nlo))
	assert a != b


def test_temperature_runs_cold_blue_to_hot_red():
	stops, lo, hi = palette.temperatureRamp(12, 22)
	cold, hot = palette.ramp(stops, (-10 - lo)/(hi - lo)), palette.ramp(stops, (40 - lo)/(hi - lo))
	assert cold[2] > cold[0] and hot[0] > hot[2]


def test_the_rainviewer_scale_orders_its_colours_weakest_first():
	assert len(palette._RAINVIEWER) == 72
	faint = np.array([[[99, 97, 89, 20]]], dtype=np.uint8)
	blue = np.array([[[0, 154, 213, 255]]], dtype=np.uint8)
	warm = np.array([[[255, 149, 0, 255]]], dtype=np.uint8)
	pink = np.array([[[255, 129, 255, 255]]], dtype=np.uint8)
	clear = np.array([[[0, 0, 0, 0]]], dtype=np.uint8)
	values = [float(palette.rainviewerIntensity(px)[0, 0]) for px in (clear, faint, blue, warm, pink)]
	assert values[0] == 0 and values == sorted(values) and values[-1] <= 1.0


def test_a_resampled_colour_goes_to_its_nearest():
	near = np.array([[[2, 152, 210, 250]]], dtype=np.uint8)  # one step off a real blue
	exact = np.array([[[0, 154, 213, 255]]], dtype=np.uint8)
	assert palette.rainviewerIntensity(near)[0, 0] == palette.rainviewerIntensity(exact)[0, 0]


# -- smoothing -----------------------------------------------------------------------------------------------------

def test_upsample_passes_through_the_grid_and_never_overshoots():
	grid = np.array([[0.0, 10.0, 0.0], [0.0, 40.0, 0.0], [0.0, 10.0, 0.0]])
	out = field.upsample(grid, 25, 25)
	assert out.shape == (25, 25)
	assert out[12, 12] == pytest.approx(40.0)
	assert out[0, 0] == pytest.approx(0.0) and out[-1, -1] == pytest.approx(0.0)
	assert out.min() >= 0.0 and out.max() <= 40.0


def test_a_missing_point_does_not_blank_the_map():
	grid = np.array([[1.0, np.nan], [3.0, 5.0]])
	assert np.isfinite(field.upsample(grid, 8, 8)).all()


def test_degree_differences_fold():
	assert field.wrapDegrees(350 - 10) == pytest.approx(-20)
	assert field.wrapDegrees(10 - 350) == pytest.approx(20)


# -- the services ---------------------------------------------------------------------------------------------------

INDEX = json.dumps({
	'version': '2.0', 'generated': 1, 'host': 'https://tilecache.example',
	'radar': {'past': [{'time': 200, 'path': '/v2/radar/b'}, {'time': 100, 'path': '/v2/radar/a'}],
		'nowcast': [{'time': 300, 'path': '/v2/radar/n'}]},
})


def test_radar_index_is_oldest_first_with_the_nowcast_marked():
	frames = data.parseRadarIndex(INDEX)
	assert [f.time for f in frames] == [100, 200, 300]
	assert [f.forecast for f in frames] == [False, False, True]
	assert data.radarUrl(frames[0], 5, 9, 12) == 'https://tilecache.example/v2/radar/a/256/5/9/12/2/1_0.png'


def test_an_index_with_no_frames_is_an_empty_list():
	assert data.parseRadarIndex(json.dumps({'host': 'h', 'radar': {'past': []}})) == []


def test_basemap_urls_name_the_tile():
	url = data.basemapUrl(data.BASEMAPS['dark'], 6, 17, 25)
	assert url.endswith('/tile/6/25/17') and 'Dark_Gray' in url  # y before x, as Esri has it


def _point(t, w, d, c):
	return {'current': {'time': 1000, 'temperature_2m': t, 'wind_speed_10m': w, 'wind_direction_10m': d, 'cloud_cover': c}}


def test_field_answers_become_row_major_grids():
	body = json.dumps([_point(i, i*2, i*3, i*4) for i in range(6)])
	grid = data.parseFields(body, 2, 3)
	assert grid.values['temperature'].shape == (2, 3)
	assert grid.values['temperature'][1, 0] == 3 and grid.values['wind'][0, 2] == 4
	assert grid.time == 1000


def test_one_point_comes_back_as_a_bare_object():
	grid = data.parseFields(json.dumps(_point(1, 2, 3, 4)), 1, 1)
	assert grid.values['clouds'][0, 0] == 4


def test_a_refused_request_says_why():
	with pytest.raises(ValueError, match='limit'):
		data.parseFields(json.dumps({'error': True, 'reason': 'Daily API request limit exceeded.'}), 1, 1)


def test_a_wrong_number_of_points_is_an_error():
	with pytest.raises(ValueError, match='points'):
		data.parseFields(json.dumps([_point(1, 1, 1, 1)]), 2, 2)


def test_a_missing_value_is_nan():
	body = json.dumps([{'current': {'time': 5, 'temperature_2m': None}}])
	assert math.isnan(data.parseFields(body, 1, 1).values['temperature'][0, 0])


def test_the_field_url_lists_every_point_once_in_row_major_order():
	vp = geo.Viewport(40.0, -88.0, 5, 800, 600)
	url = data.fieldUrl(vp.grid(3, 2))
	lats = url.split('latitude=')[1].split('&')[0].split(',')
	assert len(lats) == 6 and 'current=temperature_2m' in url and 'wind_speed_unit=ms' in url


def test_fetch_keeps_a_copy_on_disk(tmp_path):
	source = tmp_path / 'tile.bin'
	source.write_bytes(b'one')
	cache = tmp_path / 'cache'
	url = source.as_uri()
	assert data.fetch(url, ttl=60, directory=cache) == b'one'
	source.write_bytes(b'two')
	assert data.fetch(url, ttl=60, directory=cache) == b'one'  # still fresh: not asked again
	assert data.fetch(url, ttl=0, directory=cache) == b'two'


# -- the item ------------------------------------------------------------------------------------------------------

def _png(color=(0, 154, 213, 255), size=64):
	from PySide6.QtCore import QBuffer, QByteArray, QIODevice
	from PySide6.QtGui import QColor, QImage
	image = QImage(size, size, QImage.Format.Format_RGBA8888)
	image.fill(QColor(*color))
	raw = QByteArray()
	buffer = QBuffer(raw)
	buffer.open(QIODevice.OpenModeFlag.WriteOnly)
	image.save(buffer, 'PNG')
	return bytes(raw)


@pytest.fixture
def offline(monkeypatch):
	"""Every tile is a flat colour, the radar has three frames and the fields are a ramp: nothing leaves the machine."""
	asked = []

	def fetch(url, ttl=0.0, directory=None, timeout=0):
		asked.append(url)
		if 'cartocdn' in url or 'arcgisonline' in url:
			return _png((60, 60, 60, 255)) if 'Reference' not in url else _png((255, 255, 255, 0))
		return _png()

	monkeypatch.setattr(data, 'fetch', fetch)
	monkeypatch.setattr(data, 'radarFrames', lambda: [data.Frame(t, f'/v2/radar/{t}', 'https://tilecache.example') for t in (100, 200, 300)])

	def fields(points, ttl=0.0):
		rows, cols = len(points), len(points[0])
		temp = np.linspace(0, 30, rows*cols).reshape(rows, cols)
		return data.FieldGrid({'temperature': temp, 'wind': temp/2, 'direction': np.full((rows, cols), 270.0), 'clouds': temp*3}, 1000)

	monkeypatch.setattr(data, 'fetchFields', fields)
	return asked


def _map(dashboard, **settings):
	from LevityDash.lib.ui.frontends.PySide.Modules import Panel
	sandbox = Panel(parent=dashboard.scene.base, geometry={'x': '0%', 'y': '0%', 'width': '50%', 'height': '40%'})
	sandbox.state = {'items': [{
		'type': 'map', 'name': 'm', 'lat': 40.0, 'lon': -88.0, 'zoom': 5, 'marker': False,
		'geometry': {'x': '0%', 'y': '0%', 'width': '100%', 'height': '100%'}, **settings,
	}]}
	dashboard.app.processEvents()
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.weathermap.item import WeatherMap
	return sandbox, next(c for c in sandbox.childPanels if isinstance(c, WeatherMap))


def _grab(item):
	from PySide6.QtGui import QImage, QPainter
	rect = item.rect()
	image = QImage(int(rect.width()), int(rect.height()), QImage.Format.Format_ARGB32)
	image.fill(0)
	painter = QPainter(image)
	item.paint(painter, None)
	painter.end()
	return image


def _wait(dashboard, condition, timeout=5.0):
	dashboard.wait_until(condition, timeout=timeout)


def test_the_type_loads_as_a_map(dashboard, offline):
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.weathermap.item import WeatherMap
	sandbox, item = _map(dashboard, layer='radar')
	try:
		assert isinstance(item, WeatherMap) and item.layer == 'radar' and item.zoom == 5
	finally:
		sandbox.delete()


def test_radar_arrives_and_paints_in_our_palette(dashboard, offline):
	sandbox, item = _map(dashboard, layer='radar', animate=False, legend=False, stamp=False)
	try:
		_wait(dashboard, lambda: any(k[0] == 'radar' for k in item._radar) and item._base)
		_wait(dashboard, lambda: item._currentFrame(item._viewport()) is not None)
		image = _grab(item)
		pixel = image.pixelColor(image.width()//2, image.height()//2)
		# the service's blue (0,154,213) is drawn with the ramp's, which is not the same blue
		assert (pixel.red(), pixel.green(), pixel.blue()) != (0, 154, 213) and pixel.alpha() > 0
		assert item._currentFrame(item._viewport()).time == 300  # not animating: the newest picture
	finally:
		sandbox.delete()


def test_a_scheme_change_repaints_the_radar(dashboard, offline):
	sandbox, item = _map(dashboard, layer='radar', animate=False, legend=False, stamp=False, labels=False)
	try:
		_wait(dashboard, lambda: item._currentFrame(item._viewport()) is not None)
		before = _grab(item)
		item.scheme = 'apple'
		after = _grab(item)
		x, y = before.width()//2, before.height()//2
		assert before.pixelColor(x, y) != after.pixelColor(x, y)
		assert item.scheme == 'apple'
	finally:
		sandbox.delete()


def test_borders_set_how_far_lines_are_lifted(dashboard, offline):
	sandbox, item = _map(dashboard, layer='none', borders=0)
	try:
		assert item.borders == 0
		item.borders = 2.5
		assert item.borders == 2.5
	finally:
		sandbox.delete()


def test_place_names_are_drawn(dashboard, offline):
	sandbox, item = _map(dashboard, layer='none')
	try:
		base = item._baseStyle()
		labels = data.BASEMAPS[base.name + '-labels']
		spot = item._viewport().tiles(labels.max_zoom)[0]
		_wait(dashboard, lambda: ('labels', labels.name, *spot.key) in item._base)
		assert item._labelImage(labels, spot) is not None
	finally:
		sandbox.delete()


def test_the_loop_steps_through_pictures_that_are_complete(dashboard, offline):
	sandbox, item = _map(dashboard, layer='radar', speed=50)
	try:
		_wait(dashboard, lambda: len(item._frames) == 3)
		_wait(dashboard, lambda: all(item._complete(f, item._viewport().tiles(7)) for f in item._frames))
		seen = set()
		_wait(dashboard, lambda: seen.add(item._shown) or len(seen) == 3, timeout=6)
	finally:
		sandbox.delete()


def test_click_pauses_the_loop(dashboard, offline):
	sandbox, item = _map(dashboard, layer='radar', speed=50)
	try:
		_wait(dashboard, lambda: len(item._frames) == 3)
		item._paused = True
		item._schedule()
		assert not item._stepper.isActive()
		item._paused = False
		item._schedule()
		assert item._stepper.isActive()
	finally:
		sandbox.delete()


@pytest.mark.parametrize('layer', ['temperature', 'wind', 'clouds'])
def test_field_layers_paint_from_the_grid(dashboard, offline, layer):
	sandbox, item = _map(dashboard, layer=layer, legend=False, stamp=False, basemap='none')
	try:
		_wait(dashboard, lambda: item._fieldGrid is not None)
		image = _grab(item)
		colors = {image.pixel(x, y) for x in range(0, image.width(), 20) for y in range(0, image.height(), 20)}
		assert len(colors) > 3  # a gradient, not a flat fill
	finally:
		sandbox.delete()


def test_a_service_that_fails_leaves_the_map_drawing_and_is_asked_again_later(dashboard, monkeypatch, offline):
	def broken(points, ttl=0.0):
		raise OSError('no route')

	monkeypatch.setattr(data, 'fetchFields', broken)
	sandbox, item = _map(dashboard, layer='temperature')
	try:
		_wait(dashboard, lambda: ('fields',) in item._failed)
		_grab(item)  # must not raise
		assert item._fieldGrid is None
		assert not item._due(('fields',))  # held off for a minute, not hammered
	finally:
		sandbox.delete()


def test_the_base_map_follows_the_theme_and_none_draws_no_tiles(dashboard, offline):
	sandbox, item = _map(dashboard, layer='none', basemap='none')
	try:
		assert item._baseStyle() is None
		item.basemap = 'light'
		assert item._baseStyle().name == 'light'
		item.basemap = 'dark'
		assert item._baseStyle().name == 'dark'
	finally:
		sandbox.delete()


@pytest.mark.parametrize('bad', [{'zoom': 40}, {'lat': 95}, {'range': [5, 5]}, {'borders': 5}])
def test_bad_numbers_are_refused_with_a_reason(dashboard, offline, bad):
	sandbox, item = _map(dashboard)
	try:
		name, value = next(iter(bad.items()))
		before = getattr(item, name)
		with pytest.raises(ValueError):
			setattr(item, name, value)
		assert getattr(item, name) == before
	finally:
		sandbox.delete()


@pytest.mark.parametrize('bad', [{'layer': 'snow'}, {'basemap': 'sepia'}, {'scheme': 'rainbow'}, {'tiles': 'ftp://x/{z}/{x}/{y}'}, {'tiles': 'https://x/{z}'}])
def test_a_bad_word_in_a_dashboard_makes_an_error_tile_not_a_map(dashboard, offline, bad):
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.weathermap.item import WeatherMap
	sandbox = None
	try:
		with pytest.raises(StopIteration):
			sandbox, _ = _map(dashboard, **bad)
	finally:
		for panel in dashboard.scene.base.childItems():
			if isinstance(panel, WeatherMap):
				panel.delete()


# -- MET Norway fallback -------------------------------------------------------------------------------------------

MET = json.dumps({'properties': {'timeseries': [{'time': '2026-11-28T13:00:00Z', 'data': {'instant': {'details': {
	'air_temperature': 6.5, 'wind_speed': 5.9, 'wind_from_direction': 247.7, 'cloud_area_fraction': 88.3}}}}]}})


def test_a_met_norway_point_has_the_same_four_fields():
	values, when = data.parseMet(MET)
	assert values == {'temperature': 6.5, 'wind': 5.9, 'direction': 247.7, 'clouds': 88.3}
	assert when == 1795870800


def test_the_grid_falls_back_to_met_norway_when_open_meteo_refuses(monkeypatch):
	def fetch(url, ttl=0.0, directory=None, timeout=0):
		if 'open-meteo' in url:
			return json.dumps({'error': True, 'reason': 'Daily API request limit exceeded.'})
		return MET

	monkeypatch.setattr(data, 'fetch', fetch)
	grid = data.fetchFields(geo.Viewport(40.0, -88.0, 5, 800, 600).grid(3, 2))
	assert grid.source == 'MET Norway' and grid.values['temperature'].shape == (2, 3)
	assert (grid.values['temperature'] == 6.5).all()
