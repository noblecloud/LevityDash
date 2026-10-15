"""Dev-only: drag handles for a bar in the gauge editor: the value, zone edges, fill ends, markers and the track weight.

`Run` is the bar's track in scene coordinates; `barSpecs` makes the handles `HandleLayer` draws. Positions are read from
the bar each time (`Bar._layout`), so a handle follows the track when a control or a drag changes it. A drag writes the same
properties the controls hold (`zones`, `fill`, `markers`, `track`), through `studio.handleEdit`, so undo covers it.
"""
import copy
import math
from typing import Callable, List, Optional

from PySide6.QtCore import QPointF

from LevityDash.devtools._studio_guides import Line
from LevityDash.devtools._studio_stops import niceStep

OFF = 9  # px between the track's edge and a handle that sits beside it


class Run:
	"""A bar's track: where a value sits, and the value at a scene point."""

	def __init__(self, bar):
		self.bar = bar
		layout = bar._layout(None)
		if layout is None:
			raise ValueError('the bar has no room yet')
		self.line = layout['line']
		self.weight = float(layout['weight'])
		self.u = float(layout['u'])
		scale = bar.value_scale
		self.lo, self.span = float(scale.min), float(scale.span)

	def t(self, value: float) -> float:
		return self.bar._t(value)

	def at(self, t: float, cross: float = 0.0) -> QPointF:
		return self.bar.mapToScene(self.bar._point(self.line, t, cross))

	def tOf(self, scene: QPointF) -> float:
		"""The fraction along the track the scene point projects to, clamped to the track."""
		p = self.bar.mapFromScene(scene)
		a, b = self.line.start, self.line.end
		dx, dy = b.x() - a.x(), b.y() - a.y()
		length2 = dx * dx + dy * dy
		return min(1.0, max(0.0, ((p.x() - a.x()) * dx + (p.y() - a.y()) * dy) / length2)) if length2 else 0.0

	def crossOf(self, scene: QPointF) -> float:
		"""How far the scene point is from the track's centre line, in px."""
		p = self.bar.mapFromScene(scene)
		a = self.line.start
		n = self.line.normalAt(0.0)
		return (p.x() - a.x()) * n.x() + (p.y() - a.y()) * n.y()

	def value(self, t: float) -> float:
		return self.lo + self.span * t

	def step(self) -> float:
		return niceStep(self.span / 50)

	def spanPx(self) -> float:
		return float(self.line.lengthPx)


def _plain(v) -> bool:
	return isinstance(v, (int, float)) and not isinstance(v, bool)


def _tidy(v: float):
	return int(v) if float(v).is_integer() else v


