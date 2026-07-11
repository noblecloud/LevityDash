"""Pure-Python tests for statekit - no Qt, no LevityDash import required."""
import yaml

from statekit import (
	Default, DefaultFalse, DefaultGroup, DefaultTrue, SourceType, Stateful, StateProperty, StatefulDumper,
	StatefulLoader, StatefulMixin,
)


# --- StateProperty basics: get/set/default ---

class Widget(Stateful, tag='widget'):
	@StateProperty(default='untitled', key='name')
	def name(self) -> str:
		return self._name

	@name.setter
	def name(self, value: str):
		self._name = value

	@StateProperty(default=0, key='count')
	def count(self) -> int:
		return getattr(self, '_count', 0)

	@count.setter
	def count(self, value: int):
		self._count = value


def test_state_property_default_before_set():
	w = Widget()
	assert w.name == 'untitled'
	assert w.count == 0


def test_state_property_get_set_roundtrip():
	w = Widget()
	w.name = 'hello'
	w.count = 5
	assert w.name == 'hello'
	assert w.count == 5


def test_state_property_state_dict_reflects_values():
	w = Widget()
	w.name = 'hello'
	state = w.state
	assert state['name'] == 'hello'
	assert state['type'] == 'widget'


def test_state_property_state_setter_applies_values():
	w = Widget()
	w.state = {'name': 'from-state', 'count': 3}
	assert w.name == 'from-state'
	assert w.count == 3


def test_stateful_subclasses_are_discoverable():
	assert Widget in Stateful.__subclasses__()
	assert Widget.__tag__ == 'widget'


# --- StateProperty factory ---

class Owner(Stateful, tag='owner'):
	@StateProperty(default=Stateful, key='child')
	def child(self) -> 'Child':
		return self._child

	@child.setter
	def child(self, value):
		self._child = value

	@child.factory
	def child(self) -> 'Child':
		return Child()


class Child(Stateful, tag='child'):
	@StateProperty(default='child-name', key='name')
	def name(self) -> str:
		return self._name

	@name.setter
	def name(self, value):
		self._name = value


def test_state_property_factory_constructs_default_child():
	o = Owner()
	assert isinstance(o.child, Child)
	assert o.child.name == 'child-name'


def test_state_property_factory_child_state_applies():
	o = Owner()
	o.state = {'child': {'name': 'renamed'}}
	assert o.child.name == 'renamed'


# --- Default semantics ---

def test_default_wraps_dict_as_defaultdict_subtype():
	d = Default({'a': 1})
	assert dict(d) == {'a': 1}


def test_default_bool_returns_shared_singletons():
	assert Default(True) is DefaultTrue
	assert Default(False) is DefaultFalse


def test_default_group_matches_any_of_its_values():
	group = DefaultGroup(1, 2, 3)
	assert group == 2
	assert 5 not in group
	assert group.value in (1, 2, 3)


# --- SourceType (just confirm the facade re-export is intact) ---

def test_source_type_members():
	assert SourceType.Default.value == 'default'
	assert SourceType.UserConfig.value == 'user_config'


# --- StatefulMixin ---

def test_stateful_mixin_collects_state_items_across_mro():
	class Mixin(StatefulMixin):
		@StateProperty(default=1, key='mixed_in')
		def mixed_in(self) -> int:
			return self._mixed_in

		@mixed_in.setter
		def mixed_in(self, value):
			self._mixed_in = value

	class Combined(Mixin, Stateful, tag='combined'):
		pass

	c = Combined()
	assert c.mixed_in == 1
	c.mixed_in = 9
	assert c.state['mixed_in'] == 9


# --- YAML dump/load idempotence ---

def test_yaml_dump_load_roundtrip_preserves_state():
	w = Widget()
	w.name = 'roundtrip'
	w.count = 42

	dumped = yaml.dump(w.state, Dumper=StatefulDumper, default_flow_style=False, allow_unicode=True)
	loaded = yaml.load(dumped, Loader=StatefulLoader)

	assert loaded['name'] == 'roundtrip'
	assert loaded['count'] == 42
	assert loaded['type'] == 'widget'


def test_yaml_dump_is_idempotent():
	w = Widget()
	w.name = 'stable'
	first = yaml.dump(w.state, Dumper=StatefulDumper, default_flow_style=False, allow_unicode=True)
	second = yaml.dump(w.state, Dumper=StatefulDumper, default_flow_style=False, allow_unicode=True)
	assert first == second


def test_yaml_dumper_encodes_timedelta():
	from datetime import timedelta
	dumped = yaml.dump({'delta': timedelta(days=1, hours=2)}, Dumper=StatefulDumper, default_flow_style=False)
	loaded = yaml.safe_load(dumped)
	assert loaded['delta'] == {'days': 1, 'hours': 2}
