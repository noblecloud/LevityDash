"""statekit - a Qt-independent declarative state/YAML-persistence library.

Extracted from LevityDash's lib/stateful.py. LevityDash.lib.stateful is now
a thin Qt-aware facade over this package: it composes statekit's pure
StatefulMetaclass with Shiboken's QObjectType so Stateful classes can also be
QObject/QGraphicsObject subclasses, and it re-exports every symbol consumers
already import so no consumer file needed to change.
"""
from .defaults import (
	Default, DefaultDict, DefaultFalse, DefaultFloat, DefaultGroup, DefaultInt, DefaultList, DefaultNone,
	DefaultSet, DefaultState, DefaultString, DefaultTrue, DefaultTuple, DefaultType, DefaultValue, SourceType,
	UnsetDefault, UnsetExisting, isA,
)
from .data import StateData
from .yaml import StatefulConstructor, StatefulDumper, StatefulLoader
from .introspect import (
	Conditions, FrameIterator, ownerParentClass, search_stack, TypedIterable, makeType, makeTypedIterable,
	tryAndLog,
)
from ._compat import (
	ActionPool, ActionPoolItemInstance, block_pools, classproperty, clearCacheAttr, DeepChainMap, defer, DotDict,
	get, guarded_cached_property, IgnoreOr, Index, Infix, OrderedSet, OrUnset, recursiveRemove, remove_empty_dicts,
	sortDict, SubActionPool, Unset, UnsetKwarg,
)
from .core import (
	InvalidArguments, SingletonConstant, Stateful, StateProperty, StatefulMetaclass, StatefulMixin,
	StatefulReferenceProperty, gendoc,
)

__all__ = [
	"Default", "DefaultDict", "DefaultFalse", "DefaultFloat", "DefaultGroup", "DefaultInt", "DefaultList",
	"DefaultNone", "DefaultSet", "DefaultState", "DefaultString", "DefaultTrue", "DefaultTuple", "DefaultType",
	"DefaultValue", "SourceType", "UnsetDefault", "UnsetExisting", "isA",
	"StateData",
	"StatefulConstructor", "StatefulDumper", "StatefulLoader",
	"Conditions", "FrameIterator", "ownerParentClass", "search_stack", "TypedIterable", "makeType",
	"makeTypedIterable", "tryAndLog",
	"ActionPool", "ActionPoolItemInstance", "block_pools", "classproperty", "clearCacheAttr", "DeepChainMap",
	"defer", "DotDict", "get", "guarded_cached_property", "IgnoreOr", "Index", "Infix", "OrderedSet", "OrUnset",
	"recursiveRemove", "remove_empty_dicts", "sortDict", "SubActionPool", "Unset", "UnsetKwarg",
	"InvalidArguments", "SingletonConstant", "Stateful", "StateProperty", "StatefulMetaclass", "StatefulMixin",
	"StatefulReferenceProperty", "gendoc",
]
