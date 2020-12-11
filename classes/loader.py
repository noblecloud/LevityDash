from PySide2.QtUiTools import QUiLoader


class UiClassLoader(QUiLoader):
	def __init__(self, base_instance):
		QUiLoader.__init__(self, base_instance)
		self.base_instance = base_instance

	def createWidget(self, class_name, parent=None, name=''):
		if parent is None and self.base_instance:
			return self.base_instance
		else:
			widget = QUiLoader.createWidget(self, class_name, parent, name)
			if self.base_instance:
				setattr(self.base_instance, name, widget)
			return widget
