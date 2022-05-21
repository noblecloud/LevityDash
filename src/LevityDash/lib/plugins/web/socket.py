from json import JSONDecodeError, loads

import asyncio
import logging
from abc import ABC, abstractmethod
from PySide2.QtCore import QObject, Signal
from typing import Optional


class SocketMessageHandler(ABC):

	@abstractmethod
	def publish(self, message: dict):
		...


class LevityQtSocketMessageHandler(QObject):
	signal = Signal(dict)

	def __init__(self, parent=None):
		super().__init__(parent)

	def publish(self, message):
		self.signal.emit(message)

	def connectSlot(self, slot):
		self.signal.connect(slot)

	def disconnectSlot(self, slot):
		try:
			self.signal.disconnect(slot)
		except TypeError:
			pass
		except RuntimeError:
			pass


# class SocketIO(QThread):
# 	url: str
# 	params: dict
# 	socketParams: dict
# 	relay = Signal(dict)
#
# 	def __init__(self, params: dict = {}, *args, **kwargs):
# 		super(SocketIO, self).__init__()
# 		if 'plugins' in kwargs:
# 			self.plugins = kwargs['plugins']
# 		self.params = params
# 		self.socket.on("connect", self._connect)
# 		self.socket.on("disconnect", self._disconnect)
# 		self.socket.on('*', self._anything)
#
# 	def push(self, message):
# 		self.relay.emit(message)
#
# 	@property
# 	def url(self):
# 		return self.plugins.urls.socket
#
# 	@cached_property
# 	def socket(self):
# 		return socketio.Client(
# 			reconnection=True,
# 			reconnection_attempts=3,
# 			reconnection_delay=5,
# 			reconnection_delay_max=5
# 		)
#
# 	def run(self):
# 		self.socket.connect(url=self.url, **self.socketParams)
#
# 	def begin(self):
# 		self.start()
#
# 	def end(self):
# 		self.socket.disconnect()
#
# 	def _anything(self, data):
# 		self.log.warning('Catchall for SocketIO used')
# 		self.log.debug(data)
#
# 	def _connect(self):
# 		pass
#
# 	def _disconnect(self):
# 		pass


# class Websocket(QThread, Socket):
# 	urlBase = ''
#
# 	@property
# 	def url(self):
# 		return self.urlBase
#
# 	def __init__(self, *args, **kwargs):
# 		super(Websocket, self).__init__(*args, **kwargs)
# 		self.socket = websocket.WebSocketApp(self.url,
# 		                                     on_open=self._open,
# 		                                     on_data=self._data,
# 		                                     on_message=self._message,
# 		                                     on_error=self._error,
# 		                                     on_close=self._close)
#
# 	def run(self):
# 		self.socket.run_forever()
#
# 	def begin(self):
# 		self.start()
#
# 	def end(self):
# 		self.socket.close()
#
# 	def _open(self, ws):
# 		self.log.info(f'Socket {self.__class__.__name__}')
# 		print("### opened ###")
#
# 	def _message(self, ws, message):
# 		pass
#
# 	def _data(self, ws, data):
# 		pass
#
# 	def _error(self, ws, error: bytes):
# 		pass
#
# 	def _close(self, ws):
# 		self.log.info(f'Socket {self.__class__.__name__}')
# 		print("### closed ###")
#
# 	def terminate(self):
# 		self.socket.close()


class BaseSocketProtocol(asyncio.DatagramProtocol):
	api: 'REST'
	handler: 'SockeMessageHandler'

	def __init__(self, api: 'REST'):
		self._plugin = api
		self.handler = LevityQtSocketMessageHandler()
		self.log = api.pluginLog.getChild(self.__class__.__name__)

	def datagram_received(self, data, addr):
		try:
			message = loads(data.decode('utf-8'))
			self.handler.publish(message)
		except JSONDecodeError as e:
			self.log.error(f'Received invalid JSON from {addr}')
			self.log.error(e)

	def connection_made(self, transport):
		self.log.debug('Connection made')

	def connection_lost(self, exc):
		self.log.warning('Connection lost: %s', exc)

	def error_received(self, exc):
		self.log.warning('Error received: %s', exc)

	def pause_writing(self):
		self._transport.pause_reading()

	def resume_writing(self):
		self._transport.resume_reading()

	def eof_received(self):
		self.log.warning('EOF received')

	def write(self, data):
		self.log.error('Not implemented')

	def close(self):
		self.log.info('Closing')

	def abort(self):
		self.log.info('Aborting')

	def push(self, data):
		self.log.error('Not implemented')


class Socket:
	protocol: BaseSocketProtocol
	transport: asyncio.DatagramTransport
	api: 'REST'

	def __init__(self, api: 'REST', *args, **kwargs):
		self.api = api
		self.log = logging.getLogger(f'{api.name}.{self.__class__.__name__}')
		super(Socket, self).__init__(*args, **kwargs)

	def start(self):
		asyncio.create_task(self.run())

	async def run(self):
		raise NotImplementedError


class UDPSocket(Socket):
	last: dict
	port: int

	def __init__(self, api: 'REST', address: Optional[str] = None, port: Optional[int] = None, *args, **kwargs):
		super(UDPSocket, self).__init__(api=api, *args, **kwargs)
		if address is None:
			self.address = '0.0.0.0'
		if port is not None:
			self.port = port
		self.protocol = BaseSocketProtocol(self.api)

	@property
	def handler(self):
		return self.protocol.handler

	async def run(self):
		self.log.info('Starting')
		loop = asyncio.get_event_loop()
		self.transport, self.protocol = await loop.create_datagram_endpoint(lambda: self.protocol, reuse_port=True, local_addr=(self.address, self.port))
