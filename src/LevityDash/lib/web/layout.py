"""Scene extraction for LevityWeb - turn the live Qt scene graph into the
JSON-safe ``item`` payloads the browser frontend renders.

Runs only on the Qt thread (it reads the scene graph) - the same rule as
``scene.render()``. The browser never sees the scene itself; it sees this
flattening: named items with absolute geometry, their bound source key + raw
value, and the *display strings* the Qt frontend actually drew, read straight
off the live text items. Because the strings ARE the Qt frontend's strings,
there is no formatting drift to manage - the smart display pipeline
(WeatherUnits conversion, localization, format filters) has already run.

The web frontend is free to re-style everything; what it cannot do is
second-guess the layout, which is the point. The one thing that does NOT cross
the wire is layout authority.

Attribution model: every scene item is walked recursively; the nearest named
ancestor (an item carrying a ``stateName``) owns it. Unnamed top-level items
become unnamed items under no parent - the web renderer draws them as ambient
backdrop if it wants.
"""
from typing import Any, Dict, List, Optional, Tuple

__all__ = ['snapshot', 'diff']


def _item_name(item: Any) -> Optional[str]:
	name = getattr(item, 'stateName', None)
	return name if isinstance(name, str) and name else None


def _bound_key(item: Any) -> Optional[str]:
	key = getattr(item, 'key', None)
	if key is None:
		return None
	key_str = str(key)
	return key_str if key_str and key_str != 'None' else None


def _rect(item: Any) -> List[float]:
	rect = item.sceneBoundingRect()
	return [round(rect.x(), 3), round(rect.y(), 3), round(rect.width(), 3), round(rect.height(), 3)]


def _color_hex(color: Any) -> Optional[str]:
	"""A '#'-prefixed hex string, from a QColor, a color-holding object, or a
	plain string - components hold their colors as strings as often as QColors."""
	if isinstance(color, str) and color.startswith('#'):
		return color
	try:
		return color.name()
	except Exception:
		try:
			return color.color().name()
		except Exception:
			return None


def _text_payload(item: Any) -> Optional[dict]:
	"""One display string as extracted from a live text item. Duck-typed so a
	bare QGraphicsTextItem works as well as this app's `Text` (QGraphicsPathItem
	with a `.text` StateProperty)."""
	payload: Dict[str, Any] = {'rect': _rect(item)}
	text = getattr(item, 'text', None)
	if text is None and hasattr(item, 'toPlainText'):
		try:
			text = item.toPlainText()
		except Exception:
			text = None
	if not isinstance(text, str) or not text.strip():
		return None
	payload['text'] = text

	try:
		opacity = float(item.opacity())
		payload['opacity'] = round(opacity, 2)
	except Exception:
		pass

	# Qt text alignment flag -> 'top-left' style string, for the browser to
	# place the string inside its rect the same way Qt did.
	try:
		from PySide6.QtCore import Qt

		flag = item.alignment()
		if flag is not None:
			horizontal = 'left'
			if flag & Qt.AlignmentFlag.AlignHCenter:
				horizontal = 'center'
			elif flag & Qt.AlignmentFlag.AlignRight:
				horizontal = 'right'
			vertical = 'middle'
			if flag & Qt.AlignmentFlag.AlignTop:
				vertical = 'top'
			elif flag & Qt.AlignmentFlag.AlignBottom:
				vertical = 'bottom'
			payload['align'] = f'{vertical}-{horizontal}'
	except Exception:
		pass

	font = None
	for attr in ('font', '_font'):
		candidate = getattr(item, attr, None)
		if candidate is None:
			continue
		if callable(candidate):
			try:
				candidate = candidate()
			except Exception:
				candidate = None
		if candidate is not None:
			font = candidate
			break
	if font is not None:
		try:
			payload['font'] = font.family()
		except Exception:
			pass
		try:
			payload['size'] = round(float(font.pointSizeF()), 2)
		except Exception:
			pass
		try:
			payload['weight'] = int(font.weight())
		except Exception:
			pass

	hex_color = None
	for attr in ('_color', 'color'):
		color = getattr(item, attr, None)
		if color is not None and (attr != 'color' or not callable(color)):
			hex_color = _color_hex(color)
			if hex_color is not None:
				break
	if hex_color is None:
		try:
			hex_color = item.brush().color().name()
		except Exception:
			try:
				hex_color = item.pen().color().name()
			except Exception:
				hex_color = None
	if hex_color is not None:
		payload['color'] = hex_color
	return payload


def _walk(item: Any, parent: Optional[str]) -> Tuple[List[dict], List[dict]]:
	"""Recursively flatten an item subtree.

	Returns ``(items, texts)`` where ``items`` is the named-item payload list
	and ``texts`` is the list of text payloads belonging to this subtree level
	(named items collect their own subtree texts recursively).

	Keys: a named item binds every key found in its own unnamed subtree -
	panels hold their displays, and the web frontend wants the panel's whole
	value context, not just one display's key.
	"""
	name = _item_name(item)
	kind = type(item).__name__
	children = list(getattr(item, 'childItems', lambda: ())() or ())

	# A text-bearing leaf renders a display string. Panels also carry their own
	# background - mark those too so the web frontend can paint surfaces that
	# have no text of their own.
	text_payload = _text_payload(item)

	own_key = _bound_key(item)
	named_payload: Optional[dict] = None
	if name is not None:
		named_payload = {
			'name': name,
			'type': kind,
			'z': float(item.zValue()),
			'rect': _rect(item),
			'parent': parent,
			'keys': [own_key] if own_key is not None else [],
			'values': {},
			'texts': [],
		}

	own_texts: List[dict] = []
	if text_payload is not None and name is None:
		# A named item's own text is folded into its payload below; only
		# unattributed text bubbles up to the enclosing named item.
		own_texts.append(text_payload)

	child_items: List[dict] = []
	child_texts: List[dict] = []
	child_keys: List[str] = []
	for child in children:
		ci, ct = _walk(child, name if name is not None else parent)
		child_items.extend(ci)
		child_texts.extend(ct)
		child_keys.extend(_subtree_keys(child))

	if named_payload is not None:
		# A named item owns: its own text, unattributed texts of its subtree,
		# and all texts of descendant named items are owned by those descendants.
		if text_payload is not None:
			named_payload['texts'].append(text_payload)
		named_payload['texts'].extend(child_texts)
		# Keys from unnamed descendants belong to this item; named descendants
		# keep their own (they are already in child_items).
		if own_key is not None:
			child_keys.append(own_key)
		named_payload['keys'] = _dedupe_keys(child_keys)
		child_items.append(named_payload)
		return child_items, []
	return child_items, own_texts + child_texts


