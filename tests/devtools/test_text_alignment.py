"""Text lands where its alignment says, inside the box it was given.

`devtools/text_alignment.py` boots an empty dashboard on the Fixture scenario, builds every case of
`_textalign_cases.py`, and measures each text by painting the real item and finding the ink. This module runs it
once (a few minutes of Qt, in a subprocess because the dashboard singleton cannot be booted twice) and asserts on
the probes with the rules in `_textalign_rules.py`.

A failure names the case and prints the probe. To see it, set `LEVITY_TEXTALIGN_OUT=some/dir` and run again: one
overlay PNG per case is written there, with the box (blue), limit rect (green), fit rect (amber dashed), ink (red),
baseline (pink) and font metric lines (grey) drawn over the real glyphs.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from LevityDash.devtools import _textalign_cases
from LevityDash.devtools._textalign_cases import ALIGNMENTS, catalogue
from LevityDash.devtools._textalign_rules import Probe, deviations, inkAgrees, isEmpty, left, misplaced, overflow, right, top

RUNNER = Path(_textalign_cases.__file__).with_name('text_alignment.py')
CASES = {case.id: case for case in catalogue()}


@pytest.fixture(scope='module')
def sweep(tmp_path_factory):
	"""Run the whole catalogue once: `{case id: result}` with `Probe`s decoded."""
	out = os.environ.get('LEVITY_TEXTALIGN_OUT')
	target = tmp_path_factory.mktemp('textalign') / 'probes.json'
	command = [sys.executable, str(RUNNER), '--json', str(target)]
	if out:
		command += ['--out', out]
	done = subprocess.run(command, capture_output=True, text=True, timeout=1500)
	assert target.exists(), f'the runner wrote nothing:\n{done.stdout[-2000:]}\n{done.stderr[-2000:]}'
	results = {}
	for entry in json.loads(target.read_text()):
		entry['probes'] = [Probe.fromDict(p) for p in entry['probes']]
		results[entry['id']] = entry
	return results


def probes(sweep, prefix: str, roles=None):
	"""`(case id, probe)` for every probe of the cases starting with `prefix`."""
	return [
		(cid, probe) for cid, entry in sweep.items() if cid.startswith(prefix)
		for probe in entry['probes'] if roles is None or probe.role in roles
	]


def of(sweep, cid: str, roles=None):
	"""The probes of exactly one case."""
	return [p for p in sweep[cid]['probes'] if roles is None or p.role in roles]


def describe(found) -> str:
	return '\n'.join(f'  {probe}' for probe in found)


def test_every_case_drew_text(sweep):
	missing = [cid for cid in CASES if cid not in sweep or not sweep[cid]['probes']]
	assert not missing, f'no text was measured for: {missing}'
	blank = [str(p) for cid in sweep for p in sweep[cid]['probes'] if isEmpty(p.ink)]
	assert not blank, 'a text painted nothing:\n  ' + '\n  '.join(blank)


def test_the_measure_agrees_with_the_outlines(sweep):
	"""The painted ink and the glyph outline are one box. If not, the harness is measuring the wrong thing."""
	bad = [p for _, p in probes(sweep, '') if not inkAgrees(p, tolerance=1.0)]
	assert not bad, 'ink and outline disagree:\n' + describe(bad)


# --------------------------------------------------------------------------- #
# where the alignment puts text
# --------------------------------------------------------------------------- #
PLAIN = ('align/', 'font/', 'size/', 'margins/', 'text-height/', 'nested/', 'flex/', 'grid/')


@pytest.mark.parametrize('prefix', PLAIN)
def test_text_sits_where_its_alignment_says(sweep, prefix):
	"""Left/Right put the ink edge on the limit edge, Center the ink centre; Top/Bottom/Center put the fit rect on
	the limit's top, bottom or middle."""
	found = probes(sweep, prefix)
	assert found
	bad = [(p, misplaced(p)) for _, p in found if misplaced(p)]
	assert not bad, 'misplaced:\n' + '\n'.join(f'  {p}\n    off by {off}' for p, off in bad)


