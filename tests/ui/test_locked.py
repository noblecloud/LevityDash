"""Locked (display-only) mode: no edit handles, no drag/select/focus, and the dashboard still draws."""
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

from LevityDash.lib.ui.locked import resolveLocked

ROOT = Path(__file__).resolve().parents[2]


def test_resolution_order():
	assert resolveLocked([], {}, None) is False
	assert resolveLocked([], {}, True) is True
	assert resolveLocked([], {'LEVITY_LOCKED': '1'}, False) is True
	assert resolveLocked([], {'LEVITY_LOCKED': '0'}, True) is False
	assert resolveLocked(['--locked'], {'LEVITY_LOCKED': '0'}, False) is True
	assert resolveLocked(['--unlocked'], {'LEVITY_LOCKED': '1'}, True) is False


# A locked app is a different process: the mode is baked into items as they are built, and the session
# dashboard fixture was built unlocked.
_PROBE = textwrap.dedent('''
	import json, os, sys
	os.environ['QT_QPA_PLATFORM'] = 'offscreen'
	sys.path.insert(0, %(src)r)
	from LevityDash.devtools._boot import boot, shutdown
	from PySide6.QtWidgets import QGraphicsItem
	app, d = boot(seed=%(seed)r, levity=%(levity)r, size=(1680, 1000), settle=3.0)
	from LevityDash.lib.ui.locked import isLocked
	from LevityDash.lib.ui.frontends.PySide.Modules.Handles import Handle, HandleGroup
	from LevityDash.lib.ui.frontends.PySide.Modules.Handles.Splitters import Splitter
	from LevityDash.lib.ui.frontends.PySide.Modules.Panel import Panel
	items = d.scene.items()
	flags = QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable | QGraphicsItem.ItemIsFocusable
	panels = [i for i in items if isinstance(i, Panel)]
	for p in panels:
		p.setMovable(True)
	print('RESULT' + json.dumps(dict(
		locked=isLocked(),
		items=len(items),
		handles=sum(1 for i in items if isinstance(i, (Handle, HandleGroup)) and not isinstance(i, Splitter)),
		panels=len(panels),
		editable=sum(1 for p in panels if p.flags() & flags),
		hovering=sum(1 for p in panels if p.acceptHoverEvents()),
		dropping=sum(1 for p in panels if p.acceptDrops()),
	)))
	shutdown(d)
''')


def _probe(locked: bool) -> dict:
	env = dict(os.environ, LEVITY_LOCKED='1' if locked else '0', QT_QPA_PLATFORM='offscreen')
	code = _PROBE % dict(
		src=str(ROOT / 'src'), seed=str(ROOT / 'tests/resources/config-seed'),
		levity=str(ROOT / 'docs/design-references/showcase/default.levity') if (ROOT / 'docs/design-references/showcase/default.levity').exists() else str(ROOT / 'docs/tasks/lambda-cross-section.levity'),
	)
	out = subprocess.run([sys.executable, '-I', '-c', code], env=env, capture_output=True, text=True, timeout=300, cwd=ROOT)
	line = next((l for l in out.stdout.splitlines() if l.startswith('RESULT')), None)
	assert line, out.stdout[-2000:] + out.stderr[-2000:]
	return json.loads(line[len('RESULT'):])


def test_locked_dashboard_has_no_edit_machinery():
	free, locked = _probe(False), _probe(True)
	assert free['locked'] is False and locked['locked'] is True
	assert free['handles'] > 0
	assert locked['handles'] == 0
	assert locked['items'] < free['items']
	assert locked['panels'] == free['panels']
	assert locked['editable'] == 0  # not even when asked (`movable: true` in a file)
	# A graph keeps its hover tooltip; everything else stops listening.
	assert locked['hovering'] < free['hovering'] * 0.05
	assert locked['dropping'] == 0
