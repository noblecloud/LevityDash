"""Fixed values from a YAML scenario file, for repeatable design work. Dev only.

A real plugin's values change, and a render of a dashboard changes with them.
This plugin publishes the values in a scenario file and nothing else, so two
renders of the same fragment show the same numbers.

**It is off unless you turn it on.** Set ``LEVITYDASH_FIXTURE`` to a scenario
before the first LevityDash import:

	LEVITYDASH_FIXTURE=hot-clear-day

The value is a path to a YAML file, or the name of a file in
``docs/design-references/scenarios/``. With the variable unset this module
marks itself ``__disabled__``: the loader never builds the plugin, never reads
a scenario, and never writes ``Fixture.ini`` into the config directory. The
devtools take ``--scenario NAME`` and set the variable for you (see
``devtools/_seed.py``).

A scenario lists keys. Each key has a ``value`` (the current reading) and an
optional ``series`` (24 hourly values for today, 00:00 to 23:00 local):

	name: hot-clear-day
	keys:
	  environment.temperature.temperature:
	    value: 96
	    unit: f
	    series: [71, 70, ...]

``unit`` is a key from ``schema/units.py`` (``f``, ``c``, ``%%``, ``hPa``).
A compound unit is a pair, ``[mi, hr]``, and needs ``type: wind`` (or another
``unitDict['special']`` name). ``title`` is optional. A key that OpenMeteo also
publishes may leave out ``unit`` and ``title``: they come from the OpenMeteo
schema, in *its* units (Celsius, km/h). A key of your own always needs ``unit``.

The values go in as plugin data, so everything downstream is the real path:
schema, units, containers, the dispatcher, and the wire protocol.
"""
import os
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from LevityDash.lib.log import LevityPluginLog
from LevityDash.lib.plugins.ble import LifecyclePlugin
from LevityDash.lib.plugins.schema import LevityDatagram, SchemaSpecialKeys as tsk

#: The environment variable that turns this plugin on.
ENV_VAR = 'LEVITYDASH_FIXTURE'

log = LevityPluginLog.getChild('Fixture')

#: ``<repo>/docs/design-references/scenarios``. Only exists in a source checkout.
SCENARIO_DIR = Path(__file__).resolve().parents[5] / 'docs' / 'design-references' / 'scenarios'

_TIME_FORMAT = '%Y-%m-%dT%H:%M:%S'

if not os.environ.get(ENV_VAR, '').strip():
	# The loader skips a module with this attribute before it builds anything.
	__disabled__ = True


def findScenario(name: str) -> Path:
	"""A scenario by path, or by name from ``SCENARIO_DIR``."""
	candidate = Path(name).expanduser()
	for path in (candidate, SCENARIO_DIR / f'{name}.yaml', SCENARIO_DIR / name):
		if path.is_file():
			return path
	raise FileNotFoundError(f'no scenario {name!r}: tried {candidate} and {SCENARIO_DIR / (name + ".yaml")}')


def loadScenario(name: str) -> dict:
	"""Read and check a scenario. Raises ``ValueError`` naming the problem."""
	path = findScenario(name)
	with open(path, 'r') as file:
		scenario = yaml.safe_load(file)
	if not isinstance(scenario, dict) or not isinstance(scenario.get('keys'), dict) or not scenario['keys']:
		raise ValueError(f'{path}: a scenario needs a non-empty `keys:` mapping')
	scenario.setdefault('name', path.stem)
	scenario['path'] = str(path)
	return scenario


def _openMeteoDefaults() -> Dict[str, dict]:
	"""``type``/``sourceUnit``/``title`` for every key OpenMeteo publishes."""
	from LevityDash.lib.plugins.builtin.OpenMeteo import schema as openMeteoSchema
	wanted = ('type', 'sourceUnit', 'title', 'description')
	return {
		key: {field: value[field] for field in wanted if field in value}
		for key, value in openMeteoSchema.items()
		if isinstance(value, dict) and 'sourceUnit' in value and 'type' in value
	}


