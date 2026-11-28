"""QuestDB over HTTP, with nothing to install in Python.

Rows go in as InfluxDB line protocol (`POST /write`), everything else (the table, the reads, the pruning) is SQL
through `GET /exec`. QuestDB's own `questdb` client is not needed, so this adds no dependency and no wheel that has
to exist for the Python in use.

Writes go through `QueuedBackend` (a queue and a thread, so a plugin never waits and an outage loses nothing). Reads
are plain requests and return an empty answer, logged once, while the server is unreachable.

The table is one wide-open table for every plugin and stream; `DEDUP UPSERT KEYS` makes a row with the same plugin,
stream, key and time replace the older one, so a forecast fetched again overwrites itself instead of piling up.
"""
import base64
import json
import logging
import math
from datetime import datetime, timezone
from typing import List, Optional
from urllib import parse, request

from .base import Extent, Sample, fromTimestamp, toTimestamp
from .queued import QueuedBackend

__all__ = ['QuestDBBackend', 'TABLE', 'escapeTag', 'escapeString', 'lineOf']

log = logging.getLogger('LevityDash.history')

TABLE = 'levity_samples'

_CREATE = (
	f'create table if not exists {TABLE} ('
	'ts timestamp, plugin symbol, stream symbol, key symbol, number double, value varchar, fetched timestamp'
	') timestamp(ts) partition by day wal dedup upsert keys(ts, plugin, stream, key)'
)


def escapeTag(text: str) -> str:
	return text.replace('\\', '\\\\').replace(',', '\\,').replace('=', '\\=').replace(' ', '\\ ').replace('\n', '\\n').replace('\r', '\\r')


def escapeString(text: str) -> str:
	return text.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r')


def lineOf(sample: Sample) -> str:
	"""One line of the line protocol for `sample`."""
	fields = []
	if sample.number is not None and math.isfinite(sample.number):
		fields.append(f'number={sample.number!r}')
	fields.append(f'value="{escapeString(sample.encoded())}"')
	fields.append(f'fetched={int(sample.fetched * 1_000_000)}t')
	tags = f'plugin={escapeTag(sample.plugin)},stream={escapeTag(sample.stream)},key={escapeTag(sample.key)}'
	return f'{TABLE},{tags} {",".join(fields)} {int(sample.ts * 1_000_000)}000'


def _literal(text: str) -> str:
	return "'" + text.replace("'", "''") + "'"


def _isoLiteral(when) -> str:
	return _literal(fromTimestamp(toTimestamp(when)).strftime('%Y-%m-%dT%H:%M:%S.%fZ'))


def _parseTime(text: str) -> float:
	return datetime.fromisoformat(text.replace('Z', '+00:00')).astimezone(timezone.utc).timestamp()


class QuestDBBackend(QueuedBackend):
	name = 'questdb'
	label = 'QuestDB'

	def __init__(self, host: str = 'localhost', port: int = 9000, username: str = '', password: str = '', timeout: float = 5.0, secure: bool = False):
		headers = {'Authorization': 'Basic ' + base64.b64encode(f'{username}:{password}'.encode()).decode()} if username else {}
		super().__init__(f'{"https" if secure else "http"}://{host}:{port}', headers, timeout)

	def sql(self, query: str, limit: int | None = None) -> dict:
		"""Run `query` and return QuestDB's JSON answer. Raises on any failure."""
		params = {'query': query}
		if limit is not None:
			params['limit'] = f'0,{limit}'
		answer = self._getJSON(f'{self.base}/exec?{parse.urlencode(params)}')
		if 'error' in answer:
			raise OSError(answer['error'])
		return answer

	def _prepare(self) -> None:
		self.sql(_CREATE)

	def _send(self, batch: List[Sample]) -> None:
		body = ('\n'.join(lineOf(s) for s in batch) + '\n').encode('utf-8')
		self._open(request.Request(f'{self.base}/write', data=body, method='POST', headers={'Content-Type': 'text/plain; charset=utf-8', **self._headers}))

	def _applied(self) -> bool:
		# The rows are in QuestDB's write-ahead log; a read sees them once the table has applied it.
		rows = self.sql(f"select writerTxn, sequencerTxn from wal_tables() where name = '{TABLE}'")['dataset']
		return not rows or rows[0][0] >= rows[0][1]

	# -- reading ------------------------------------------------------------------------------------------------

	def _where(self, plugin: str, stream: str, since, until, key: str | None) -> str:
		clauses = [f'plugin = {_literal(plugin)}', f'stream = {_literal(stream)}', f'ts >= {_isoLiteral(since)}']
		if until is not None:
			clauses.append(f'ts <= {_isoLiteral(until)}')
		if key is not None:
			clauses.append(f'key = {_literal(key)}')
		return ' and '.join(clauses)

	def _query(self, query: str, limit: int | None = None) -> Optional[list]:
		try:
			dataset = self.sql(query, limit)['dataset']
		except Exception as e:  # noqa: BLE001
			self._warn('a read failed', e)
			return None
		self._ok()
		return dataset

	def _sample(self, plugin: str, stream: str, row: list) -> Optional[Sample]:
		ts, key, value, number, fetched = row
		try:
			return Sample(plugin, stream, key, _parseTime(ts), json.loads(value), _parseTime(fetched) if fetched else 0.0, number)
		except (ValueError, TypeError):
			log.warning(f'{plugin}: a stored value for {key} is not readable; it is skipped')
			return None

	def read(self, plugin: str, stream: str, since, until=None, key: str | None = None) -> List[Sample]:
		rows = self._query(f'select ts, key, value, number, fetched from {TABLE} where {self._where(plugin, stream, since, until, key)} order by ts, key', limit=5_000_000)
		return [s for row in rows or () if (s := self._sample(plugin, stream, row)) is not None]

	def extent(self, plugin: str, stream: str, key: str, since, until=None) -> Extent:
		rows = self._query(f'select count(number), min(number), max(number), avg(number) from {TABLE} where {self._where(plugin, stream, since, until, key)}')
		if not rows:
			return Extent(0, None, None, None)
		count, low, high, mean = rows[0]
		return Extent(count or 0, low, high, mean)

	def latest(self, plugin: str, stream: str, key: str | None = None) -> Optional[Sample]:
		where = f'plugin = {_literal(plugin)} and stream = {_literal(stream)}' + (f' and key = {_literal(key)}' if key is not None else '')
		rows = self._query(f'select ts, key, value, number, fetched from {TABLE} where {where} order by ts desc limit 1')
		return self._sample(plugin, stream, rows[0]) if rows else None

	def prune(self, stream: str | None, before) -> None:
		# QuestDB drops whole day partitions, not rows, so a prune of one stream is left to the next prune of all of them.
		if stream is not None:
			return
		try:
			self.sql(f'alter table {TABLE} drop partition where ts < {_isoLiteral(before)}')
		except Exception as e:  # noqa: BLE001
			# "no partitions to drop" is the normal answer when nothing is old enough
			if 'drop' not in str(e).lower() or 'partition' not in str(e).lower():
				self._warn('the history could not be pruned', e)
