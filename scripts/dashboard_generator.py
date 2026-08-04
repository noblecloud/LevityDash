#!/usr/bin/env python3
"""In-repo dashboard generator for LevityDash ``.levity`` layout files.

Why this exists
---------------
The dashboard layout used to be emitted by ``mk3.py`` living in a session
scratchpad, *outside* the repo (see ``docs/tasks/dashboard-redesign.md``). That
is brittle: if the scratchpad is gone, the only source of truth is the installed
``.levity`` and the layout can't be regenerated deterministically. This script
moves that job into the repo: a dashboard is described by a small, declarative
``spec`` (a list of panels + sizes + per-display options) and rendered to a
YAML ``.levity`` file the app loads.

It is *not* a replacement for hand-tuned dashboards. It produces a faithful,
clean baseline; you can still open the emitted file and tweak it by hand. Every
default below encodes a trap that previously cost a full render cycle — see
``docs/tasks/dashboard-traps.md`` for the war stories behind each one.

Usage
-----
    # Emit the Norfolk default layout to stdout
    poetry run python scripts/dashboard_generator.py --preset default_norfolk

    # Write it to a file
    poetry run python scripts/dashboard_generator.py \
        --preset default_norfolk \
        --out src/LevityDash/resources/example-config/templates/dashboards/Generated-Norfolk.levity

    # Emit a custom spec from JSON/YAML
    poetry run python scripts/dashboard_generator.py --spec my_dashboard.yaml

The spec format
----------------
    name: My Dashboard
    base_size: 1920            # only used for human-readable trap warnings
    panels:                   # horizontal band, sizes are % of the stack
      - title: Condition
        size: 20
        items:
          - realtime: environment.condition.icon
            title: false
          - realtime: environment.condition.condition
            title: false
      - title: Wind
        size: 15
        items:
          - realtime: environment.wind.speed.speed
          - realtime: environment.wind.direction.direction
    graph:                    # optional bottom-spanning graph band
      timeframe: {days: 2, hours: 18}
      series:
        - key: environment.temperature.temperature
          gradient: TemperatureGradient
        - key: environment.temperature.feelsLike
          gradient: TemperatureGradient
          weight: 0.6

Panel/item sizes are expressed as percentages and summed; if they don't land
near 97% (the stack reserves ~2-3% for inter-panel spacing) the generator warns
but still emits, because the app silently renders overflow otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

# ---------------------------------------------------------------------------
# Constants encoding the verified dashboard traps (see docs/tasks/dashboard-traps.md)
# ---------------------------------------------------------------------------

# The stack reserves ~2-3% for inter-panel spacing, so declared sizes must sum
# to ~97%, not 100%. A full 100% silently overflows off the right edge.
TARGET_PANEL_SUM = 97.0
PANEL_SUM_TOLERANCE = 2.0

# Keys with no source in the default OpenMeteo/WeatherFlow plugin set. They
# render as "•••" and pad density without adding information — avoid them.
DEAD_KEYS = frozenset({
	"light.irradiance",
	"light.illuminance",
	"precipitation.precipitation",
	"precipitation.daily",
	"precipitation.type",
	"pressure.trend",
	"indoor.temperature.feelsLike",
})

# Time values render as "10:05:41" (with seconds) unless an explicit format is
# supplied. This is the canonical short clock format used across panels.
TIME_FORMAT = "%-I:%M%p"

# Real-time value cells must stop short of 100% height/width or the floating unit
# label clips at the panel edge. 94% is the known-good value.
FLOATING_UNIT_SAFE = 94


def _warn(msg: str) -> None:
	sys.stderr.write(f"dashboard_generator: WARNING: {msg}\n")


# ---------------------------------------------------------------------------
# Item / panel builders
# ---------------------------------------------------------------------------

def realtime_item(key: str, *, title: Any = None, source: Optional[str] = None,
				  display: Optional[Dict[str, Any]] = None,
				  geometry: Optional[Dict[str, Any]] = None,
				  forecast: bool = False) -> Dict[str, Any]:
	"""Build a ``realtime.text`` display item, applying trap-safe defaults."""
	if key in DEAD_KEYS:
		_warn(f"{key!r} is a dead key (no source in the default plugin set); "
			  f"it will render as '•••'. Skipping.")
		return {}
	item: Dict[str, Any] = {"type": "realtime.text", "key": key}
	if title is not None:
		item["title"] = title
	if source is not None:
		item["source"] = source
	if forecast:
		item["forecast"] = True
	item.setdefault("display", {})
	if display:
		item["display"].update(display)
	if geometry:
		item["geometry"] = geometry
	return item


def titled_group(title: str, items: List[Dict[str, Any]], *,
				 size: Optional[float] = None) -> Dict[str, Any]:
	grp: Dict[str, Any] = {
		"type": "titled-group",
		"title": {"height": "0.75cm", "text": title},
		"items": [it for it in items if it],
	}
	if size is not None:
		grp["size"] = f"{size}%"
	return grp


def graph_band(timeframe: Dict[str, Any],
			   series: List[Dict[str, Any]]) -> Dict[str, Any]:
	"""Build the bottom-spanning graph panel with one figure per series."""
	figures = []
	for s in series:
		key = s["key"]
		plot: Dict[str, Any] = {"type": "plot", "resolution": 2}
		if s.get("gradient"):
			plot["gradient"] = s["gradient"]
		if s.get("weight") is not None:
			plot["weight"] = s["weight"]
		fig: Dict[str, Any] = {key: {"plot": plot}}
		if s.get("max") is not None:
			fig[key]["max"] = s["max"]
		figures.append({"figure": s.get("name", key.split(".")[-1]), **fig})
	return {
		"type": "graph",
		"timeframe": timeframe,
		"annotations": {
			"dayLabels": {"alignment": "TopCenter"},
			"hourLabels": {"alignment": "BottomCenter", "spacingIntervals": "1, 3, 6"},
			"lines": {"spacing": "8 mm", "weight": 0.8},
		},
		"figures": figures,
	}


# ---------------------------------------------------------------------------
# Spec -> .levity document
# ---------------------------------------------------------------------------

def build_document(spec: Dict[str, Any]) -> List[Dict[str, Any]]:
	"""Render a spec dict into a LevityDash ``.levity`` document (a list)."""
	base_size = spec.get("base_size", 1920)
	panels: List[Dict[str, Any]] = spec.get("panels", [])
	graph = spec.get("graph")

	# Top band: the panels laid out horizontally.
	band_items = [titled_group(p["title"], p.get("items", []), size=p.get("size"))
				  for p in panels]
	if graph is not None:
		band_items.append(graph_band(graph.get("timeframe", {"days": 2, "hours": 18}),
									 graph.get("series", [])))

	# Trap check: declared panel sizes must sum to ~97%, not 100%.
	declared = [float(str(p.get("size", 0)).rstrip("%")) for p in panels]
	declared_sum = sum(declared)
	if abs(declared_sum - TARGET_PANEL_SUM) > PANEL_SUM_TOLERANCE:
		_warn(f"panel sizes sum to {declared_sum:.1f}% (target ~{TARGET_PANEL_SUM}%). "
			  f"At {base_size}px the stack spacing (~2-3%) will make a 100% layout "
			  f"overflow off the right edge.")

	doc = [{
		"type": "stack",
		"defaultType": "group",
		"name": "main",
		"padding": "1mm",
		"spacing": "2 mm",
		"dividers": {"enabled": True, "opacity": "70%", "size": "99%"},
		"items": [{
			"type": "stack",
			"name": "bottom",
			"direction": "Horizontal",
			"spacing": "20px",
			"dividers": {"enabled": True, "opacity": "70%", "size": "98%"},
			"items": band_items,
		}],
	}]
	return doc


# ---------------------------------------------------------------------------
# Presets — faithful recreations of known-good layouts
# ---------------------------------------------------------------------------

def preset_default_norfolk() -> Dict[str, Any]:
	"""Recreate the live Norfolk default layout structure (15-inch display).

	Bottom band: Condition / Wind / Precipitation. Top band carries the clock
	and temperature stack plus the temperature graph. Sizes use the verified
	~97% split rather than the old 100% that overflowed.
	"""
	return {
		"name": "Norfolk Default (generated)",
		"base_size": 1920,
		"panels": [
			{
				"title": "Condition", "size": 34,
				"items": [
					realtime_item("environment.light.sunrise",
								  title={"size": 0.33, "alignment": "right",
										 "position": "left", "icon": "wi:sunrise"},
								  display={"format": TIME_FORMAT,
										   "valueLabel": {"alignment": "left"}}),
					realtime_item("environment.light.sunset",
								  title={"size": 0.33, "alignment": "right",
										 "position": "left", "icon": "wi:sunset"},
								  display={"format": TIME_FORMAT,
										   "valueLabel": {"alignment": "left"}}),
					realtime_item("environment.condition.icon", title=False,
								  display={"valueLabel": {"margins": "6mm, 2mm"}}),
					realtime_item("environment.condition.condition", title=False,
								  display={"valueLabel": {"margins": "2mm, .5mm"}}),
					realtime_item("environment.temperature.high", source="WeatherFlow",
								  title={"size": 0.33, "text": "High"}),
					realtime_item("environment.temperature.low", source="WeatherFlow",
								  title={"size": 0.33, "text": "Low"}),
				],
			},
			{
				"title": "Wind", "size": 33,
				"items": [
					realtime_item("environment.wind.speed.speed", title=False,
								  display={"unitLabel": {"alignment": "CenterLeft",
														 "matchingGroup": "global.direction"}},
								  geometry={"height": "62%", "width": "100%", "x": "0%", "y": "0%"}),
					realtime_item("environment.wind.direction.direction", title=False,
								  display={"unitLabel": {"filters": ["Lower"]}},
								  geometry={"height": "13%", "width": "42.1%", "x": "57.9%", "y": "49.1%"}),
					realtime_item("environment.wind.speed.gust", title={"text": "Gust"},
								  display={"unitPosition": "hidden"}),
					realtime_item("environment.wind.speed.gustMax", title={"text": "Gusts Max"},
								  display={"unitPosition": "hidden"}),
				],
			},
			{
				"title": "Precipitation", "size": 30,
				"items": [
					realtime_item("environment.precipitation.precipitation", title=False,
								  display={"format-hint": "0.0", "unitPosition": "float-under"},
								  geometry={"height": "50%", "width": "40%", "x": "0%", "y": "50%"}),
					realtime_item("environment.precipitation.daily", title={"text": "Today"},
								  display={"format": "format={value}{self.numerator.unit}, precision=2"}),
					realtime_item("environment.precipitation.daily", title={"text": "Expected"},
								  display={"format": "format={value}in, precision=2"}, forecast=True),
				],
			},
		],
		"graph": {
			"timeframe": {"days": 2, "hours": 18},
			"series": [
				{"key": "environment.temperature.temperature", "gradient": "TemperatureGradient"},
				{"key": "environment.temperature.feelsLike", "gradient": "TemperatureGradient", "weight": 0.6},
				{"key": "environment.temperature.dewpoint", "gradient": None, "name": "dewpoint",
				 "max": None},
			],
		},
	}


PRESETS = {
	"default_norfolk": preset_default_norfolk,
}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _load_spec(path: Path) -> Dict[str, Any]:
	if path.suffix in (".yaml", ".yml"):
		return yaml.safe_load(path.read_text())
	return json.loads(path.read_text())


def main(argv: Optional[List[str]] = None) -> int:
	parser = argparse.ArgumentParser(description="Generate a LevityDash .levity dashboard file.")
	src = parser.add_mutually_exclusive_group(required=True)
	src.add_argument("--preset", choices=list(PRESETS), help="built-in layout preset")
	src.add_argument("--spec", type=Path, help="path to a YAML/JSON dashboard spec")
	parser.add_argument("--out", type=Path, help="write to this .levity path instead of stdout")
	parser.add_argument("--check", action="store_true",
						help="validate the spec (trap checks) without emitting YAML")
	args = parser.parse_args(argv)

	spec = PRESETS[args.preset]() if args.preset else _load_spec(args.spec)

	if args.check:
		build_document(spec)  # runs the trap warnings
		return 0

	doc = build_document(spec)
	body = yaml.safe_dump(doc, sort_keys=False, default_flow_style=False, allow_unicode=True)

	if args.out:
		args.out.parent.mkdir(parents=True, exist_ok=True)
		args.out.write_text(body)
		print(f"wrote {args.out} ({len(body)} bytes)", file=sys.stderr)
	else:
		print(body)
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
