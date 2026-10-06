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
- Nothing here raises: a bad `vars:` is logged and the file loads without it.

Qt-free and import-free, so a tool can resolve a file without booting the app.
"""
import logging
import re
from typing import Any, Dict

__all__ = ["resolveVariables", "substitute"]

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
