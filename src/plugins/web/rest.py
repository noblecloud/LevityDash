import asyncio
from typing import Optional

import aiohttp

from src.plugins.translator import LevityDatagram
from src.plugins.web import Endpoint, Web
from src.plugins.web.errors import APIError, InvalidCredentials, RateLimitExceeded

__all__ = ["REST"]


class REST(Web, prototype=True):

	async def __getData(self, url: str = None, params: dict = None, headers=None) -> Optional[dict]:
		async with aiohttp.ClientSession() as session:
			async with session.get(url, params=params, headers=headers) as response:
				if response.status == 200:
					self.pluginLog.info(f'{self.name} request successful for {url}')
					data = await response.json()
					self.pluginLog.debug(f'Returned: {str(data)[:300]} ... ')
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
			datagram = LevityDatagram(data, translator=self.translator, sourceData={'endpoint': endpoint}, dataMap=self.translator.dataMaps.get(endpoint.name, {}))
			return self.normalizeData(datagram)
		except Exception as e:
			self.pluginLog.error(f'{self.name} request failed for {url}')
			self.pluginLog.exception(e)

	@property
	def running(self):
		from src.plugins.plugin import ScheduledEvent
		tasks = ScheduledEvent.instances.get(self, [])
		return any(task.timer.when() for task in tasks)