@pytest.mark.parametrize('prefix', PLAIN + ('realtime/', 'group/', 'statrow/', 'tiles/'))
def test_ink_stays_inside_the_box_it_was_given(sweep, prefix):
	"""The box less its margins (and `text-height`) is where text may go. It used to hang out below for `Top` and
	above for `Bottom`, by as much as a third of the box, because the alignment lined up font metrics (the ascent
	line) that are not the edges of what the fit measured."""
	bad = [(p, overflow(p)) for _, p in probes(sweep, prefix) if overflow(p)]
	assert not bad, 'ink outside the limit rect:\n' + '\n'.join(f'  {p}\n    by {off}' for p, off in bad)


@pytest.mark.parametrize('prefix', ('realtime/',))
def test_value_text_sits_where_its_alignment_says(sweep, prefix):
	bad = [(p, misplaced(p)) for _, p in probes(sweep, prefix, roles={'value'}) if misplaced(p)]
	assert not bad, 'misplaced:\n' + '\n'.join(f'  {p}\n    off by {off}' for p, off in bad)


def test_no_text_leaves_the_panel_that_holds_it(sweep):
	"""However deep the layout (stat rows, tiles with graphs, value stacks), the ink stays inside the panel the
	case built, which is the box a person sees the text overflow."""
	slack = 1.5
	bad = []
	for cid, entry in sweep.items():
		for probe in entry['probes']:
			x, y, w, h = probe.ink
			inside = any(
				x >= px - slack and y >= py - slack and x + w <= px + pw + slack and y + h <= py + ph + slack
				for px, py, pw, ph in entry['panels']
			)
			if not inside and not isEmpty(probe.ink):
				bad.append(probe)
	assert not bad, 'text outside its panel:\n' + describe(bad)


# --------------------------------------------------------------------------- #
# alignment must change something
# --------------------------------------------------------------------------- #
def test_horizontal_alignment_moves_the_ink(sweep):
	"""In a box wider than its text, Left, Center and Right are three different places."""
	for shape in ('wide',):
		for text in ('Hi',):
			lefts = {}
			for alignment in ('CenterLeft', 'Center', 'CenterRight'):
				(probe,) = [p for p in of(sweep, f'align/{shape}/{alignment}') if p.text == text]
				lefts[alignment] = left(probe.ink)
			assert lefts['CenterLeft'] + 100 < lefts['Center'] < lefts['CenterRight'] - 100, lefts


def test_vertical_alignment_moves_the_ink(sweep):
	"""In a box taller than its text, Top, Center and Bottom are three different places."""
	for text in ('Hi',):
		tops = {}
		for alignment in ('TopCenter', 'Center', 'BottomCenter'):
			(probe,) = [p for p in of(sweep, f'align/tall/{alignment}') if p.text == text]
			tops[alignment] = top(probe.ink)
		assert tops['TopCenter'] + 10 < tops['Center'] < tops['BottomCenter'] - 10, tops


@pytest.mark.parametrize('spelling', ('valueLabel', 'item'))
@pytest.mark.parametrize('key', ('temperature', 'wind', 'humidity'))
def test_a_value_display_takes_its_alignment(sweep, key, spelling):
	"""`alignment:` on a `realtime.text` item moves the value, like `display: {valueLabel: {alignment: ...}}` does.
	Nothing read the item-level key, so it had no effect at all."""
	places = {}
	for alignment in ('CenterLeft', 'Center', 'CenterRight'):
		(probe,) = of(sweep, f'realtime/{key}/{spelling}/hidden/{alignment}', roles={'value'})
		places[alignment] = (left(probe.ink), right(probe.ink), probe.limit)
	l, c, r = places['CenterLeft'], places['Center'], places['CenterRight']
	assert l[0] < c[0] < r[0], places
	assert abs(l[0] - l[2][0]) <= 1.5, f'left value is not on the left edge: {places}'
	assert abs(r[1] - (r[2][0] + r[2][2])) <= 1.5, f'right value is not on the right edge: {places}'


def test_a_baseline_does_not_depend_on_the_string(sweep):
	"""A descender must not move the text (the hour labels sat at two heights): `Hamburg 88` and `Hi` share a
	baseline for every alignment and shape."""
	# only in the wide box, where both strings are height-limited and so fit to one size; in the others the two fit
	# to their own widths, and their baselines legitimately differ
	for alignment in ALIGNMENTS:
		found = of(sweep, f'align/wide/{alignment}')
		assert len(found) == 2
		spread = abs(found[0].baseline - found[1].baseline)
		assert spread <= 1.0, f'{alignment}: baselines {found[0].baseline} and {found[1].baseline}'


