"""Variables in a `.levity` file: `vars:` at the root, `$name` wherever a value goes.

```yaml
vars:
  hot: 90°F
  temp: environment.temperature.temperature
  gap: 3mm
items:
  - type: stack
    padding: $gap
    items:
      - type: text
        text: Hot
        when: $temp > $hot        # spliced as text: environment.temperature.temperature > 90°F
        geometry: {height: $tall} # a whole value keeps its type, so a number stays a number
```

- A value that is exactly `$name` (or `${name}`) becomes the variable, with its own type.
- `$name` or `${name}` inside longer text is spliced in as text. Use the braces when a letter,
  digit or hyphen follows (`${room}-1`).
- A variable may use the ones defined before it.
- A name that is not a variable is left as written, so theme tokens (`$accent`) go on to the
  theme engine, which reports the ones it does not know.
- A save writes the `$name` back. `retemplate` takes what the app would save now, what the file
  resolved to when it loaded, and the file as written: wherever the live value still equals the
  resolved one, it writes the template's text; wherever it differs (the user edited it, or the app
  normalised it) it writes the live value.
- Nothing here raises: a bad `vars:` is logged and the file loads without it.

Qt-free and import-free, so a tool can resolve a file without booting the app.
"""
import logging
import re
from typing import Any, Dict

__all__ = ["resolveVariables", "retemplate", "substitute"]

log = logging.getLogger("LevityDash.variables")

_REFERENCE = re.compile(r'\$(?:\{([A-Za-z_][\w-]*)\}|([A-Za-z_]\w*))')
_WHOLE = re.compile(r'^\s*\$(?:\{([A-Za-z_][\w-]*)\}|([A-Za-z_]\w*))\s*$')


def substitute(value: Any, variables: Dict[str, Any]) -> Any:
	"""`value` with every `$name` that names a variable replaced. Containers are copied, not changed."""
	if isinstance(value, str):
		if (whole := _WHOLE.match(value)) and (name := whole.group(1) or whole.group(2)) in variables:
			return variables[name]

		def splice(match: re.Match) -> str:
			name = match.group(1) or match.group(2)
			return str(variables[name]) if name in variables else match.group(0)

		return _REFERENCE.sub(splice, value) if '$' in value else value
	if isinstance(value, dict):
		return {key: substitute(item, variables) for key, item in value.items()}
	if isinstance(value, list):
		return [substitute(item, variables) for item in value]
	return value


def _definitions(raw: Any) -> Dict[str, Any]:
	if not isinstance(raw, dict):
		log.error(f'vars must be a mapping of names to values, not {raw!r}; the file loads without variables')
		return {}
	variables: Dict[str, Any] = {}
	for name, value in raw.items():
		if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z_][\w-]*', name):
			log.error(f'variable name {name!r} is not a plain name; it is skipped')
			continue
		variables[name] = substitute(value, variables)
	return variables


def resolveVariables(state: Any) -> Any:
	"""The root of a dashboard with its `vars:` applied to everything else. The `vars:` block stays, so a save keeps the definitions."""
	if not isinstance(state, dict) or 'vars' not in state:
		return state
	try:
		variables = _definitions(state['vars'])
		if not variables:
			return state
		return {key: (item if key == 'vars' else substitute(item, variables)) for key, item in state.items()}
	except Exception:
		log.exception('variables could not be applied; the file loads as written')
		return state


def _names(items: list) -> Any:
	"""The `name` of every dict in `items` when each has one and they are all different, else None."""
	if not all(isinstance(item, dict) and isinstance(item.get('name'), str) for item in items):
		return None
	names = [item['name'] for item in items]
	return names if len(set(names)) == len(names) else None


_LEADING_NUMBER = re.compile(r'^\s*([-+]?\d+(?:\.\d+)?)\s*[°º˚]?\s*$')


def _same(live: Any, resolved: Any) -> bool:
	"""Equal, or the same number once the app has added a degree sign (`30°` for `30`)."""
	if live == resolved:
		return True
	if isinstance(live, str) and isinstance(resolved, (int, float)) and not isinstance(resolved, bool):
		found = _LEADING_NUMBER.match(live)
		return found is not None and float(found.group(1)) == float(resolved)
	return False


def retemplate(live: Any, resolved: Any, template: Any) -> Any:
	"""`live` with the `$name` text of `template` restored wherever `live` still equals `resolved`.

	`resolved` is `template` after `resolveVariables`, so the two have the same shape. A list lines up by
	`name` when every item has a distinct one, else by position, and only when the lengths agree.
	"""
	try:
		if _same(live, resolved):
			return template
		if isinstance(live, dict) and isinstance(resolved, dict) and isinstance(template, dict):
			return {
				key: retemplate(value, resolved[key], template[key]) if key in resolved and key in template else value
				for key, value in live.items()
			}
		if isinstance(live, list) and isinstance(resolved, list) and isinstance(template, list) and len(resolved) == len(template):
			liveNames, resolvedNames = _names(live), _names(resolved)
			if liveNames is not None and resolvedNames is not None:
				where = {name: index for index, name in enumerate(resolvedNames)}
				return [
					retemplate(item, resolved[where[name]], template[where[name]]) if name in where else item
					for name, item in zip(liveNames, live)
				]
			if len(live) == len(resolved):
				return [retemplate(*triple) for triple in zip(live, resolved, template)]
	except Exception:
		log.exception('a save could not restore the variable names; it writes the values')
	return live
