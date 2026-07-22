"""statekit - a Qt-independent declarative state/YAML-persistence library.

Extracted from LevityDash's lib/stateful.py. LevityDash.lib.stateful is now
a thin Qt-aware facade over this package: it composes statekit's pure
StatefulMetaclass with Shiboken's QObjectType so Stateful classes can also be
QObject/QGraphicsObject subclasses, and it re-exports every symbol consumers
already import so no consumer file needed to change.

statekit depends on qolkit (generic Python QOL utilities - DotDict,
DeepChainMap, OrderedSet, classproperty, etc.) but does not re-export it:
import those directly from qolkit. What's exported here is state-management
specific, including ActionPool/defer (statekit/actions.py) - unlike
qolkit's utilities, those require Stateful-specific concepts
(is_loading/state_is_loading) and aren't generically reusable.
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
from .actions import ActionPool, ActionPoolItemInstance, block_pools, defer, SubActionPool
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
	"ActionPool", "ActionPoolItemInstance", "block_pools", "defer", "SubActionPool",
	"InvalidArguments", "SingletonConstant", "Stateful", "StateProperty", "StatefulMetaclass", "StatefulMixin",
	"StatefulReferenceProperty", "gendoc",
]
