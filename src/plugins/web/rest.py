import asyncio

import requests

from typing import overload

from src.plugins.web import Endpoint, Web
from src.plugins.web.errors import APIError, InvalidCredentials, RateLimitExceeded

__all__ = ["REST"]


class REST(Web, prototype=True):

	def __getData(self, url: str = None, params: dict = None, headers=None) -> dict:
		try:
			request = requests.get(url=url, params=params, headers=headers, timeout=10)

		# TODO: Add retry logic
		except requests.exceptions.ConnectionError:
			self.pluginLog.error('ConnectionError')
			return
		except requests.exceptions.Timeout:
			self.pluginLog.error(f'{self.name} request timed out for {url}')
			return

		if request.status_code == 200:
			self.pluginLog.info(f'{self.name} request successful for {url}')
			self.pluginLog.debug(f'Returned: {str(request.json())[:300]} ... ')
			return self.normalizeData(request.json())
		elif request.status_code == 429:
			self.pluginLog.error('Rate limit exceeded', request.content)
			raise RateLimitExceeded
		elif request.status_code == 401:
			self.pluginLog.error('Invalid credentials', request.content)
			raise InvalidCredentials
		elif request.status_code == 404:
			self.pluginLog.error(f'404: Invalid URL: {request.url}')
		else:
			self.pluginLog.error('API Error', request.content)
			raise APIError(request)

	# @overload
	# async def getData(self, url: str = None, params: dict = None, headers=None) -> dict: ...

	async def getData(self, endpoint: Endpoint, **kwargs) -> dict:
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

		loop = asyncio.get_event_loop()
		return await loop.run_in_executor(None, self.__getData, url, params, headers)
