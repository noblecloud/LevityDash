from typing import Optional

import aiohttp
from rich.pretty import pretty_repr

from LevityDash.lib.plugins.schema import LevityDatagram
from LevityDash.lib.plugins.web import Endpoint, Web
from LevityDash.lib.plugins.web.errors import APIError, InvalidCredentials, RateLimitExceeded

__all__ = ["REST"]


class REST(Web, prototype=True):

	async def __getData(self, url: str = None, params: dict = None, headers=None) -> Optional[dict]:
		async with aiohttp.ClientSession() as session:
			async with session.get(url, params=params, headers=headers) as response:
				if response.status == 200:
					self.pluginLog.info(f'{self.name} request successful for {url}')
					data = await response.json()
					self.pluginLog.debug(pretty_repr(data, indent_size=2, max_width=120, max_depth=5, max_length=10, max_string=600))
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
					self.pluginLog.error('API Error', response.content)
					raise APIError(response)

	# try:
	# 	request = requests.get(url=url, params=params, headers=headers, timeout=10)
	#
	# 	# TODO: Add retry logic
	# 	except aiohttp.client_exceptions.ClientConnectorError as e:
	# 		self.pluginLog.error('ConnectionError')
	# 		return
	# 	except aiohttp.ServerTimeoutError as e:
	# 		self.pluginLog.error(f'{self.name} request timed out for {url}')
	# 		return

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
			datagram = LevityDatagram(data, schema=self.schema, sourceData={'endpoint': endpoint}, dataMap=self.schema.dataMaps.get(endpoint.name, {}))
			self.pluginLog.verbose(f'{self.name} received parsed data: {datagram}')
			return self.normalizeData(datagram)
		except Exception as e:
			self.pluginLog.error(f'{self.name} request failed for {url}')
			self.pluginLog.exception(e)
			return LevityDatagram({})

	@property
	def running(self):
		from LevityDash.lib.plugins.plugin import ScheduledEvent
		tasks = ScheduledEvent.instances.get(self, [])
		return any(task.timer.when() for task in tasks)
