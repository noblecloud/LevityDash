"""LevityWeb wire messages - the protocol between the web service (a headless
Qt frontend) and its browser clients.

Deliberately a sibling protocol to ``lib/wire`` rather than an extension of it:
this one carries *rendered layout* (absolute geometry + display strings) instead
of raw container updates, and it is owned entirely by the web service, so it
stays out of the heavily-tested lib/wire surface. It reuses lib/wire's shapes
where the concepts are identical - ``encode_container`` payloads for raw values
and the ``ts_request``/``ts_response`` pair for timeseries - but not its message
namespace.

Client -> server:

    hello       {v, w, h, dpr}            announce the canvas; server answers
                                          with 'layout' + 'update', then streams
    ts_request  {v, id, source, key, minPeriod, maxPeriod}
                                          same shape as lib/wire's build_ts_request

Server -> client:

    layout      {v, viewport:{w,h,dpr}, items:[item, ...]}   full snapshot
    update      {v, items:{name: item, ...}}                 changed items only
    ts_response {v, id, ok, error, source, key, timeseries}  same shape as wire
    heartbeat   {v, seq, uptime}                             liveness

An ``item`` is one named element of the resolved dashboard:

    {
      'name':   the .levity name ('' for unnamed),
      'type':   class name of the scene item,
      'z':      scene z-order,
      'rect':   [x, y, w, h] absolute scene coords,
      'parent': nearest named ancestor or None,
      'key':    bound source key (string) if this item displays one,
      'value':  encode_container payload for the bound container, plus a
                'formatted' smart-display string, or None,
      'texts':  [ {rect, text, font, size, weight, color}, ... ] the display
                strings this item renders, as extracted from the live scene -
                identical to what the Qt frontend draws because they ARE the
                strings the Qt frontend drew.
    }
"""
from typing import Dict, List, Optional

WIRE_VERSION = 1


def encode_layout(*, viewport: dict, items: List[dict]) -> dict:
	return {
		'v': WIRE_VERSION,
		'type': 'layout',
		'viewport': {
			'w': int(viewport['w']),
			'h': int(viewport['h']),
			'dpr': float(viewport.get('dpr', 1.0)),
		},
		'items': items,
	}


def encode_update(*, items: Dict[str, dict]) -> dict:
	return {
		'v': WIRE_VERSION,
		'type': 'update',
		'items': items,
	}


def parse_hello(message: dict) -> dict:
	"""Validate a 'hello' and return a normalized viewport dict.

	Anything a browser could plausibly send wrong - missing or non-numeric
	fields, non-positive sizes, fractional pixels, a zero device-pixel-ratio -
	raises ValueError so the server answers with a single error shape.
	"""
	if message.get('type') != 'hello':
		raise ValueError(f"expected a 'hello' message, got {message.get('type')!r}")
	width = int(message.get('w', 0))
	height = int(message.get('h', 0))
	if message.get('w') != width or message.get('h') != height:
		raise ValueError(f'hello needs integer w/h, got {message.get("w")!r}x{message.get("h")!r}')
	if width <= 0 or height <= 0:
		raise ValueError(f'hello needs positive w/h, got {width}x{height}')
	dpr = float(message.get('dpr', 1.0))
	if dpr <= 0:
		raise ValueError(f'hello needs a positive dpr, got {message.get("dpr")!r}')
	return {'w': width, 'h': height, 'dpr': dpr}


def encode_heartbeat(*, seq: int, uptime: float) -> dict:
	return {
		'v': WIRE_VERSION,
		'type': 'heartbeat',
		'seq': int(seq),
		'uptime': float(uptime),
	}
