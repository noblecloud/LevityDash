"""Border beams: a travelling or breathing glow around a panel.

The painting engine (`styles`, `palettes`, `types`) is a port of the React component
border-beam (https://github.com/Jakubantalik/border-beam) by way of the PySide6 port
`border-beam-qt`. The painters reuse the component's CSS values, so its licence applies
to this package:

	MIT License

	Copyright (c) the border-beam authors

	Permission is hereby granted, free of charge, to any person obtaining a copy of this
	software and associated documentation files (the "Software"), to deal in the Software
	without restriction, including without limitation the rights to use, copy, modify,
	merge, publish, distribute, sublicense, and/or sell copies of the Software, and to
	permit persons to whom the Software is furnished to do so, subject to the following
	conditions:

	The above copyright notice and this permission notice shall be included in all copies
	or substantial portions of the Software.

	THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
	INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
	PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
	HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF
	CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE
	OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

What is here:

- `styles`, `palettes`, `types`: the painters and colour tables, moved from `border_beam`.
- `ring`: the Oklch ring colours, on top of `lib/ui/colors/oklch.py`.
- `pulse_driver`: one shared clock that runs only while a beam animates.
- `item`: `PanelBeam`, the panel decoration that the `beam:` setting of a `.levity` builds.

Qt rules learned in `border-beam-qt` and kept in the code:

- `QConicalGradient` runs counter-clockwise and CSS conic angles run clockwise, so angles are negated.
- `PulseDriver.set_time()` must tolerate a dead `QTimer` at interpreter shutdown.
- `QGraphicsEffect` does not run under `render()`. The beam is a plain item and paints directly.
"""

from .types import ColorSpace, ColorVariant, Size, Theme

__all__ = ('ColorSpace', 'ColorVariant', 'Size', 'Theme')
