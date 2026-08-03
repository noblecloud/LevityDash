"""Tests for the dev-only warm render service (devtools/render_service.py).

Never boots a real dashboard - that costs ~6s of Qt startup, which is the very
thing the service exists to avoid paying repeatedly. The HTTP surface is
exercised against a stand-in renderer via aiohttp's TestClient, the same way
tests/devtools/test_backend_watch.py drives _make_status_app.

What this pins is the routing/argument contract. The Qt half (that
scene.render() runs on the Qt thread, and that its output matches
render_dashboard.py) is verified by running the service, not from here.
"""
import asyncio

from aiohttp.test_utils import TestClient, TestServer

from LevityDash.devtools.render_service import (
	RenderError, _makeApp, _parseSize, _pathSegments,
)

PNG = b'\x89PNG\r\n\x1a\n-fake-'


class FakeRenderer:
	"""Stands in for QtRenderer: `call` runs the callable inline instead of
	marshaling it onto the Qt thread."""

	uptime = 12.5
	size = (1800, 1015)

	def __init__(self):
		self.renders = 0
		self.reloads = 0
		self.lastFull = None
		self.lastItem = None

	async def call(self, fn):
		return fn()

	def renderFull(self, size, scale):
		self.lastFull = (size, scale)
		self.renders += 1
		return PNG

	def renderItem(self, name, scale, pad):
		if name != 'terrarium':
			raise RenderError(f'no item named {name!r}')
		self.lastItem = (name, scale, pad)
		self.renders += 1
		return PNG

	def listItems(self):
		return [{'name': 'terrarium', 'type': 'Panel', 'width': 289, 'height': 382}]

	def tree(self, depth=4):
		return {'type': 'CentralPanel', 'rect': [0, 0, 1800, 1015], 'depth': depth}

	def renderAt(self, segments, scale, pad):
		if segments == ['9']:
			raise RenderError('index 9 out of range at <root>: 2 child item(s)')
		self.lastAt = (segments, scale, pad)
		self.renders += 1
		return PNG

	def loadFile(self, path):
		if 'nope' in path:
			raise RenderError(f'no such dashboard: {path}')
		self.loaded = path
		return f'/saves/dashboards/{path}'

	settle = 0.0   # tests must not actually wait out a settle

	def previewLoad(self, source):
		self.previewed = source
		return '/saves/dashboards/_preview.levity'

	def dashboardPath(self):
		return 'default.levity'

	def reload(self):
		self.reloads += 1


def _run(scenario):
	return asyncio.run(scenario())


def _client(renderer):
	return TestClient(TestServer(_makeApp(renderer)))


def test_parse_size():
	assert _parseSize('1800x1015') == (1800, 1015)
	assert _parseSize('1800X1015') == (1800, 1015)


def test_health_and_status():
	renderer = FakeRenderer()

	async def scenario():
		async with _client(renderer) as client:
			health = await client.get('/health')
			assert health.status == 200
			assert 'ok' in await health.text()

			status = await (await client.get('/status')).json()
			assert status['status'] == 'ok'
			assert status['size'] == [1800, 1015]
			assert status['dashboard'] == 'default.levity'

	_run(scenario)


def test_items_lists_named_panels():
	renderer = FakeRenderer()

	async def scenario():
		async with _client(renderer) as client:
			items = await (await client.get('/items')).json()
			assert [i['name'] for i in items] == ['terrarium']

	_run(scenario)


def test_render_full_defaults_to_no_resize():
	"""Omitting w/h must leave the layout alone - a resize costs a settle."""
	renderer = FakeRenderer()

	async def scenario():
		async with _client(renderer) as client:
			response = await client.get('/render')
			assert response.status == 200
			assert response.content_type == 'image/png'
			assert await response.read() == PNG
			assert renderer.lastFull == (None, 1.0)

	_run(scenario)


def test_render_full_passes_size_and_scale():
	renderer = FakeRenderer()

	async def scenario():
		async with _client(renderer) as client:
			await client.get('/render?w=800&h=600&scale=2')
			assert renderer.lastFull == ((800, 600), 2.0)

	_run(scenario)


def test_render_full_rejects_a_half_given_size():
	"""Width without height would silently render at the wrong aspect."""
	renderer = FakeRenderer()

	async def scenario():
		async with _client(renderer) as client:
			assert (await client.get('/render?w=800')).status == 400

	_run(scenario)


def test_render_rejects_a_non_numeric_scale():
	renderer = FakeRenderer()

	async def scenario():
		async with _client(renderer) as client:
			assert (await client.get('/render?scale=huge')).status == 400

	_run(scenario)


