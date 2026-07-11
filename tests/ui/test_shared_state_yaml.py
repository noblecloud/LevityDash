"""Regression test for a corrupted `shared:` block in saved dashboards.

`DeepChainMap.__getitem__` wraps any nested-mapping value it returns in a new
`DeepChainMap`, so iterating `.items()` on a shared map can hand back raw
`DeepChainMap` objects as values instead of plain dicts. Those objects used to
leak into `Stateful.shared`'s encoded output, and the YAML dumper's generic
object fallback (`objectRepresentor` in ui/frontends/PySide/utils.py) silently
stringified them via `repr()` instead of raising - producing a `shared:` block
whose value was a plain string. Reloading that file then crashed with
`AttributeError: 'str' object has no attribute 'pop'` in the `shared` setter
(stateful.py) because it always expects a dict.
"""
import re

import yaml

DEEP_CHAIN_MAP_REPR = re.compile(r"DeepChainMap\(")


def test_saved_state_has_no_stringified_deepchainmap(dashboard):
	from LevityDash import LevityDashboard
	from LevityDash.lib.stateful import StatefulDumper

	central = LevityDashboard.CENTRAL_PANEL
	state = central.state

	dumped = yaml.dump(state, Dumper=StatefulDumper, default_flow_style=False, allow_unicode=True)

	assert not DEEP_CHAIN_MAP_REPR.search(dumped), (
		"a DeepChainMap object leaked into the saved YAML instead of being "
		"flattened to a plain dict - this corrupts the file and breaks reload"
	)
