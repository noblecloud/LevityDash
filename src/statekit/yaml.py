"""YAML dump/load machinery for Stateful classes.

Pure PyYAML - no Qt, no LevityDash-domain imports.

Note: the original stateful.py's StatefulConstructor also carried
loadGraphs/loadRealtime/loadClock/loadPanels/loadLabels/loadMoon/itemLoader
methods that imported LevityDash UI modules directly. Those were dead code -
a separate, actually-used set of same-named module-level functions already
lives in LevityDash.lib.ui.frontends.PySide.utils and is what Panel.py /
DateTime.py actually import and call. The class-body versions here were
unreachable (itemLoader's own calls to loadGraphs() etc referenced bare
names that don't resolve inside a class body - a NameError waiting to
happen if ever hit) and were dropped rather than moved to a facade.
"""
from contextlib import contextmanager
from datetime import timedelta
from typing import List

from yaml import SafeDumper
from yaml.composer import Composer
from yaml.constructor import SafeConstructor
from yaml.parser import Parser
from yaml.reader import Reader
from yaml.resolver import Resolver
from yaml.scanner import Scanner


class StatefulConstructor(SafeConstructor):
	node_stack: List['Stateful']
	currentNode: 'Stateful'

	def construct_object(self, node, deep=False):
		return super().construct_object(node, deep=deep)

	def construct_mapping(self, node, deep=False):
		return super().construct_mapping(node, deep=deep)


class StatefulDumper(SafeDumper):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.add_representer(timedelta, self.represent_timedelta)

	def represent_timedelta(self, dumper, data):
		data = data.total_seconds()
		weeks = int(data/(60*60*24*7))
		data -= weeks*60*60*24*7
		days = int(data/(60*60*24))
		data -= days*60*60*24
		hours = int(data/(60*60))
		data -= hours*60*60
		minutes = int(data/60)
		data -= minutes*60
		seconds = int(data)
		result = {}
		if weeks > 0:
			result["weeks"] = weeks
		if days > 0:
			result["days"] = days
		if hours > 0:
			result["hours"] = hours
		if minutes > 0:
			result["minutes"] = minutes
		if seconds > 0:
			result["seconds"] = seconds
		return dumper.represent_dict(result)

	def ignore_aliases(self, data):
		return True


class StatefulLoader(Reader, Scanner, Parser, Composer, StatefulConstructor, Resolver):
	node_stack: List['Stateful'] = []

	def __init__(self, stream):
		Reader.__init__(self, stream)
		Scanner.__init__(self)
		Parser.__init__(self)
		Composer.__init__(self)
		StatefulConstructor.__init__(self)
		Resolver.__init__(self)

	@contextmanager
	def dive(self, node):
		self.node_stack.append(node)
		yield self
		self.node_stack.pop()

	@property
	def currentNode(self):
		return self.node_stack[-1]
