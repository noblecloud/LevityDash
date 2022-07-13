from dataclasses import dataclass, field

from enum import Enum

from rich import repr

from LevityDash.lib.config import PluginConfig
from LevityDash.lib.plugins import Plugin
from datetime import timedelta
from typing import Any, ClassVar, Dict, Optional, Union

__all__ = ["AuthType", "Auth", "URLs", "Endpoint", "Web", "REST"]


@repr.auto
class AuthType(Enum):
	NONE = 0
	BASIC = 1
	PARAMETER = 2
	OAUTH = 3
	OAUTH2 = 4

	@classmethod
	def _missing_(cls, value):
		return AuthType.NONE


@dataclass
class Auth:
	authType: AuthType = field(default=AuthType.NONE, hash=True)
	authData: Dict[str, str] = field(default_factory=dict, hash=True)

	@property
	def vars(self):
		return {i for i in self.authData.values() if isinstance(i, str) and i.startswith('@')}

	def __repr__(self):
		data = {k: self.__obfuscateSensitiveData(v) for k, v in self.authData.items()}
		return f'Auth({self.authType.name}, data={data})'

	def __str__(self):
		return repr(self)

	@staticmethod
	def __obfuscateSensitiveData(value: str):
		if len(value) > 8:
			return value[:4] + '...' + value[-4:]
		else:
			return hash(value)


class URLsMeta(type):
	def __new__(cls, name, bases, attrs, base: str = None):
		def findAttr(attr: str, required: bool = False, default: Any = None, defaultType=object, **kwargs):
			if attr in attrs:
				value = attrs.pop(attr)
				if isinstance(value, defaultType):
					return value
			for baseCls in bases:
				if hasattr(baseCls, attr):
					value = getattr(baseCls, attr)
					if isinstance(value, defaultType):
						return value
			if required:
				message = kwargs.get('errorMessage', f'{attr} is required for {name}')
				error = kwargs.get('error', AttributeError)
				if issubclass(error, Exception):
					raise error(message)
				raise AttributeError(message)
			if defaultType is not object:
				if isinstance(defaultType, tuple):
					return defaultType[0]()
				return defaultType()
			return default

		if base is not None:
			if isinstance(base, str):
				kwargs = {
					'base':            base,
					'method':          findAttr('method', default=None, required=False),
					'port':            findAttr('port', default=80, required=False),
					'protocol':        findAttr('protocol', default='https', required=False),
					'auth':            findAttr('auth', defaultType=Auth, required=False),
					'params':          findAttr('params', default=None, required=False),
					'headers':         findAttr('headers', default=None, required=False),
					'refresh':         findAttr('refresh', default=None, required=False),
					'refreshInterval': findAttr('refreshInterval', default=None, required=False),
					'period':          findAttr('period', default=None, required=False)
				}
			else:
				kwargs = {}

			attrs.update(kwargs)

		return super().__new__(cls, name, bases, attrs)


@repr.auto
class URLs(metaclass=URLsMeta):
	base: str
	auth: Auth

	__instances: ClassVar[dict[Plugin, 'URLs']] = dict()

	def __init__(self, plugin=None):
		endpoints = ((endpointName, endpoint) for endpointName, endpoint in self.__class__.__dict__.items() if isinstance(endpoint, Endpoint))
		self.__plugin = plugin
		self.endpoints = dict()
		match plugin:
			case None:
				for endpointName, endpoint in endpoints:
					if endpoint.base is None:
						endpoint.base = self
					endpoint.name = endpointName
			case Plugin():
				for endpointName, endpoint in endpoints:
					exec(f'self.{endpointName} = endpoint')
					endpoint.name = endpointName
					if isinstance(endpoint.base, type(self)):
						endpoint.base = self

	@property
	def default(self):
		if hasattr(self, 'endpoint'):
			return self.endpoint
		return self.base

	def __str__(self):
		return self.base

	def __get__(self, instance, owner):
		if instance in self.__instances:
			return self.__instances[instance]
		new = type(self)(plugin=instance)
		self.__instances[instance] = new
		return new

	def __set__(self, instance, value):
		self.__instances[instance] = value

	# def __getattribute__(self, key):
	# 	if not key.startswith('__') and key in self.__dict__:
	# 		return self.__dict__[key]
	# 	return super().__getattribute__(key)

	@property
	def config(self) -> Optional['PluginConfig']:
		return getattr(self.plugin, 'config', None)

	@classmethod
	def newInstance(cls, owner):
		return cls(plugin=owner)

	@property
	def plugin(self):
		return self.__plugin


