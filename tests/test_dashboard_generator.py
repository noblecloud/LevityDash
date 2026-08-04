"""Tests for scripts/dashboard_generator.py — in-repo .levity generator.

Covers: valid YAML emission, the panel-size-sum trap warning, and the dead-key
refusal. These pin the "traps doc" rules (docs/tasks/dashboard-traps.md) in code
so a regression in the generator surfaces immediately.
"""
import importlib.util
import sys
from pathlib import Path

import pytest
import yaml

SPEC = Path(__file__).resolve().parents[1] / "scripts" / "dashboard_generator.py"


def _load_module():
	# scripts/ is not a package; load it by path
	spec = importlib.util.spec_from_file_location("dashboard_generator", SPEC)
	mod = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(mod)
	return mod


dg = _load_module()


def test_preset_emits_valid_yaml(tmp_path):
	out = tmp_path / "out.levity"
	rc = dg.main(["--preset", "default_norfolk", "--out", str(out)])
	assert rc == 0
	data = yaml.safe_load(out.read_text())
	assert isinstance(data, list) and len(data) == 1
	# main stack -> bottom band -> 3 panels + 1 graph
	bands = data[0]["items"][0]["items"]
	assert len(bands) == 4


def test_dead_key_is_refused_and_warns(capsys):
	result = dg.realtime_item("light.irradiance")
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
