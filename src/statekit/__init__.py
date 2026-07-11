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

__all__ = [
	"Default", "DefaultDict", "DefaultFalse", "DefaultFloat", "DefaultGroup", "DefaultInt", "DefaultList",
	"DefaultNone", "DefaultSet", "DefaultState", "DefaultString", "DefaultTrue", "DefaultTuple", "DefaultType",
	"DefaultValue", "SourceType", "UnsetDefault", "UnsetExisting", "isA",
	"StateData",
	"StatefulConstructor", "StatefulDumper", "StatefulLoader",
	"Conditions", "FrameIterator", "ownerParentClass", "search_stack", "TypedIterable", "makeType",
	"makeTypedIterable", "tryAndLog",
]