@repr.auto
class Endpoint(object):
	base: URLs
	params: dict
	url: str
	method: str
	headers: dict
	refresh: bool
	refreshInterval: Optional[timedelta]
	period: Optional[timedelta]
	name: Optional[str]
	__protocol: Optional[str]
	__method: Optional[str]
	__base: Optional['Endpoint']
	__url: Optional[str]
	__params: Optional[dict]
	__headers: Optional[dict]
	__refresh: Optional[bool]
	__refreshInterval: Optional[timedelta]
	__period: Optional[timedelta]
	__auth: Optional[Auth]
	__name: Optional[str]
	__dataMap: Optional[Dict[str, Any]]

	def __init__(self,
		method: str = None,
		protocol: str = None,
		base: Union[URLs, str, 'Endpoint'] = None,
		url: str = None,
		params: dict = None,
		headers: dict = None,
		refresh: bool = False,
		refreshInterval: Optional[timedelta] = None,
		period: Optional[timedelta] = None,
		auth: Optional[Auth] = None):
		self.method = method if method is not None else 'GET'
		self.protocol = protocol if protocol is not None else 'https'
		self.base = base
		self.url = url or ''
		self.params = params or {}
		self.headers = headers or {}
		self.refresh = refresh
		self.refreshInterval = refreshInterval
		self.period = period
		self.auth = auth
		self.__inherit = {'headers', 'params', 'auth'}
		self.__instances: dict = dict()

	@classmethod
	def newInstance(cls, owner):
		return cls(base=owner)

	def parseData(self, data: dict) -> dict:
		return data

	@property
	def protocol(self) -> str:
		if self.__protocol is None:
			return self.__base.protocol
		return self.__protocol

	@protocol.setter
	def protocol(self, value: str):
		self.__protocol = value

	@property
	def method(self) -> str:
		if self.__method is None:
			return self.__base.method
		return self.__method

	@method.setter
	def method(self, value: str):
		self.__method = value

	@property
	def base(self) -> Union[URLs, str]:
		return self.__base

	@base.setter
	def base(self, value: Union[URLs, str]):
		self.__base = value

	@property
	def urlBase(self):
		if isinstance(self.base, Endpoint):
			return self.base.urlBase
		return self.base

	@property
	def url(self):
		url = self.__url
		if self.__base is None:
			value = url
		else:
			value = f'{self.protocol}://{self.base}/{url}'
		return value

	def _applyConfigVariables(self, value: str) -> str:
		match value:
			case str() if '{' in value:
				return value.format(**self.config.defaults())
			case dict():
				for key in value:
					value[key] = self._applyConfigVariables(value[key])
				return value
			case _:
				return value
		return value

	def __str__(self):
		string = f'{self.base}/{self.__url}'
		# if '{' in string:
		# 	string = string.format(**self.params)
		return string

	@url.setter
	def url(self, value):
		self.__url = value

	@property
	def params(self):
		params = {}
		if 'params' in self.__inherit:
			params.update(self.__base.params or {})
		params.update(self.__params or {})
		if (auth := self.auth).authType == AuthType.PARAMETER:
			params.update(auth.authData)
		return params

	@params.setter
	def params(self, value):
		self.__params = value

	@property
	def headers(self):
		if 'headers' in self.__inherit:
			headers = self.__base.headers or {}
			headers.update(self.__headers)
			return headers
		return self.__headers

	@headers.setter
	def headers(self, value):
		self.__headers = value

	@property
	def refresh(self):
		return self.__refresh

	@refresh.setter
	def refresh(self, value):
		self.__refresh = value

	@property
	def refreshInterval(self):
		if self.__refreshInterval is None:
			return self.__base.refreshInterval
		return self.__refreshInterval

	@refreshInterval.setter
	def refreshInterval(self, value):
		self.__refreshInterval = value

	@property
	def period(self):
		return self.__period

	@period.setter
	def period(self, value):
		self.__period = value

	@property
	def auth(self):
		if 'auth' in self.__inherit:
			if self.__auth is None:
				return self.__base.auth
			authData = {}
			auth = self.__base.auth or Auth()
			if auth.authType == self.__auth.authType:
				authData.update(auth.authData)
			authData.update(self.__auth.authData)
			return Auth(auth.authType, self._applyConfigVariables(authData))
		return self.__auth

	@auth.setter
	def auth(self, value):
		self.__auth = value

	@property
	def name(self):
		return self.__name

	@name.setter
	def name(self, value):
		self.__name = value

	def __get__(self, instance, owner):
		if self.name in instance.endpoints:
			return instance.endpoints[self.name]
		return self

	def __getattribute__(self, name):
		value = super().__getattribute__(name)
		if name != '_applyConfigVariables':
			func = super().__getattribute__('_applyConfigVariables')
			return func(value)
		return value

	def __set__(self, instance, value):
		instance.endpoints[self.name] = value

	@property
	def config(self):
		return getattr(self.urlBase, 'config', None)


class Web(Plugin, prototype=True):
	urls: URLs

	def __init__(self, *args, **kwargs):
		super().__init__()

	def normalizeData(self, rawData):
		return rawData


from .rest import *
