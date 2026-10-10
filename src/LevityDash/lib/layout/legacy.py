"""The bridge from today's `Stack` to the flex algorithm.

The new engine is opt-in. A stack uses it only when one of the new keys is present
(`grow`, `shrink`, `basis`, `justify`, `align`, `wrap`, `min-size`, `max-size`, `order`).
A stack with none of them keeps `Stack.setGeometries`, so existing boards render the same.

This module states the equivalence that makes that safe, as functions. Once they are
implemented, the parity test in `tests/test_layout_skeleton.py` compares the legacy and the
flex result on the shipped boards before anything switches over.

| Stack today                       | flex                                       |
|-----------------------------------|--------------------------------------------|
| `size: X` on an item              | `grow 0, shrink 0, basis X`                |
| item with no `size:`              | `grow 1, shrink 1, basis 0`                |
| `spacing:`                        | `gap` on the main axis                     |
| `padding:`                        | container padding                          |
| items fill the cross axis         | `align-items: stretch`                     |
| items start at the leading edge   | `justify-content: flex-start`              |
| `item-size: X`                    | every unsized item gets `basis X`, `grow 0`|
| `item-size-min` / `-max`          | `min_main` / `max_main` on the unsized item|

Known difference: legacy clamps `item-size-min` after the equal split and does not share the
change with the other items. Flex redistributes. A board that has the clamp bite will move.
The parity test lists such boards; none ship today.
"""

from .flex import FlexContainer, FlexItem
from .spec import implements
from .types import Direction, Edge, Gap, INF

__all__ = ['stack_as_flex']


@implements('css-flexbox-1', 'Flex Layout Algorithm', '9', status='done')
def stack_as_flex(
	direction: str,
	sizes: list[float | None],
	spacing: float,
	padding_main: tuple[float, float],
	padding_cross: tuple[float, float],
	main: float,
	cross: float,
	*,
	item_size: float | None = None,
	item_size_min: float | None = None,
	item_size_max: float | None = None,
) -> tuple[FlexContainer, list[FlexItem]]:
	"""Build the flex container and items that reproduce a legacy `Stack` (table above).

	`sizes[i]` is the item's resolved `size:` in pixels, or None if it has none. All values are
	already in pixels. `direction` is `'vertical'` or `'horizontal'`.

	`main` and `cross` are the stack's full sizes. The container gets the inner sizes (less
	`padding_*`), and `layout_flex` rects start at the padding edge, so the caller adds the
	leading padding to each rect.
	"""
	if direction not in ('vertical', 'horizontal'):
		raise ValueError(f'direction must be vertical or horizontal, got {direction!r}')
	sized_cells = item_size is not None
	items = []
	for size in sizes:
		if size is not None:
			items.append(FlexItem(grow=0.0, shrink=0.0, basis=size, min_main=0.0))
		else:
			items.append(FlexItem(
				grow=0.0 if sized_cells else 1.0,
				shrink=0.0 if sized_cells else 1.0,
				basis=item_size if sized_cells else 0.0,
				min_main=item_size_min if item_size_min is not None else 0.0,
				max_main=item_size_max if item_size_max is not None else INF,
			))
	container = FlexContainer(
		direction=Direction.column if direction == 'vertical' else Direction.row,
		gap=Gap(row=spacing, column=spacing),
		main=main - sum(padding_main),
		cross=cross - sum(padding_cross),
		padding_main=Edge(*padding_main),
		padding_cross=Edge(*padding_cross),
	)
	return container, items
