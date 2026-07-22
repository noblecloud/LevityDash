"""qolkit - small, dependency-free Python quality-of-life utilities.

Sentinels, a dotted-key dict, a recursive ChainMap, an insertion-ordered
set, and a couple of descriptor helpers. No domain concepts, no Qt - these
are useful in any Python project, not just LevityDash. Extracted out of
LevityDash's lib/utils/shared.py, which re-exports everything here so no
consumer file needed to change.

statekit depends on qolkit (for the pieces StateProperty/Stateful/ActionPool
need); qolkit has no reverse dependency on statekit or LevityDash.
"""
from .sentinels import IgnoreOr, Infix, OrUnset, Unset, UnsetKwarg
from .mappings import DeepChainMap, DotDict, get, recursiveRemove, remove_empty_dicts, sortDict
from .collections_ import Index, OrderedSet
from .descriptors import classproperty, clearCacheAttr, guarded_cached_property

__all__ = [
	"IgnoreOr", "Infix", "OrUnset", "Unset", "UnsetKwarg",
	"DeepChainMap", "DotDict", "get", "recursiveRemove", "remove_empty_dicts", "sortDict",
	"Index", "OrderedSet",
	"classproperty", "clearCacheAttr", "guarded_cached_property",
]
