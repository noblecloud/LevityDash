"""Tests for scripts/dashboard_generator.py — in-repo .levity generator.

Covers: valid YAML emission, the panel-size-sum trap warning, the dead-key
refusal, and a snapshot test that pins the emitted panel/type tree against a
checked-in fixture so drift from the *declared baseline* fails CI (rather than
needing a manual dump against the hand-tuned live default.levity, which the
generator was never meant to reproduce).
"""
import importlib.util
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC = REPO_ROOT / "scripts" / "dashboard_generator.py"
SNAPSHOT = REPO_ROOT / "tests" / "snapshots" / "default_norfolk.levity"


def _load_module():
	# scripts/ is not a package; load it by path
	spec = importlib.util.spec_from_file_location("dashboard_generator", SPEC)
	mod = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(mod)
	return mod


dg = _load_module()


def _emit() -> dict:
	"""Generate the default_norfolk preset and return the parsed document."""
	import io, contextlib
	buf = io.StringIO()
	with contextlib.redirect_stdout(buf):
		rc = dg.main(["--preset", "default_norfolk"])
	assert rc == 0
	return yaml.safe_load(buf.getvalue())


def test_preset_emits_valid_yaml(tmp_path):
	out = tmp_path / "out.levity"
	rc = dg.main(["--preset", "default_norfolk", "--out", str(out)])
	assert rc == 0
	data = yaml.safe_load(out.read_text())
	assert isinstance(data, list) and len(data) == 1
	# main stack -> bottom band -> 3 panels (no top band / graph in baseline)
	bands = data[0]["items"][0]["items"]
	assert len(bands) == 3
	# every band is a titled-group with a text title
	for band in bands:
		assert band["type"] == "titled-group"
		assert isinstance(band["title"].get("text"), str)


def test_dead_key_is_refused_and_warns(capsys):
	# indoor.temperature.feelsLike is genuinely undefined in the default plugin set
	# (Govee's indoor.temperature.* block has temperature/dewpoint/heatIndex, no
	# feelsLike, and no other builtin plugin uses the `indoor` namespace)
	result = dg.realtime_item("indoor.temperature.feelsLike")
	assert result == {}
	captured = capsys.readouterr()
	assert "dead key" in captured.err


def test_panel_size_sum_trap_warns(capsys):
	# a 100%-sum spec should warn about overflow
	spec = {"name": "x", "panels": [
		{"title": "A", "size": 50, "items": []},
		{"title": "B", "size": 50, "items": []},
	]}
	dg.build_document(spec)
	captured = capsys.readouterr()
	assert "panel sizes sum to 100.0%" in captured.err


def test_good_size_sum_is_quiet(capsys):
	# ~97% split should emit no size warning
	spec = {"name": "x", "panels": [
		{"title": "A", "size": 34, "items": []},
		{"title": "B", "size": 33, "items": []},
		{"title": "C", "size": 30, "items": []},
	]}
	dg.build_document(spec)
	captured = capsys.readouterr()
	assert "panel sizes sum" not in captured.err


def test_forecast_flag_threads_through():
	item = dg.realtime_item("environment.precipitation.daily", forecast=True,
							title={"text": "Expected"})
	assert item.get("forecast") is True


def test_preset_matches_snapshot():
	"""Pin the preset output against a checked-in fixture.

	Catches drift from the *declared baseline* — if someone changes the preset,
	this fails instead of silently shipping a different layout. The snapshot is
	the generator's own contract, not the live default.levity.
	"""
	assert SNAPSHOT.exists(), f"missing snapshot fixture: {SNAPSHOT}"
	generated = _emit()
	snapshot = yaml.safe_load(SNAPSHOT.read_text())
	assert generated == snapshot
