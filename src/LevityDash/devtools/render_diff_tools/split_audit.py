#!/usr/bin/env python
"""Audit the meter split: is every moved member byte-identical to its original?

Job B of `docs/tasks/meter-m2b-remaining.md`. For each step (a commit that moved
members out of `Gauge.py`) this extracts the named definitions from the source
file at the commit *before* the move and from the target module at HEAD, and
compares the text (indentation normalised, because a member nested in the Gauge
class body gains/loses one tab when it moves to module level).

    python src/LevityDash/devtools/render_diff_tools/split_audit.py            # every step
    python src/LevityDash/devtools/render_diff_tools/split_audit.py f21b6a2    # one step

Read-only: it only runs `git show`. Nothing is written.
"""
import ast
import difflib
import subprocess
import sys
import textwrap
from pathlib import Path

REPO = subprocess.run(['git', 'rev-parse', '--show-toplevel'], capture_output=True, text=True).stdout.strip()
B = 'src/LevityDash/lib/ui/frontends/PySide/Modules/Displays/'
GAUGE = B + 'Gauge.py'


def git(*a):
    return subprocess.run(['git', '-C', REPO] + list(a), capture_output=True, text=True).stdout


def defs(src, cls):
    """Definition source text, keyed by member name, directly under a class body or at module level."""
    tree = ast.parse(src)
    body = tree.body
    if cls:
        node = next((n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == cls), None)
        if node is None:
            return {}
        body = node.body
    out = {}
    for stmt in body:
        key = getattr(stmt, 'name', None)
        if key is None and isinstance(stmt, ast.Assign):
            for t in stmt.targets:
                if isinstance(t, ast.Name):
                    out.setdefault(t.id, []).append(ast.get_source_segment(src, stmt))
        elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            out.setdefault(stmt.target.id, []).append(ast.get_source_segment(src, stmt))
        elif key is not None:
            out.setdefault(key, []).append(ast.get_source_segment(src, stmt))
    return out


def norm(texts):
    """Dedent a member so a nested->module move is not read as a change.

    `get_source_segment` strips the first line's indent but not the rest, so
    dedent against the minimum indent of the remaining lines.
    """
    out = []
    for text in texts:
        lines = text.split('\n')
        rest = [ln for ln in lines[1:] if ln.strip()]
        if rest:
            indent = min(len(ln) - len(ln.lstrip('\t')) for ln in rest)
            lines = [lines[0]] + [(ln[indent:] if ln.strip() else ln) for ln in lines[1:]]
        out.append('\n'.join(lines))
    return out


#: commit, target path (under Displays/), source class (None=module), target class, names
STEPS = [
    ('f21b6a2', 'meter/scale.py', None, None,
     ['filter_factors', '_isWholeSteps', 'formatDuration', 'shortestDelta', 'CLOCK_HANDS',
      'clockTurn', 'parseClockTime', 'decode_measurement']),
    ('26a79e3', 'meter/scale.py', None, None, ['Numeric', 'GaugeValue']),
    ('26a79e3', 'meter/elements.py', None, None,
     ['GaugeItem', 'StatefulGaugeItem', 'GaugePathItem', 'StatefulGaugePathItem']),
    ('2b7e68b', 'meter/elements.py', None, None,
     ['Graduations', 'Tick', 'SubTick', 'TickSurface', 'GaugeTickText', 'GaugeTickTextGroup']),
    ('1291bc6', 'meter/elements.py', None, None, ['Needle', 'Arrow', 'GaugeMarker']),
    ('fae5d57', 'meter/elements.py', None, None, ['GaugeZones', 'GaugeFill', '_FillEnd']),
    ('c34db29', 'meter/elements.py', None, None,
     ['GaugeCaption', 'GaugeText', 'GaugeLabel', 'GaugeValueLabel', 'GaugeUnit',
      '_decodeOffset', '_shiftByOffset', '_UNIT_UNDER_VALUE']),
    ('14ac71f', 'meter/meter.py', 'Gauge', None, ['GaugeRange']),
    ('b76cac9', 'meter/meter.py', 'Gauge', 'Meter',
     ['_buildLabel', '_captionItem', '_captionItems', '_clearCaption', '_decodeCaption',
      '_setCaption', '_subItem', '_syncCaptions', '_syncUnitUnderValue', '_unit',
      '_valueAnchor', 'caption', 'subLabel', 'unitLabel', 'valueLabel']),
    ('a3f1291', 'meter/meter.py', 'Gauge', 'Meter',
     ['_value', '_valueClass', 'range', 'updateSlot', 'value', 'valueChanged', 'valueClass',
      'value_scale']),
    ('80fcfe2', 'meter/meter.py', 'Gauge', 'Meter',
     ['_ANCHORS', '_anchor', '_captionSpec', '_center_offset', '_dialRect', '_s_inset',
      '_sideStripWidth', '_sideValueRect', '_subSpec', '_update_shape', '_valueSide',
      'alignment', 'anchor', 'baseWidth', 'center', 'center_offset', 'defaultColor',
      'displayType', 'inset', 'insetPx', 'parentResized', 'pen', 'rebuild', 'releaseSources',
      'scene_center', 'setRect', 'type', 'update_center_offset']),
    ('210b3d9', 'meter/meter.py', 'Gauge', 'Meter',
     ['_clearFill', '_clearMarkers', '_clearZones', '_fillItems', '_zoneItems', 'fill',
      'majorDivisions', 'markers', 'microDivisions', 'minorDivisions', 'needle', 'zones']),
    ('210b3d9', 'meter/meter.py', None, None, ['_markerText']),
]


def main(only=None):
    head = git('rev-parse', 'HEAD').strip()
    print(f'HEAD = {head}')
    verdicts = {}
    for commit, tpath, src_cls, tgt_cls, names in STEPS:
        if only and commit != only:
            continue
        if commit not in verdicts:
            verdicts[commit] = []
        old = defs(git('show', f'{commit}^:{GAUGE}'), src_cls)
        new = defs(git('show', f'{head}:{B}{tpath}'), tgt_cls)
        print(f'\n== {commit}  Gauge -> {tpath} ({tgt_cls or "module"}) ==')
        for name in names:
            a, b = norm(old.get(name) or []), norm(new.get(name) or [])
            if not old.get(name):
                verdict = 'NOT-IN-SOURCE'
            elif not new.get(name):
                verdict = 'MISSING-AT-HEAD'
            elif a == b:
                verdict = 'identical'
            else:
                verdict = 'DIFFERS'
                for x, y in zip(a, b):
                    for line in list(difflib.unified_diff(x.splitlines(), y.splitlines(), n=0, lineterm=''))[2:]:
                        print('    ' + line)
            verdicts[commit].append((name, verdict))
            print(f'  {name:<24} {verdict}')
    print('\n== summary ==')
    for commit, rows in verdicts.items():
        same = sum(1 for _, v in rows if v == 'identical')
        print(f'  {commit}: {same}/{len(rows)} identical')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
