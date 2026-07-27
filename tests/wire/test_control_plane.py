"""Tests for the plugin control plane (health + liveness).

Covers the 'plugin_status' and 'heartbeat' message pair end to end at the
logic level: RemoteBackend's tick (encode + change-suppression), WireServer's
late-joiner replay, and RemoteFrontend's decode.

Uses stand-in plugins rather than real ``Plugin`` instances, matching
test_containers.py's approach - encode_plugin_status reads its inputs
duck-typed precisely so this is possible without the plugin bootstrap
machinery (config files, schema, threads).
"""
# Import LevityDash before `datetime` - see test_codec.py's import-order note.
from LevityDash.lib.wire.backend import RemoteBackend
from LevityDash.lib.wire.frontend import RemoteFrontend
from LevityDash.lib.wire.messages import (
	PluginState, encode_heartbeat, encode_plugin_status, parse_heartbeat, parse_plugin_status,
)
from datetime import datetime, timezone


class FakePlugin:
	"""Only what encode_plugin_status actually reads."""

	def __init__(self, name, enabled=True, running=True, keys=0):
		self.name = name
		self.enabled = enabled
		self.running = running
		self._keys = keys

	def __len__(self):
		return self._keys


class TestPluginStatusMessage:

	def test_round_trips_every_field(self):
		published = datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc)
		message = encode_plugin_status(
			plugins=[FakePlugin('WeatherFlow', keys=42), FakePlugin('Govee', enabled=False, running=False, keys=3)],
			lastPublish={'WeatherFlow': published},
		)
		states = parse_plugin_status(message)

		assert states['WeatherFlow'] == PluginState('WeatherFlow', True, True, 42, published)
		assert states['Govee'] == PluginState('Govee', False, False, 3, None)

	def test_entries_are_sorted_so_equal_snapshots_compare_equal(self):
		# tick() suppresses an unchanged status by dict equality, which only
		# works if plugin ordering is stable regardless of attach order.
		a = encode_plugin_status(plugins=[FakePlugin('a'), FakePlugin('b')])
		b = encode_plugin_status(plugins=[FakePlugin('b'), FakePlugin('a')])
		assert a == b

	def test_malformed_entry_is_skipped_not_fatal(self):
		states = parse_plugin_status({'plugins': [{'no_name': True}, {'name': 'ok', 'keyCount': 1}]})
		assert set(states) == {'ok'}

	def test_plugin_without_len_still_encodes(self):
		class NoLen:
			name, enabled, running = 'x', True, True

		assert parse_plugin_status(encode_plugin_status(plugins=[NoLen()]))['x'].keyCount == 0

	def test_key_count_comes_from_keys_not_len(self):
		# A real Plugin has no __len__ - len(plugin) raises TypeError, which an
		# over-broad except once reported as 0 keys for every plugin. keys() is
		# the actual published surface.
		class RealShapedPlugin:
			name, enabled, running = 'p', True, True

			def keys(self):
				return {'a', 'b', 'c'}

		assert parse_plugin_status(encode_plugin_status(plugins=[RealShapedPlugin()]))['p'].keyCount == 3

	def test_key_count_falls_back_to_containers(self):
		class ContainersOnly:
			name, enabled, running = 'c', True, True
			containers = {'x': 1, 'y': 2}

		assert parse_plugin_status(encode_plugin_status(plugins=[ContainersOnly()]))['c'].keyCount == 2


class TestHeartbeatMessage:

	def test_round_trips(self):
		assert parse_heartbeat(encode_heartbeat(seq=7, uptime=12.5)) == (7, 12.5)

	def test_tolerates_missing_fields(self):
		assert parse_heartbeat({'type': 'heartbeat'}) == (0, 0.0)


class TestRemoteBackendTick:

	def _backend(self):
		sent = []
		backend = RemoteBackend(send=sent.append)
		return backend, sent

	def test_first_tick_sends_heartbeat_and_status(self):
		backend, sent = self._backend()
		backend._plugins = {'a': FakePlugin('a')}

		backend.tick()

		assert [m['type'] for m in sent] == ['heartbeat', 'plugin_status']
		assert sent[0]['seq'] == 1

	def test_unchanged_status_is_not_resent_but_heartbeat_always_is(self):
		backend, sent = self._backend()
		plugin = FakePlugin('a')
		backend._plugins = {'a': plugin}

		backend.tick()
		backend.tick()
		backend.tick()

		assert [m['type'] for m in sent] == ['heartbeat', 'plugin_status', 'heartbeat', 'heartbeat']
		assert [m['seq'] for m in sent if m['type'] == 'heartbeat'] == [1, 2, 3]

	def test_status_resent_when_a_plugin_changes(self):
		backend, sent = self._backend()
		plugin = FakePlugin('a')
		backend._plugins = {'a': plugin}

		backend.tick()
		plugin.running = False
		backend.tick()

		statuses = [m for m in sent if m['type'] == 'plugin_status']
		assert len(statuses) == 2
		assert statuses[0]['plugins'][0]['running'] is True
		assert statuses[1]['plugins'][0]['running'] is False

	def test_failed_status_send_is_retried_next_tick(self):
		# The 'unchanged' cache must only record what actually went out,
		# otherwise one transient send failure suppresses that snapshot forever.
		sent = []
		fail = {'now': False}

		def send(message):
			if fail['now'] and message['type'] == 'plugin_status':
				raise RuntimeError('socket gone')
			sent.append(message)

		backend = RemoteBackend(send=send)
		backend._plugins = {'a': FakePlugin('a')}

		fail['now'] = True
		backend.tick()
		assert [m['type'] for m in sent] == ['heartbeat']

		fail['now'] = False
		backend.tick()
		assert [m['type'] for m in sent] == ['heartbeat', 'heartbeat', 'plugin_status']

	def test_heartbeat_send_failure_does_not_block_status(self):
		sent = []

		def send(message):
			if message['type'] == 'heartbeat':
				raise RuntimeError('nope')
			sent.append(message)

		backend = RemoteBackend(send=send)
		backend._plugins = {'a': FakePlugin('a')}
		backend.tick()

		assert [m['type'] for m in sent] == ['plugin_status']


