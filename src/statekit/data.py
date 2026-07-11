"""StateData - a small (state, parent) pairing used when passing a decoded
state value around together with the Stateful instance it belongs to.

Note: the original stateful.py defined *two* classes named `StateData` back
to back - an unrelated dict/list/tuple/str/int/float conversion-registry
class (with its StateStr/StateInt/StateFloat/StateDict/StateList/StateTuple
subclasses and six registerConverstion() calls), immediately shadowed by
this dataclass. Nothing outside that shadowed block ever referenced it by
name (and after the shadowing, the name `StateData` pointed here anyway) -
so the whole conversion-registry cluster was dead code and was dropped
rather than moved.
"""
from dataclasses import dataclass
from typing import Any


@dataclass
class StateData:
	state: Any
	parent: 'Stateful'