def _subtree_keys(item: Any) -> List[str]:
	"""All bound keys in an item's subtree, including its own - but skipping
	descendant NAMED items, whose keys are owned by those items."""
	keys = []
	if _item_name(item) is not None:
		return keys
	if (key := _bound_key(item)) is not None:
		keys.append(key)
	for child in getattr(item, 'childItems', lambda: ())() or ():
		keys.extend(_subtree_keys(child))
	return keys


def _dedupe_keys(keys: List[str]) -> List[str]:
	seen, out = set(), []
	for key in keys:
		if key not in seen:
			seen.add(key)
			out.append(key)
	return out


def _value_payload(key_str: str) -> Optional[dict]:
	"""The bound MultiSourceContainer's current read-surface as a JSON-safe
	dict, or None when nothing has arrived yet. Runs on the Qt thread with
	the live dispatcher - the same values the Qt frontend renders.

	Built directly off the live container, not encode_container: the wire
	encoder targets RemoteContainer (frontend stand-ins) and assumes a
	`.metadata` attribute the live MultiSourceContainer does not have. The
	wire payload *shape* is kept - ContainerFlags field names, value/title -
	so the browser treats both modes identically.
	"""
	try:
		from LevityDash import LevityDashboard
		from LevityDash.lib.plugins.categories import CategoryItem
		from LevityDash.lib.wire.codec import encode_value
		from LevityDash.lib.wire.containers import ContainerFlags

		container = LevityDashboard.dispatcher.getContainer(CategoryItem(key_str))
		if not container:
			return None
		value = container.value  # the preferred/default per-source Container
		if value is None:
			return None
		observation = value.value  # the ObservationValue
		if observation is None:
			return None
		raw = observation.value
		payload = {
			'value': None,
			'key': key_str,
			'title': container.title,
			'flags': {name: getattr(container, name, False) for name in ContainerFlags._fields},
		}
		if raw is not None:
			try:
				encoded = encode_value(raw)
				if isinstance(encoded, (int, float, str, bool, type(None), dict, list)):
					payload['value'] = encoded
			except Exception:
				pass  # icons carry QFonts and are not wire-safe; the glyph
				# string is in the texts[] payload anyway
		try:
			payload['source'] = value.source.name
		except Exception:
			pass
		try:
			payload['formatted'] = str(raw)
		except Exception:
			pass
		return payload
	except Exception:
		return None


def snapshot(scene, resolve_values: bool = True) -> List[dict]:
	"""Full snapshot of the scene as a list of item payloads.

	Item order is scene paint order (reverse z): later items paint on top, and
	the browser renderer preserves that order.
	"""
	items, orphan_texts = [], []
	# scene.items() returns ALL items (children included, stacking order), so
	# recursing every entry would visit each subtree multiple times - root
	# only, and walk down childItems().
	roots = [i for i in scene.items() if getattr(i, 'parentItem', lambda: None)() is None]
	for item in roots:
		si, st = _walk(item, None)
		items.extend(si)
		orphan_texts.extend(st)
	if orphan_texts:
		items.append({
			'name': '',
			'type': '_orphans',
			'z': 0.0,
			'rect': [0.0, 0.0, 0.0, 0.0],
			'parent': None,
			'keys': [],
			'values': {},
			'texts': orphan_texts,
		})
	if resolve_values:
		for item in items:
			for key in item.get('keys') or ():
				payload = _value_payload(key)
				if payload is not None:
					item['values'][key] = payload
	return items


def _texts_key(texts: List[dict]) -> List[Tuple]:
	return [
		(tuple(t['rect']), t.get('text'), t.get('font'), t.get('size'), t.get('weight'), t.get('color'))
		for t in texts
	]


def diff(old: List[dict], new: List[dict]) -> Dict[str, dict]:
	"""Which items changed between two snapshots, as ``{name: payload}``.

	Geometry, texts, bound keys or values all count. Items are matched by
	name - layout authority stays with the service, so the browser just
	applies whatever arrives.
	"""
	by_name_old = {item['name']: item for item in old}
	changed: Dict[str, dict] = {}
	for item in new:
		old_item = by_name_old.get(item['name'])
		if old_item is None or old_item.get('type') != item['type'] or old_item.get('rect') != item['rect'] or old_item.get('keys') != item['keys'] or _texts_key(old_item.get('texts', [])) != _texts_key(item.get('texts', [])):
			changed[item['name']] = item
		else:
			old_values = old_item.get('values') or {}
			new_values = item.get('values') or {}
			for key, payload in new_values.items():
				if payload is None:
					continue
				old_payload = old_values.get(key) or {}
				if old_payload.get('value') != payload.get('value'):
					changed[item['name']] = item
					break
	return changed