class TestRemoteFrontendControlPlane:

	def _frontend(self):
		seen = {'status': [], 'heartbeat': []}
		frontend = RemoteFrontend(
			on_update=lambda batch: seen.setdefault('updates', []).append(batch),
			on_plugin_status=lambda s: seen['status'].append(s),
			on_heartbeat=lambda seq, uptime: seen['heartbeat'].append((seq, uptime)),
		)
		return frontend, seen

	def test_plugin_status_is_decoded_and_cached(self):
		frontend, seen = self._frontend()
		frontend.handle_message(encode_plugin_status(plugins=[FakePlugin('a', keys=2)]))

		assert seen['status'][-1]['a'].keyCount == 2
		# cached on the frontend too, for an observer that connects later
		assert frontend.plugin_states['a'].keyCount == 2

	def test_heartbeat_is_decoded(self):
		frontend, seen = self._frontend()
		frontend.handle_message(encode_heartbeat(seq=4, uptime=1.0))
		assert seen['heartbeat'] == [(4, 1.0)]

	def test_unknown_message_type_is_ignored(self):
		frontend, seen = self._frontend()
		frontend.handle_message({'type': 'something_new'})
		assert seen['status'] == [] and seen['heartbeat'] == []

	def test_control_plane_callbacks_are_optional(self):
		# The update-only construction predates the control plane and must keep
		# working untouched.
		frontend = RemoteFrontend(on_update=lambda batch: None)
		frontend.handle_message(encode_plugin_status(plugins=[FakePlugin('a')]))
		frontend.handle_message(encode_heartbeat(seq=1, uptime=0.0))
		assert frontend.plugin_states['a'].name == 'a'


class TestServerReplay:
	"""WireServer retains the latest plugin_status for late joiners, but must
	never retain a heartbeat - see server.py's _latestStatus comment."""

	def test_status_is_retained_and_heartbeat_is_not(self):
		import asyncio

		from LevityDash.lib.wire.client import WireClient
		from LevityDash.lib.wire.server import WireServer

		async def scenario():
			server = WireServer(host='127.0.0.1', port=0)
			await server.start()
			try:
				# broadcast with nobody connected: only the status is kept
				await server.broadcast(encode_heartbeat(seq=1, uptime=1.0))
				await server.broadcast(encode_plugin_status(plugins=[FakePlugin('a', keys=7)]))

				received = []
				client = WireClient(server.url, received.append)
				await client.connect()
				try:
					end = asyncio.get_running_loop().time() + 2.0
					while asyncio.get_running_loop().time() < end and not received:
						await asyncio.sleep(0.02)
				finally:
					await client.close()

				types = [m['type'] for m in received]
				assert 'plugin_status' in types, f'late joiner got no status: {types}'
				assert 'heartbeat' not in types, 'a stale heartbeat was replayed'
				assert parse_plugin_status(received[0])['a'].keyCount == 7
			finally:
				await server.stop()

		asyncio.run(scenario())


class TestHeartbeatWatchdog:
	"""RemoteConnection.backendAlive - the distinction between 'the socket is
	open' and 'the backend is actually serving'."""

	def _connection(self):
		from LevityDash.lib.wire.remote import RemoteConnection

		class FakeDispatcher:
			def update(self, batch):
				pass

		# Port 0 never accepts, so the background thread just retries with
		# backoff and never interferes; every assertion below drives the
		# control-plane callbacks directly.
		connection = RemoteConnection(FakeDispatcher(), 'ws://127.0.0.1:0/ws')
		connection.stop()
		return connection

	def test_not_alive_while_disconnected_even_with_a_recent_beat(self):
		connection = self._connection()
		connection._on_heartbeat(1, 0.0)
		connection.state = 'disconnected'
		assert connection.backendAlive is False

	def test_alive_when_connected_before_any_beat_arrives(self):
		# Avoids flapping to 'stale' in the window between connecting and the
		# first beat.
		connection = self._connection()
		connection.state = 'connected'
		assert connection.secondsSinceHeartbeat is None
		assert connection.backendAlive is True

	def test_goes_stale_once_beats_stop(self):
		from LevityDash.lib.wire import remote as remote_module

		connection = self._connection()
		connection.state = 'connected'
		connection._on_heartbeat(1, 0.0)
		assert connection.backendAlive is True

		# Backdate the last beat past the threshold rather than sleeping.
		connection._lastHeartbeat -= remote_module._HEARTBEAT_STALE_AFTER + 1
		assert connection.backendAlive is False

	def test_sequence_going_backwards_clears_stale_plugin_snapshot(self):
		connection = self._connection()
		connection.state = 'connected'
		connection._on_heartbeat(9, 40.0)
		connection.plugins = {'a': PluginState('a', True, True, 1, None)}

		connection._on_heartbeat(1, 0.5)  # backend restarted underneath us

		assert connection.plugins == {}
		assert connection._heartbeatSeq == 1