def buildSchema(scenario: dict) -> tuple[dict, Dict[str, str]]:
	"""The schema dict for a scenario, and ``{key: sourceKey}``.

	Each key's source key is its own flattened name, so the realtime and the
	series datagrams share one spelling.
	"""
	defaults = _openMeteoDefaults()
	schema: Dict[str, Any] = {
		'timestamp': {
			'type': 'datetime', 'sourceUnit': 'ISO8601', 'format': _TIME_FORMAT,
			'title': 'Time', 'sourceKey': 'time', tsk.metaData: '@timestamp',
		},
		'dataMaps': {'forecast': {'hourly': 'hourly'}, 'realtime': {'realtime': ()}},
	}
	sourceKeys = {}
	for key, entry in scenario['keys'].items():
		entry = entry if isinstance(entry, dict) else {'value': entry}
		spec = deepcopy(defaults.get(key, {}))
		spec.update({k: v for k, v in entry.items() if k in ('type', 'sourceUnit', 'title', 'description')})
		if 'unit' in entry:
			spec['sourceUnit'] = entry['unit']
		if 'sourceUnit' not in spec:
			raise ValueError(f'{key}: no `unit`, and OpenMeteo does not publish this key')
		spec.setdefault('type', 'measurement')
		spec.setdefault('title', key.rsplit('.', 1)[-1])
		spec['sourceKey'] = sourceKeys[key] = key.replace('.', '_').replace('#', '__')
		schema[key] = spec
	return schema, sourceKeys


class Fixture(LifecyclePlugin, realtime=True, hourly=True, logged=False):
	"""Publishes one scenario. See the module docstring."""

	name = 'Fixture'

	__defaultConfig__ = """
	[plugin]
	enabled = True
	"""

	def __init__(self):
		self.scenario = loadScenario(os.environ[ENV_VAR].strip())
		self.schema, self._sourceKeys = buildSchema(self.scenario)
		super().__init__()
		log.info(f"Fixture: scenario {self.scenario['name']!r} from {self.scenario['path']}")

	# The values are fixed, so there is nothing to keep running. `start()` runs
	# on the plugin's own thread (see `PluginThread`), publishes once and returns.
	# `LifecyclePlugin.start` would park a loop in the default executor, whose
	# thread keeps the process alive after a one-shot render has finished.
	def start(self):
		self.publish()
		self._running = True
		return self

	def stop(self, callback=None):
		self._running = False
		if callback is not None:
			callback()

	def publish(self) -> None:
		"""Push the realtime values and today's hourly series into the observations."""
		keys = self.scenario['keys']
		now = datetime.now().replace(microsecond=0)

		realtime = {'time': now.strftime(_TIME_FORMAT)}
		for key, entry in keys.items():
			value = entry.get('value') if isinstance(entry, dict) else entry
			if value is not None:
				realtime[self._sourceKeys[key]] = value
		datagram = LevityDatagram(realtime, schema=self.schema, dataMap=self.schema.dataMaps['realtime'], static=False)
		self.realtime.update(datagram)

		midnight = now.replace(hour=0, minute=0, second=0)
		times = [(midnight + timedelta(hours=h)).strftime(_TIME_FORMAT) for h in range(24)]
		series = {'time': times}
		for key, entry in keys.items():
			values = entry.get('series') if isinstance(entry, dict) else None
			if values is None:
				continue
			if len(values) != 24:
				raise ValueError(f'{key}: `series` needs 24 hourly values, got {len(values)}')
			series[self._sourceKeys[key]] = list(values)
		if len(series) > 1:
			datagram = LevityDatagram({'hourly': series}, schema=self.schema, dataMap=self.schema.dataMaps['forecast'])
			self.hourly.update(datagram)

		log.info(f"Fixture: published {len(realtime) - 1} values, {len(series) - 1} series")


__plugin__ = Fixture
