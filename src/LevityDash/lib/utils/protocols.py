from abc import abstractmethod
from functools import cached_property

from typing import runtime_checkable, Protocol, Hashable

__ALL__ = ['HasWeight', 'GraphItem', 'ValueSubscriber']


@runtime_checkable
class HasWeight(Protocol):


	@property
	@abstractmethod
	def weight(self) -> float:
		...

	@property
	@abstractmethod
	def weight_px(self) -> float:
		...


@runtime_checkable
class GraphItem(Protocol):


	@property
	@abstractmethod
	def graphic(self) -> 'Plot':
		...

	@property
	@abstractmethod
	def figure(self) -> 'Figure':
		...

	@property
	@abstractmethod
	def graph(self) -> 'Graph':
		...


@runtime_checkable
class ValueSubscriber(Protocol):

	@abstractmethod
	def on_value(self, value) -> None:
		...


@runtime_checkable
class ActionPoolItemInstance(Protocol, Hashable):

	@property
	def is_loading(self) -> bool:
		...

	@property
	def state_is_loading(self) -> bool:
		...

	@cached_property
	def action_pool(self) -> 'ActionPool':
		...


@runtime_checkable
class Aligned(Protocol):

	@property
	def alignment(self) -> 'Alignment':
		...
