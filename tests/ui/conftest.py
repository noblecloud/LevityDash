import pytest


@pytest.fixture(autouse=True)
def _remove_leftover_sandboxes(request):
	"""Remove panels a test added to the shared dashboard and did not remove.

	The `dashboard` fixture lives for the whole session. A test that fails
	before its own cleanup would otherwise leave its sandbox panel in the
	scene, and a later test (a blank-text check, say) would fail on it.
	"""
	if 'dashboard' not in request.fixturenames:
		yield
		return
	dashboard = request.getfixturevalue('dashboard')
	base = dashboard.scene.base
	before = set(base.childItems())
	yield
	for item in base.childItems():
		if item not in before and item.scene() is not None:
			item.scene().removeItem(item)
