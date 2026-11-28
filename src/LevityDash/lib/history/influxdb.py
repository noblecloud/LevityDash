"""InfluxDB 3 over HTTP, with nothing to install in Python.

Rows go in as line protocol (`POST /api/v3/write_lp`) and come out through SQL (`GET /api/v3/query_sql`), so the
`influxdb3-python` client and its Arrow dependency are not needed. One table, `samples`, holds every plugin and
stream: `plugin`, `stream` and `key` are tags, `number`, `value` (the JSON) and `fetched` are fields, and the row's time
is the time the value is *for*. A row with the same tags and time replaces the older one, so a forecast fetched again
overwrites itself.

- **Retention** is the database's: it is created with `retention_period`, and the server drops what is older. `prune`
  does nothing here.
- **InfluxDB 3 Core limits how much a single query may read** (documented as about 72 hours of data, enforced as a
  count of files, so a quiet database reads further back than a busy one). `restore` in `[History]` is two days by
  default, inside it. The free at-home Enterprise licence lifts the limit.
- **Auth**: a `token` in `[History]` is sent as a bearer token. The supervisor starts the server on 127.0.0.1 without
  auth, which is enough for a display that nothing else can reach.
"""
import json
import logging
import math
from datetime import datetime, timezone
from typing import List, Optional
from urllib import parse, request

from .base import Extent, Sample, fromTimestamp, toTimestamp
from .queued import QueuedBackend

__all__ = ['InfluxDBBackend', 'TABLE', 'lineOf']

log = logging.getLogger('LevityDash.history')

TABLE = 'samples'


def _tag(text: str) -> str:
	return text.replace('\\', '\\\\').replace(',', '\\,').replace('=', '\\=').replace(' ', '\\ ').replace('\n', '\\n').replace('\r', '\\r')


def _string(text: str) -> str:
	return text.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r')


def lineOf(sample: Sample) -> str:
	"""One line of line protocol for `sample`, timestamped in nanoseconds."""
	fields = []
	if sample.number is not None and math.isfinite(sample.number):
		fields.append(f'number={sample.number!r}')
	fields.append(f'value="{_string(sample.encoded())}"')
	fields.append(f'fetched={float(sample.fetched)!r}')
	tags = f'plugin={_tag(sample.plugin)},stream={_tag(sample.stream)},key={_tag(sample.key)}'
	return f'{TABLE},{tags} {",".join(fields)} {int(round(sample.ts * 1_000_000))}000'


def _literal(text: str) -> str:
	return "'" + text.replace("'", "''") + "'"


def _isoLiteral(when) -> str:
	return _literal(fromTimestamp(toTimestamp(when)).strftime('%Y-%m-%dT%H:%M:%S.%fZ'))


def _parseTime(text: str) -> float:
	parsed = datetime.fromisoformat(text.replace('Z', '+00:00'))
	if parsed.tzinfo is None:
		parsed = parsed.replace(tzinfo=timezone.utc)
	return parsed.timestamp()


class InfluxDBBackend(QueuedBackend):
	name = 'influxdb'
	label = 'InfluxDB'

	def __init__(self, host: str = 'localhost', port: int = 8181, database: str = 'levitydash', token: str = '',
	             retentionDays: int = 30, timeout: float = 5.0, secure: bool = False):
		headers = {'Authorization': f'Bearer {token}'} if token else {}
		super().__init__(f'{"https" if secure else "http"}://{host}:{port}', headers, timeout)
		self.database = database
		self.retentionDays = retentionDays
		self._lastSent: Optional[Sample] = None

	def _prepare(self) -> None:
		self._open(request.Request(f'{self.base}/health', headers=self._headers))
		body = json.dumps({'db': self.database, 'retention_period': f'{self.retentionDays}d'}).encode()
		try:
			self._open(request.Request(f'{self.base}/api/v3/configure/database', data=body, method='POST', headers={'Content-Type': 'application/json', **self._headers}))
		except OSError as e:
			if not str(e).startswith('409'):  # 409: the database is already there
				raise

	def _send(self, batch: List[Sample]) -> None:
		body = ('\n'.join(lineOf(s) for s in batch) + '\n').encode('utf-8')
		query = parse.urlencode({'db': self.database, 'precision': 'nanosecond'})
		self._open(request.Request(f'{self.base}/api/v3/write_lp?{query}', data=body, method='POST', headers={'Content-Type': 'text/plain; charset=utf-8', **self._headers}))
		self._lastSent = batch[-1]

	def _applied(self) -> bool:
		# A write is queryable a moment after it is acknowledged (the server flushes its log about once a second).
		if (last := self._lastSent) is None:
			return True
		rows = self.sql(f'select count(*) as n from {TABLE} where {self._where(last.plugin, last.stream, last.ts - 1, last.ts + 1, last.key)}')
		return bool(rows and rows[0].get('n'))

	# -- reading ------------------------------------------------------------------------------------------------

	def sql(self, query: str) -> list:
		return self._getJSON(f'{self.base}/api/v3/query_sql?{parse.urlencode({"db": self.database, "format": "json", "q": query})}')

	def _where(self, plugin: str, stream: str, since, until, key: str | None) -> str:
		clauses = [f'plugin = {_literal(plugin)}', f'stream = {_literal(stream)}', f'time >= {_isoLiteral(since)}']
		if until is not None:
			clauses.append(f'time <= {_isoLiteral(until)}')
		if key is not None:
			clauses.append(f'key = {_literal(key)}')
		return ' and '.join(clauses)

	def _query(self, query: str) -> Optional[list]:
		try:
			rows = self.sql(query)
		except Exception as e:  # noqa: BLE001
			# Nothing has been written yet, so there is no table to read: an empty history, not a fault.
			if 'not found' in str(e):
				return []
			self._warn('a read failed', e)
			return None
		self._ok()
		return rows

	def _sample(self, plugin: str, stream: str, row: dict) -> Optional[Sample]:
		try:
			return Sample(plugin, stream, row['key'], _parseTime(row['time']), json.loads(row['value']), row.get('fetched') or 0.0, row.get('number'))
		except (ValueError, TypeError, KeyError):
			log.warning(f'{plugin}: a stored value for {row.get("key")} is not readable; it is skipped')
			return None

	def read(self, plugin: str, stream: str, since, until=None, key: str | None = None) -> List[Sample]:
		rows = self._query(f'select time, key, value, number, fetched from {TABLE} where {self._where(plugin, stream, since, until, key)} order by time, key')
		return [s for row in rows or () if (s := self._sample(plugin, stream, row)) is not None]

	def extent(self, plugin: str, stream: str, key: str, since, until=None) -> Extent:
		rows = self._query(f'select count(number) as n, min(number) as low, max(number) as high, avg(number) as mean from {TABLE} where {self._where(plugin, stream, since, until, key)}')
		if not rows:
			return Extent(0, None, None, None)
		row = rows[0]
		return Extent(row.get('n') or 0, row.get('low'), row.get('high'), row.get('mean'))

	def latest(self, plugin: str, stream: str, key: str | None = None) -> Optional[Sample]:
		where = f'plugin = {_literal(plugin)} and stream = {_literal(stream)}' + (f' and key = {_literal(key)}' if key is not None else '')
		rows = self._query(f'select time, key, value, number, fetched from {TABLE} where {where} order by time desc limit 1')
		return self._sample(plugin, stream, rows[0]) if rows else None

	def prune(self, stream: str | None, before) -> None:
		"""The database's retention period does this."""
