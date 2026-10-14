"""Registry of the CSS spec sections that the stubs in this package will implement.

Every stub carries `@implements(...)`. The decorator records which part of which spec the
function ports, so a thread that fills in a stub reads one section and nothing else, and
`python -m LevityDash.lib.layout` lists what is still to do.

Port from the spec text only. Never copy from a browser engine or from Taffy.
Section numbers follow Flexbox CR 2018 and Grid CR 2020. They were written from memory, so
check the number against the spec when you implement. The title is the reliable name.
"""

from dataclasses import dataclass
from typing import Callable, Literal, TypeVar

__all__ = ['Section', 'implements', 'REGISTRY', 'pending']

F = TypeVar('F', bound=Callable)

Status = Literal['stub', 'done']


@dataclass(frozen=True, slots=True)
class Section:
	spec: str  # W3C shortname, e.g. `css-flexbox-1`
	title: str  # section title as printed in the spec
	number: str | None = None  # e.g. `9.7`; None where the number is not sure
	status: Status = 'stub'

	@property
	def url(self) -> str:
		return f'https://www.w3.org/TR/{self.spec}/'

	def __str__(self) -> str:
		number = f' §{self.number}' if self.number else ''
		return f'{self.spec}{number} {self.title}'


REGISTRY: dict[str, Section] = {}


def implements(spec: str, title: str, number: str | None = None, *, status: Status = 'stub') -> Callable[[F], F]:
	"""Mark a function as the port of one spec section.

	Change `status` to `'done'` in the same commit that replaces `raise NotImplementedError`.
	"""

	def decorate(function: F) -> F:
		section = Section(spec, title, number, status)
		function.__section__ = section
		REGISTRY[f'{function.__module__}.{function.__qualname__}'] = section
		return function

	return decorate


def pending() -> dict[str, Section]:
	"""The stubs that are not done yet."""
	return {name: section for name, section in REGISTRY.items() if section.status == 'stub'}
