from abc import abstractmethod

from typing import runtime_checkable, Protocol

__ALL__ = ['HasWeight', 'GraphItem']

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
