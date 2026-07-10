"""Graph plots must actually render a pixmap (regression: off-thread QPixmap
painting silently produced nothing, so no graph lines drew).

The session fixture loads plugins but never starts them (no network), so plots
have no data here; this test skips until fixed test data (the TestData plugin)
is wired up. The fix is verified live with real OpenMeteo data.
"""
import pytest


def test_data_bearing_plots_render(dashboard):
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Graph import Plot

	plots = [i for i in dashboard.scene.items() if isinstance(i, Plot)]
	assert plots, "expected the default dashboard to contain graph plots"

	data_plots = [p for p in plots
	              if getattr(getattr(p, "data", None), "hasData", None) and p.path().elementCount() > 0]
	if not data_plots:
		pytest.skip("no data-bearing plots (fixture doesn't start plugins; needs fixed test data)")

	# render() is synchronous (GUI-thread paint); each data-bearing plot must
	# produce a non-null pixmap. Off-thread painting used to silently produce
	# nothing, so no graph lines drew.
	unrendered = []
	for p in data_plots:
		p.render()
		dashboard.app.processEvents()
		if p.pixmap().isNull():
			unrendered.append(p.data.key.name)

	assert unrendered == [], f"data-bearing plots produced no pixmap (no lines): {unrendered}"
