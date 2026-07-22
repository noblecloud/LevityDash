"""Proves `[Backend] mode = loopback` boots cleanly end-to-end (Phase 4.1's
actual milestone: "identical rendering in mode=loopback... before any real
process/network exists").

Runs in a fresh subprocess rather than against the shared `dashboard`
fixture: PluginValueDirectory is a process-wide singleton (`__new__` returns
the same instance on every construction within a process, but `__init__`
still re-runs on it every time per Python's data model), so instantiating a
second one inside the same pytest session - which already booted one in the
default `live` mode via `dashboard` - would re-wire the live singleton's
plugin connections out from under other tests. A subprocess sidesteps that
entirely; it's slower than an in-process test but the only safe way to
exercise this without adding cross-test contamination risk.
"""
import json
import subprocess
import sys
import textwrap

BOOT_SCRIPT = textwrap.dedent("""
	from LevityDash import LevityDashboard

	LevityDashboard.init()
	LevityDashboard.plugins.load_all()

	dispatcher = LevityDashboard.dispatcher
	from LevityDash.lib.wire.bridge import LoopbackBridge

	result = {
		"bridge_is_loopback_bridge": isinstance(dispatcher.bridge, LoopbackBridge),
		"plugin_count": len(list(dispatcher.plugins)),
	}
	print("RESULT_JSON:" + __import__("json").dumps(result))
""")


def _run_boot_script(mode: str) -> dict:
	import os

	env = {
		**os.environ,
		"QT_QPA_PLATFORM": "offscreen",
		"LEVITYDASH_CONFIG_DEBUG": "1",
		"LEVITYDASH_BACKEND_MODE": mode,
	}
	proc = subprocess.run(
		[sys.executable, "-c", BOOT_SCRIPT],
		capture_output=True,
		text=True,
		timeout=60,
		env=env,
	)
	assert proc.returncode == 0, f"{mode} boot crashed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"

	line = next((l for l in proc.stdout.splitlines() if l.startswith("RESULT_JSON:")), None)
	assert line is not None, f"boot script never printed its result - stdout:\n{proc.stdout}"
	return json.loads(line[len("RESULT_JSON:"):])


def test_loopback_mode_boots_and_wires_bridge():
	# PluginValueDirectory is constructed as a side effect of the first
	# `import LevityDash` (see dispatcher.py's comment on the mode read),
	# before any in-process code could set config - LEVITYDASH_BACKEND_MODE
	# is the only thing that can actually reach it, so this drives the real
	# boot path via env var, in an isolated subprocess (PluginValueDirectory
	# is a process-wide singleton; a second in-process construction would
	# re-wire the `dashboard` fixture's already-live singleton out from
	# under other tests in this session).
	result = _run_boot_script("loopback")
	assert result["bridge_is_loopback_bridge"] is True
	assert result["plugin_count"] > 0


def test_live_mode_does_not_wire_a_bridge():
	result = _run_boot_script("live")
	assert result["bridge_is_loopback_bridge"] is False