def test_render_item_passes_scale_and_pad():
	renderer = FakeRenderer()

	async def scenario():
		async with _client(renderer) as client:
			response = await client.get('/render/terrarium?scale=3&pad=8')
			assert response.status == 200
			assert renderer.lastItem == ('terrarium', 3.0, 8.0)

	_run(scenario)


def test_unknown_item_is_a_404_not_a_500():
	renderer = FakeRenderer()

	async def scenario():
		async with _client(renderer) as client:
			response = await client.get('/render/nope')
			assert response.status == 404
			assert 'nope' in await response.text()

	_run(scenario)


def test_size_accepts_the_levity_dimension_vocabulary():
	"""w/h should read like a .levity, not like bare pixels only."""
	renderer = FakeRenderer()   # size is (1800, 1015)

	async def scenario():
		async with _client(renderer) as client:
			for query, expected in (
				('w=800&h=600', (800, 600)),          # bare pixels
				('w=800px&h=600px', (800, 600)),      # explicit px
				('w=50%25&h=50%25', (900, 508)),      # relative to the current size
				('w=10in&h=5in&dpi=100', (1000, 500)),  # physical, explicit dpi
			):
				await client.get(f'/render?{query}')
				assert renderer.lastFull[0] == expected, query

	_run(scenario)


def test_size_rejects_something_unparseable():
	renderer = FakeRenderer()

	async def scenario():
		async with _client(renderer) as client:
			assert (await client.get('/render?w=wide&h=600')).status == 400

	_run(scenario)


def test_path_segments_accepts_both_notations():
	assert _pathSegments('0/1/main') == ['0', '1', 'main']
	assert _pathSegments('[0][1][main]') == ['0', '1', 'main']
	assert _pathSegments('/0//1/') == ['0', '1']
	assert _pathSegments('') == []


def test_tree_is_served_with_a_depth():
	renderer = FakeRenderer()

	async def scenario():
		async with _client(renderer) as client:
			body = await (await client.get('/tree?depth=2')).json()
			assert body['type'] == 'CentralPanel'
			assert body['depth'] == 2

	_run(scenario)


def test_render_at_resolves_a_structural_path():
	renderer = FakeRenderer()

	async def scenario():
		async with _client(renderer) as client:
			response = await client.get('/render/at/0/1/main?scale=3&pad=8')
			assert response.status == 200
			assert response.content_type == 'image/png'
			assert renderer.lastAt == (['0', '1', 'main'], 3.0, 8.0)

	_run(scenario)


def test_render_at_is_not_shadowed_by_the_named_item_route():
	"""'at' must not be captured as an item name by /render/{name}."""
	renderer = FakeRenderer()

	async def scenario():
		async with _client(renderer) as client:
			await client.get('/render/at/0')
			assert renderer.lastAt == (['0'], 1.0, 0.0)

	_run(scenario)


def test_render_at_out_of_range_is_a_404_naming_the_options():
	renderer = FakeRenderer()

	async def scenario():
		async with _client(renderer) as client:
			response = await client.get('/render/at/9')
			assert response.status == 404
			assert 'out of range' in await response.text()

	_run(scenario)


def test_load_switches_dashboard():
	renderer = FakeRenderer()

	async def scenario():
		async with _client(renderer) as client:
			response = await client.post('/load', json={'path': 'OpenMeteo.levity'})
			assert response.status == 200
			assert renderer.loaded == 'OpenMeteo.levity'

	_run(scenario)


def test_load_without_a_path_is_a_400():
	renderer = FakeRenderer()

	async def scenario():
		async with _client(renderer) as client:
			assert (await client.post('/load', json={})).status == 400

	_run(scenario)


def test_load_of_a_missing_file_is_a_404():
	renderer = FakeRenderer()

	async def scenario():
		async with _client(renderer) as client:
			assert (await client.post('/load', json={'path': 'nope.levity'})).status == 404

	_run(scenario)


def test_preview_renders_the_posted_document():
	renderer = FakeRenderer()
	document = '- type: stack\n  name: main\n'

	async def scenario():
		async with _client(renderer) as client:
			response = await client.post('/preview?scale=2', data=document)
			assert response.status == 200
			assert response.content_type == 'image/png'
			assert await response.read() == PNG
			assert renderer.previewed == document
			# load and render are separate marshaled calls with an await between
			assert renderer.lastFull == (None, 2.0)

	_run(scenario)


def test_preview_rejects_an_empty_body():
	renderer = FakeRenderer()

	async def scenario():
		async with _client(renderer) as client:
			assert (await client.post('/preview', data='   \n')).status == 400

	_run(scenario)


def test_reload_reloads():
	renderer = FakeRenderer()

	async def scenario():
		async with _client(renderer) as client:
			assert (await client.post('/reload')).status == 200
			assert renderer.reloads == 1

	_run(scenario)