# --------------------------------------------------------------------------- #
# relative geometry, margins, layouts
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize('prefix', ('nested/', 'flex/', 'grid/'))
def test_boxes_land_where_the_nominal_arithmetic_puts_them(sweep, prefix):
	"""Percent geometry three levels down, flex growth and grid lines: each label's box is the cell computed by hand."""
	checked = 0
	for cid, entry in sweep.items():
		if not cid.startswith(prefix):
			continue
		for probe in entry['probes']:
			want = entry['facts']['boxes'].get(probe.text)
			if want is None:
				continue
			checked += 1
			assert probe.box == pytest.approx(tuple(want), abs=0.75), f'{cid}: {probe.text!r} box {probe.box}, expected {tuple(want)}'
	assert checked


def test_margins_shrink_the_limit_rect(sweep):
	whole = {(cid.split('/')[-1]): p.limit for cid, p in probes(sweep, 'margins/none/')}
	for name, edges in {'even-10px': (10, 10, 10, 10), 'uneven': (30, 2, 4, 20)}.items():
		for cid, probe in probes(sweep, f'margins/{name}/'):
			box = whole[cid.split('/')[-1]]
			l, t, r, b = edges
			assert probe.limit == pytest.approx((box[0] + l, box[1] + t, box[2] - l - r, box[3] - t - b), abs=0.75), cid


def test_text_height_is_a_band_centred_in_the_box(sweep):
	for cid, probe in probes(sweep, 'text-height/'):
		box = probe.box
		assert probe.limit[1] + probe.limit[3] / 2 == pytest.approx(box[1] + box[3] / 2, abs=0.75), cid
	heights = {cid.split('/')[1]: p.limit[3] for cid, p in probes(sweep, 'text-height/') if cid.endswith('Center')}
	assert heights['12px'] == pytest.approx(12, abs=0.75)
	assert heights['60px'] == pytest.approx(60, abs=0.75)
	assert heights['40%'] == pytest.approx(0.4 * 110, abs=0.75)


# --------------------------------------------------------------------------- #
# size groups
# --------------------------------------------------------------------------- #
def sizes(sweep, cid, roles):
	return [p.fontPixels for p in sweep[cid]['probes'] if p.role in roles]


def test_a_size_group_gives_labels_one_size_across_panels(sweep):
	"""Boxes of one height and different widths: ungrouped they fit to their own width, grouped (matchAll) they
	all take the smallest, across four separate panels."""
	ungrouped = sizes(sweep, 'group/labels-none', {'label'})
	grouped = sizes(sweep, 'group/labels-matchall', {'label'})
	assert max(ungrouped) / min(ungrouped) > 1.5, f'the control does not differ: {ungrouped}'
	assert max(grouped) / min(grouped) < 1.01, grouped
	assert grouped[0] == pytest.approx(min(ungrouped), rel=0.02), 'the group takes the tightest box'
	assert all(p.group for p in sweep['group/labels-matchall']['probes'])


def test_values_of_one_box_height_share_a_size_in_a_group(sweep):
	"""Temperature and humidity boxes are one height (one tier): grouped, one size."""
	by = {p.text: p.fontPixels for p in sweep['group/values-matchall']['probes'] if p.role == 'value'}
	assert by['98°'] == pytest.approx(by['31%'], rel=0.01), by


@pytest.mark.xfail(strict=True, reason=(
	'A value with a unit line has a shorter box (the unit takes about a fifth of it), so it lands in another '
	'height tier (size-groups.md: tiers are ~10 px buckets) and keeps its own size beside the unitless values '
	'around it, even in a global matchAll group. Wind next to Temperature shows it.'))
def test_values_with_and_without_a_unit_line_share_a_size_in_a_group(sweep):
	sized = [p.fontPixels for p in sweep['group/values-matchall']['probes'] if p.role == 'value']
	assert max(sized) / min(sized) < 1.02, sized