def barSpecs(layer) -> list:
	"""The handles for the bar the studio has open."""
	from LevityDash.devtools._studio_handles import Spec
	studio = layer.studio
	out: List = []

	def bar():
		return studio.studio.gauge

	def run() -> Run:
		return Run(bar())

	def guide(r: Run, value: float, t: float, cross: float = 0.0):
		hot = 'v' in layer.hits
		a, b = r.at(t, -(r.weight / 2 + 20)), r.at(t, r.weight / 2 + 20)
		layer.showGuides([Line([a, b], hot=hot)], [layer._tag(f'{t * 100:.0f}% · {value:.4g}', r.at(t, -(r.weight / 2 + 30)))])

	def valueAt(r: Run, p: QPointF, fine: bool) -> tuple:
		t = r.tOf(p)
		v = layer.pick(r.value(t), r.step(), fine, 'fraction', r.spanPx(), r.lo, r.span)
		v = min(max(v, r.lo), r.lo + r.span)
		return v, r.t(v)

	# the value rides the track, as the needle tip does on a dial
	def vpos():
		r = run()
		return r.at(r.t(float(bar().value)), 0.0)

	def vdrag(state, p, fine):
		r = run()
		v, t = valueAt(r, p, fine)
		studio.setValueFromDrag(v)
		guide(r, v, t)
	out.append(Spec('needle', 'Drag to set the preview value', vpos, drag=vdrag, shape='diamond'))

	# markers, below the track
	for i, spec in enumerate(copy.deepcopy(bar()._markerSpecs)):
		if spec.get('time') is not None or not _plain(spec.get('value')):
			continue

		def mpos(i=i):
			specs = bar()._markerSpecs
			if i >= len(specs) or not _plain(specs[i].get('value')):
				return None
			r = run()
			return r.at(r.t(float(specs[i]['value'])), r.weight / 2 + 24)

		def mdrag(state, p, fine, i=i):
			r = run()
			v, t = valueAt(r, p, fine)
			specs = copy.deepcopy(bar()._markerSpecs)
			specs[i]['value'] = _tidy(v)
			studio.handleEdit(('markers',), specs)
			guide(run(), v, t)
		out.append(Spec('marker', f'Drag marker {i + 1} along the track', mpos, drag=mdrag))

	# zone edges, above the track; a cutoff two zones share moves both
	seen = set()
	for i, zone in enumerate(copy.deepcopy(bar()._zoneSpecs)):
		for end in ('from', 'to'):
			v = zone.get(end)
			if not _plain(v) or round(float(v), 6) in seen:
				continue
			seen.add(round(float(v), 6))

			def zpos(i=i, end=end):
				specs = bar()._zoneSpecs
				if i >= len(specs) or not _plain(specs[i].get(end)):
					return None
				r = run()
				return r.at(r.t(float(specs[i][end])), -(r.weight / 2 + OFF))

			def zbegin(i=i, end=end):
				return float(bar()._zoneSpecs[i][end])

			def zdrag(state, p, fine):
				r = run()
				v, t = valueAt(r, p, fine)
				v = _tidy(v)
				specs = copy.deepcopy(bar()._zoneSpecs)
				for spec in specs:
					for e in ('from', 'to'):
						if _plain(spec.get(e)) and math.isclose(float(spec[e]), state, abs_tol=1e-9):
							spec[e] = v
				layer._state = float(v)
				studio.handleEdit(('zones',), specs)
				guide(run(), v, t)
			out.append(Spec('zone', f'Drag zone {i + 1}\'s {end} edge (a shared cutoff moves both zones)', zpos, begin=zbegin, drag=zdrag, shape='square'))

	# fill ends, below the track
	fill = bar()._fillSpec
	for end in ('from', 'to'):
		if not fill or not _plain(fill.get(end)):
			continue

		def fpos(end=end):
			spec = bar()._fillSpec
			if not spec or not _plain(spec.get(end)):
				return None
			r = run()
			return r.at(r.t(float(spec[end])), r.weight / 2 + OFF)

		def fdrag(state, p, fine, end=end):
			r = run()
			v, t = valueAt(r, p, fine)
			spec = copy.deepcopy(bar()._fillSpec)
			spec[end] = _tidy(v)
			studio.handleEdit(('fill',), spec)
			guide(run(), v, t)
		out.append(Spec('fill', f'Drag the fill\'s {end} end', fpos, drag=fdrag))

	# track weight, on the near edge a third of the way along
	def wpos():
		r = run()
		return r.at(0.3, r.weight / 2)

	def wdrag(state, p, fine):
		r = run()
		w = max(2 * abs(r.crossOf(p)), 1.0)
		pct = layer.pick(w / max(r.u, 1) * 100, 0.5, fine, 'fraction', r.u, scale=100, digits=1)
		pct = max(pct, 1.0)
		track = copy.deepcopy(bar()._trackSpec) or {}
		track['weight'] = f'{pct:g}%'
		studio.handleEdit(('track',), track)
		after = run()
		layer.showGuides([Line([after.at(0.3, -after.weight / 2), after.at(0.3, after.weight / 2)], hot='v' in layer.hits)],
		                 [layer._tag(f'{after.weight:.0f}px · {pct:g}%', after.at(0.3, after.weight / 2 + 14))])
	out.append(Spec('weight', 'Drag to set the track weight (Cmd: no snap, Option: fine control)', wpos, drag=wdrag))
	return out


def signature(bar) -> tuple:
	"""What decides which handles a bar has: they are made again when it changes."""
	return (id(bar), len(bar._markerSpecs), len(bar._zoneSpecs), bool(bar._fillSpec))
