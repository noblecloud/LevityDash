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

from LevityDash.devtools.render_service import RenderError, _makeApp, _parseSize

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


def test_reload_reloads():
	renderer = FakeRenderer()

	async def scenario():
		async with _client(renderer) as client:
			assert (await client.post('/reload')).status == 200
			assert renderer.reloads == 1

	_run(scenario)
