"""Studio windows are deleted when the test that made them ends.

`Suite` and the editors apply an application-wide palette and style sheet when they open (`setLight`, `_setTheme`), and
Qt re-polishes every widget that is still alive for it. A window a test only `close()`d stays alive, so each later
test pays for all the earlier ones: the same test took 0.5 s alone and 17 s after four others, and a whole run took
for ever. Deleting the window ends that. Only Studio windows go: the dashboard other tests share is left alone.
"""
import pytest

pytest.importorskip('PySide6')


@pytest.fixture(autouse=True)
def _delete_studio_windows():
	yield
	from PySide6.QtCore import QCoreApplication, QEvent
	from PySide6.QtWidgets import QApplication
	from LevityDash.devtools import _studio_builder, _studio_polar, _studio_suite, studio
	kinds = (_studio_suite.Suite, _studio_builder.Builder, _studio_polar.PolarStudio, studio.Studio)
	for widget in QApplication.topLevelWidgets():
		if isinstance(widget, kinds):
			widget.close()
			widget.deleteLater()
	QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
