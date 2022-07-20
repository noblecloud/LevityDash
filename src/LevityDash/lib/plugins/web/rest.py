import errno
from typing import Optional

import aiohttp
from aiohttp import ClientOSError
from rich.pretty import pretty_repr

from LevityDash.lib.plugins.schema import LevityDatagram
from LevityDash.lib.plugins.web import Endpoint, Web
from LevityDash.lib.plugins.web.errors import APIError, InvalidCredentials, RateLimitExceeded, RequestTimeout

__all__ = ["REST"]

from LevityDash.lib.plugins.errors import InvalidData


class REST(Web, prototype=True):

	async def __getData(self, url: str = None, params: dict = None, headers=None) -> dict | APIError | TimeoutError:
		async with aiohttp.ClientSession() as session:
			async with session.get(url, params=params, headers=headers) as response:
				if response.status == 200:
					data = await response.json()
					self.pluginLog.verbose(pretty_repr(data, indent_size=2, max_width=120, max_depth=5, max_length=10, max_string=600), verbosity=5)
					return await response.json()
				elif response.status == 429:
					self.pluginLog.error('Rate limit exceeded', response.content)
					raise RateLimitExceeded
				elif response.status == 401:
					self.pluginLog.error('Invalid credentials', response.content)
					raise InvalidCredentials
				elif response.status == 404:
					self.pluginLog.error(f'404: Invalid URL: {url}')
				else:
					error = await response.text()
					reason = await response.reason()
					self.pluginLog.error('API Error', reason, error)
					raise APIError(response)

	async def getData(self, endpoint: Endpoint, **kwargs) -> LevityDatagram:
		if isinstance(endpoint, str):
			url = kwargs.get('url', endpoint)
			params = kwargs.get('params', {})
			headers = kwargs.get('headers', {})

		else:
			url = kwargs.get('url', endpoint.url)
			params = endpoint.params
			params.update(kwargs.get('params', {}))
			headers = endpoint.headers
			headers.update(kwargs.get('headers', {}))

		try:
			data = await self.__getData(url, params, headers)
			datagram = LevityDatagram(
				self.normalizeData(data),
				schema=self.schema,
				sourceData={'endpoint': endpoint},
				dataMap=self.schema.dataMaps.get(endpoint.name, {})
			)
			if not len(datagram):
				raise InvalidData(f'{self.name}\'s data {endpoint.name} request returned invalid data', endpoint)
			self.pluginLog.verbose(f'{self.name}\'s {endpoint.name} request was successful', verbosity=0)
			self.pluginLog.verbose(f'and received parsed data: {datagram}', verbosity=5)
			return datagram
		except ClientOSError as e:
			if e.errno == errno.ETIMEDOUT:
				self.pluginLog.error(f'{self.name}: {endpoint.name} request timed out for {url}')
				self.pluginLog.exception(e)
				raise RequestTimeout(f'{self.name}: {endpoint.name} request timed out')
			raise APIError(f'{self.name} {endpoint.name} request failed for {url}')
		except Exception as e:
			self.pluginLog.error(f'{self.name} {endpoint.name} request failed for {url}')
			self.pluginLog.exception(e)
			raise APIError(f'{self.name} {endpoint.name} request failed for {url}')

	@property
	def running(self):
		from LevityDash.lib.plugins.utils import ScheduledEvent
		tasks = ScheduledEvent.instances.get(self, [])
		return any(task.running for task in tasks)
