"""Rebuild the key tables in docs/config/dashboard/reference.md from the code.

Every `@StateProperty` on a dashboard class is a key a .levity file can set. This reads them
with `ast` (no Qt needed) and rewrites the text between the GENERATED markers in the reference.

    python3 docs/_scripts/gen_reference.py          # rewrite
    python3 docs/_scripts/gen_reference.py --check  # exit 1 if the doc is stale
"""
import ast
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
LIB = ROOT / 'src' / 'LevityDash' / 'lib'
DOC = ROOT / 'docs' / 'config' / 'dashboard' / 'reference.md'

# marker name -> [(class, heading)]
SECTIONS = {
	'item': [('Panel', 'Every item (`type: group`)'), ('Border', '`border:`'), ('PanelBeam', '`beam:`'), ('GlowMixin', '`glow:` (anything that glows)'),
		('ColorMixin', 'Colour'), ('ColorGradientMixin', 'Colour with a gradient')],
	'containers': [('CentralPanel', 'The dashboard root'), ('Stack', '`type: stack`'), ('StackedItem', 'On an item inside a stack'),
		('DividerProperties', '`dividers:`'), ('ValueStack', '`type: value-stack`'), ('GridStack', '`type: grid`'), ('SplitPanel', '`type: split`'),
		('Switch', '`type: switch`'), ('Band', '`type: band`'), ('TitledPanel', '`type: titled-group`')],
	'text': [('Label', '`type: label` / `type: text`'), ('TitleLabel', 'A title label'), ('ClockComponent', 'A clock cell')],
	'realtime': [('Realtime', '`type: realtime` (and `.text`, `.gauge`, `.bar`)'), ('Connection', '`connection:`'),
		('MeasurementDisplayProperties', '`display:` on a text reading'), ('DisplayLabel', '`display:` value and unit labels'),
		('TitleValueSplitter', '`title:` (the title and its splitter)')],
	'gauge': [('Meter', '`display:` of every dial and bar'), ('Gauge', '`display:` of `realtime.gauge`'), ('GaugeRange', '`range:`'),
		('GaugeArc', '`arc:`'), ('Needle', '`needle:`'), ('Graduations', '`major:` `minor:` `micro:` (ticks)'),
		('GaugeTickTextGroup', 'Tick labels (`labels:` on a tick set)'), ('GaugeValueLabel', '`value-label:` on a dial'), ('GaugeUnit', '`unit-label:` on a dial')],
	'bar': [('Bar', '`display:` of `realtime.bar` (also takes the Meter keys above)')],
	'graph': [('GraphPanel', '`type: graph`'), ('MiniGraph', '`type: mini-graph`'), ('Figure', 'A figure'), ('GraphItemData', 'A graph item'),
		('Plot', 'Every plot'), ('LinePlot', '`type: line`'), ('FilledPlot', 'Filled plots'), ('BasedPlot', 'Plots with a base'), ('BarPlot', '`type: bar`'),
		('BandPlot', '`type: band`'), ('ViolinPlot', '`type: violin`'), ('DayAnnotations', '`annotations:`'), ('TimeMarkers', '`lines:`'),
		('HourLabels', '`hourLabels:`'), ('PlotLabels', 'Plot labels'), ('CurrentTimeIndicator', '`indicator:`'), ('AnnotationLabels', 'Any annotation labels')],
	'other': [('Moon', '`type: moon`'), ('Polar', '`type: polar`')],
}


def collect():
	out = {}
	for p in sorted(LIB.rglob('*.py')):
		try:
			tree = ast.parse(p.read_text())
		except (SyntaxError, UnicodeDecodeError):
			continue
		for cls in (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)):
			rows = []
			for f in cls.body:
				if not isinstance(f, ast.FunctionDef):
					continue
				for d in f.decorator_list:
					if isinstance(d, ast.Call) and getattr(d.func, 'id', getattr(d.func, 'attr', '')) == 'StateProperty':
						kw = {k.arg: k.value for k in d.keywords}
						key = ast.literal_eval(kw['key']) if 'key' in kw and isinstance(kw['key'], ast.Constant) else f.name
						default = ast.unparse(kw['default']) if 'default' in kw else ''
						doc = ' '.join((ast.get_docstring(f) or '').split())
						rows.append((key, default, doc))
			if rows and cls.name not in out:
				tag = next((ast.literal_eval(k.value) for k in cls.keywords if k.arg == 'tag' and isinstance(k.value, ast.Constant) and isinstance(k.value.value, str)), None)
				out[cls.name] = (tag, rows)
	return out


def cell(s):
	return s.replace('|', '\\|').replace('\n', ' ')


def render(name, classes):
	lines = []
	for cls, heading in SECTIONS[name]:
		if cls not in classes:
			continue
		tag, rows = classes[cls]
		lines.append(f'#### {heading}')
		if tag and tag not in ('...',):
			lines.append(f'Tag: `{tag}`  ·  class `{cls}`')
		else:
			lines.append(f'Class `{cls}`')
		lines += ['', '| Key | Default | What it does |', '|---|---|---|']
		seen = set()
		for key, default, doc in rows:
			if key in seen:
				continue
			seen.add(key)
			d = default if len(default) <= 38 else default[:35] + '...'
			lines.append(f'| `{key}` | {("`" + cell(d) + "`") if d else ""} | {cell(doc)} |')
		lines.append('')
	return '\n'.join(lines)


def main():
	classes = collect()
	text = DOC.read_text()
	new = text
	for name in SECTIONS:
		pat = re.compile(rf'(<!-- GENERATED:{name} -->\n).*?(<!-- /GENERATED:{name} -->)', re.S)
		if not pat.search(new):
			sys.exit(f'marker {name} missing in {DOC}')
		new = pat.sub(lambda m: m.group(1) + render(name, classes) + '\n' + m.group(2), new)
	if '--check' in sys.argv:
		sys.exit(0 if new == text else 1)
	DOC.write_text(new)


if __name__ == '__main__':
	main()
