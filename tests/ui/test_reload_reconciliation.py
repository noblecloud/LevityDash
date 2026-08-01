"""Regression tests for the itemLoader reload orphan bugs.

`CentralPanel._load` deliberately skips `clear()` on a same-file reload, so
`Panel.items`'s setter (`itemLoader`, PySide/utils.py) has to reconcile the
incoming `.levity` state against the *live* scene rather than rebuild it.
Two independent defects made that untrustworthy:

- **The orphan (defect A).** Every loader's closest-match fallback arm -
  reached whenever a change is large enough that nothing hits an exact-match
  tier - claimed a panel (exempting it from teardown) without ever assigning
  `panel.state = item`. The panel survived on screen showing its *old*
  configuration while the new configuration was silently dropped.
- **The stranded type (defect C).** Each loader tore down its own leftovers
  from a *local copy* of the candidate list, so a type entirely absent from
  the new file was never visited by any loader and its panels were never torn
  down at all.

Both are fixed by having every loader claim out of a *shared* candidate list
(`_claim`) and moving teardown to `itemLoader`, which deletes whatever no
loader claimed - "vanished type" and "genuinely unmatched item" become the
same case.

Sandboxed as a bare Panel parented directly onto the booted dashboard's root
(`dashboard.scene.base`), rather than mutating the seeded `default.levity`'s
own content - keeps this independent of that file's exact structure.
"""
from LevityDash.lib.ui.frontends.PySide.Modules import EditableLabel, Panel


def _childNames(panel):
	return {c.stateName for c in panel.childPanels}


def test_reload_tears_down_a_type_that_vanishes_from_the_file(dashboard):
	sandbox = Panel(parent=dashboard.scene.base, geometry={'x': '0%', 'y': '0%', 'width': '10%', 'height': '10%'})

	sandbox.state = {'items': [
		{'type': 'group', 'name': 'alpha', 'geometry': {'x': '0%', 'y': '0%', 'width': '50%', 'height': '50%'}},
		{'type': 'clock', 'name': 'clk', 'geometry': {'x': '50%', 'y': '0%', 'width': '50%', 'height': '50%'}},
	]}
	dashboard.app.processEvents()
	assert {'alpha', 'clk'} <= _childNames(sandbox)
	stale_clock = next(c for c in sandbox.childPanels if c.stateName == 'clk')

	# reload: the clock type is entirely absent from the new file
	sandbox.state = {'items': [
		{'type': 'group', 'name': 'alpha', 'geometry': {'x': '0%', 'y': '0%', 'width': '100%', 'height': '100%'}},
	]}
	dashboard.app.processEvents()

	assert 'clk' not in _childNames(sandbox), "the vanished type's panel was left behind (the orphan bug)"
	assert stale_clock.scene() is None, "the orphaned panel is still attached to the scene, not actually deleted"

	sandbox.scene().removeItem(sandbox)


def test_reload_applies_new_state_through_the_closest_match_fallback(dashboard):
	"""Two candidates, neither an exact match, forces the closest-match
	fallback arm - the one that used to claim a panel and never update it."""
	sandbox = Panel(parent=dashboard.scene.base, geometry={'x': '0%', 'y': '0%', 'width': '10%', 'height': '10%'})

	sandbox.state = {'items': [
		{'type': 'label', 'text': 'alpha-before', 'geometry': {'x': '0%', 'y': '0%', 'width': '50%', 'height': '100%'}},
		{'type': 'label', 'text': 'beta-before', 'geometry': {'x': '50%', 'y': '0%', 'width': '50%', 'height': '100%'}},
	]}
	dashboard.app.processEvents()
	before = sorted(c.text for c in sandbox.childPanels if isinstance(c, EditableLabel))
	assert before == ['alpha-before', 'beta-before']

	# Different text AND different geometry for both labels, so neither the
	# (text, geometry), (geometry), nor (text) exact tiers can match - with 2
	# remaining candidates this must land on the closest-match fallback.
	sandbox.state = {'items': [
		{'type': 'label', 'text': 'alpha-after', 'geometry': {'x': '10%', 'y': '10%', 'width': '40%', 'height': '80%'}},
		{'type': 'label', 'text': 'beta-after', 'geometry': {'x': '55%', 'y': '10%', 'width': '40%', 'height': '80%'}},
	]}
	dashboard.app.processEvents()

	after_labels = [c for c in sandbox.childPanels if isinstance(c, EditableLabel)]
	assert len(after_labels) == 2, f'expected exactly 2 labels after reload, found {len(after_labels)} (orphans or dupes)'
	after = sorted(l.text for l in after_labels)
	assert after == ['alpha-after', 'beta-after'], (
		f'reload left stale text {after!r} - a panel was matched by the fallback but never updated (defect A)'
	)

	sandbox.scene().removeItem(sandbox)


def test_reload_of_an_unchanged_file_is_a_no_op(dashboard):
	"""Guards against the fix over-correcting into deleting/rebuilding
	everything on every reload, which the shared-candidate-list rewrite could
	plausibly have introduced."""
	sandbox = Panel(parent=dashboard.scene.base, geometry={'x': '0%', 'y': '0%', 'width': '10%', 'height': '10%'})
	state = {'items': [
		{'type': 'group', 'name': 'solo', 'geometry': {'x': '0%', 'y': '0%', 'width': '100%', 'height': '100%'}},
	]}

	sandbox.state = state
	dashboard.app.processEvents()
	original = next(c for c in sandbox.childPanels if c.stateName == 'solo')

	sandbox.state = state
	dashboard.app.processEvents()

	assert len(sandbox.childPanels) == 1, 'an unchanged reload should not create or destroy anything'
	assert sandbox.childPanels[0] is original, 'an unchanged reload rebuilt the panel instead of reusing it'

	sandbox.scene().removeItem(sandbox)
