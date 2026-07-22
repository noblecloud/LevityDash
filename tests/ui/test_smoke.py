"""Smoke test: the headless dashboard fixture boots and populates the scene."""


def test_dashboard_boots(dashboard):
	texts = dashboard.texts()
	assert len(texts) > 20, f"expected a populated scene, got {len(texts)} text items"


def test_dashboard_has_visible_text(dashboard):
	assert dashboard.visible_texts(), "no visible text with content after boot"
