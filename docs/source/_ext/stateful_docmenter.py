import inspect
from types import FunctionType
from typing import Any

from docutils.statemachine import StringList
from sphinx.ext.autodoc import ClassDocumenter, ObjectMembers, AttributeDocumenter, logger, ClassLevelDocumenter, \
    DocstringStripSignatureMixin, PropertyDocumenter

# add src to the path so we can import the stateful module
import sys
from pathlib import Path

from sphinx.util.inspect import safe_getattr, isabstractmethod
from sphinx.util.typing import stringify_annotation

sys.path.append(str(Path.cwd().absolute().parent / 'src'))

from LevityDash.lib.stateful import Stateful, StatefulMixin, StateProperty


class StatePropertyDocumenter(PropertyDocumenter):
    """
    Specialized Documenter subclass for stateful properties.
    """
    objtype = 'stateproperty'
    member_order = 100

    # before PropertyDocumenter
    priority = PropertyDocumenter.priority + 10

    def _is_state_property(self, obj=None) -> bool:
        return isinstance(obj or self.object, StateProperty)

    @classmethod
    def can_document_member(cls, member: Any, membername: str, isattr: bool, parent: Any,
                            ) -> bool:
        if isinstance(parent, ClassDocumenter):
            if isinstance(member, StateProperty):
                return True
            else:
                __dict__ = safe_getattr(parent.object, '__dict__', {})
                obj = __dict__.get(membername, None)
                return isinstance(obj, StateProperty)
        else:
            return False

    def import_object(self, raiseerror: bool = False) -> bool:
        """Check the exisitence of uninitialized instance attribute when failed to import
        the attribute."""
        ret = super().import_object(raiseerror)
        if ret and not self._is_state_property():
            __dict__ = safe_getattr(self.parent, '__dict__', {})
            obj = __dict__.get(self.objpath[-1])
            if isinstance(obj, classmethod) and self._is_state_property(obj.__func__):
                self.object = obj.__func__
                self.isclassmethod = True
                return True
            else:
                return False

        self.isclassmethod = False
        return ret

    def add_directive_header(self, sig: str) -> None:
        super().add_directive_header(sig)
        sourcename = self.get_sourcename()
        if isabstractmethod(self.object):
            self.add_line('   :abstractmethod:', sourcename)
        if self.isclassmethod:
            self.add_line('   :classmethod:', sourcename)

        func = self._get_property_getter()
        if func is None or self.config.autodoc_typehints == 'none':
            return

        try:
            signature = inspect.signature(func,
                                          type_aliases=self.config.autodoc_type_aliases)
            if signature.return_annotation is not inspect.Parameter.empty:
                if self.config.autodoc_typehints_format == "short":
                    objrepr = stringify_annotation(signature.return_annotation, "smart")
                else:
                    objrepr = stringify_annotation(signature.return_annotation,
                                                   "fully-qualified-except-typing")
                self.add_line('   :type: ' + objrepr, sourcename)
        except TypeError as exc:
            logger.warning("Failed to get a function signature for %s: %s",
                           self.fullname, exc)
            pass
        except ValueError:
            pass


class StatefulDocumenter(ClassDocumenter):
    objtype = 'stateproperty'
    directivetype = ClassDocumenter.objtype
    priority = ClassDocumenter.priority + 10

    doc_as_attr = False

    @classmethod
    def can_document_member(
            cls,
            member: Any, membername: str,
            isattr: bool, parent: Any) -> bool:
        try:
            return issubclass(member, (StatefulMixin, Stateful))
        except TypeError:
            return False

    # def get_object_members(self, want_all: bool) -> list[tuple[str, Any]]:
    #     return ClassDocumenter.get_object_members(self, want_all)
    #     a = ClassDocumenter.get_object_members(self, want_all)[1]
    #     for (name, item) in a:
    #         if isinstance(item, StateProperty):
    #             print(name, item)
    #     return a

    def filter_members(self, members: ObjectMembers, want_all: bool,
                       ) -> list[tuple[str, Any, bool]]:
        filtered_members = ClassDocumenter.filter_members(self, members, True)

        if issubclass(self.object, StatefulMixin):
            for name, member in members:
                if isinstance(member, StateProperty):
                    continue
                if isinstance(member, FunctionType) and member.__doc__:
                    filtered_members.append((name, member, False))

        a = filtered_members
        return [(name, member, False if isinstance(member, StateProperty) else is_attr) for name, member, is_attr in
                filtered_members]

    # def add_directive_header(self, sig: str) -> None:
    # 	super().add_directive_header(sig)
    # 	self.add_line('   :final:', self.get_sourcename())

    def get_sourcename(self, obj: StateProperty | Any = None) -> str:
        obj = self.object
        if (safe_getattr(obj, '__module__', None) and
                safe_getattr(obj, '__qualname__', None)):
            # Get the correct location of docstring from self.object
            # to support inherited methods
            fullname = f'{obj.__module__}.{obj.__qualname__}'
        else:
            fullname = self.fullname

        if self.analyzer:
            return f'{self.analyzer.srcname}:docstring of {fullname}'
        else:
            return 'docstring of %s' % fullname

    #
    #
    # def add_content(self,
    #                 more_content: StringList | None,
    #                 no_docstring: bool = False,
    #                 ) -> None:
    #
    #     source_name = self.get_sourcename()
    #     stateful_object: Stateful | StatefulMixin = self.object
    #     use_hex = self.options.hex
    #     self.add_line('', source_name)
    #
    #     for key, prop in stateful_object.__state_items__.items():
    #         the_member_value = prop.docstring
    #         lines, start_line = inspect.getsourcelines(prop.fget)
    #         # prop_line_numbers = [start_line + i for i in range(len(lines))]
    #         if use_hex:
    #             the_member_value = hex(the_member_value)
    #
    #         self.add_line(
    #             f"**{key}**: {the_member_value}", self.get_sourcename(), start_line
    #         )
    #     super().add_content(more_content)


def setup(app):
    """Setup the documenter plugin."""
    app.add_autodocumenter(StatefulDocumenter)
    app.add_autodocumenter(StatePropertyDocumenter)
