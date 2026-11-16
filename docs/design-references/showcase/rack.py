"""Rack: the homelab showcase. Phosphor green on black, dot-matrix numerals over monospace comments."""
import math

from kit import *

GLOW = {'strength': 1.3, 'reach': 2.0, 'passes': 6}
FREEZE = '2026-03-12T21:30:00'
H = 'homelab'
NODES = [('pve-01', 62, 71, 58), ('pve-02', 34, 48, 51), ('pve-03', 88, 83, 67), ('pve-04', 17, 39, 46)]
POOLS = [('tank', 61.4, 96.0), ('fast', 3.1, 3.6), ('backup', 22.8, 48.0)]
DISKS = [38, 39, 41, 37, 44, 40, 52, 39]
SERVICES = [('jellyfin', 'OK', 42), ('hass', 'OK', 18), ('immich', 'OK', 65), ('paperless', 'SLOW', 840),
            ('gitea', 'OK', 23), ('vaultwarden', 'OK', 12), ('frigate', 'DOWN', 0)]


def data():
	d = Data('rack', 'A homelab on a weekday evening: one node working hard, one service slow, one down, a backup overdue.', 21.5)
	busy = lambda h: 0.25 + 0.55 * bell(h, 20.5, 2.6) + 0.25 * bell(h, 3, 1.2)
	for name, cpu, mem, temp in NODES:
		s = d.series(lambda h, day, t: cpu * (0.45 + 0.75 * busy(h)), noise=4, smooth=1, lo=2, hi=99, digits=0)
		d.add(f'{H}.node.cpu#{name}', 'int', s, value=cpu, title=f'{name} CPU')
		d.add(f'{H}.node.memory#{name}', 'int', value=mem, title=f'{name} memory')
		d.add(f'{H}.node.temperature#{name}', 'int', value=temp, title=f'{name} temperature')
	cpu = d.series(lambda h, day, t: 50 * (0.45 + 0.75 * busy(h)), noise=2.5, smooth=1, lo=3, hi=99, digits=0)
	d.add(f'{H}.cluster.cpu', 'int', cpu, value=50, title='Cluster CPU')
	d.add(f'{H}.cluster.memory', 'int', value=60, title='Cluster memory')
	d.add(f'{H}.cluster.load', 'int', value=11.4, title='Load')
	d.add(f'{H}.cluster.guests', 'int', value=41, title='Guests')
	down = d.series(lambda h, day, t: 30 + 520 * bell(h, 20.5, 2.2) + 140 * bell(h, 13, 3) + 610 * bell(h, 3, 0.7), noise=22, smooth=1, lo=2, digits=0)
	up = d.series(lambda h, day, t: 8 + 40 * bell(h, 20, 3) + 310 * bell(h, 3, 0.8), noise=5, smooth=1, lo=1, digits=0)
	d.add(f'{H}.wan.down', 'int', down, value=412, title='Download')
	d.add(f'{H}.wan.up', 'int', up, value=38, title='Upload')
	d.add(f'{H}.wan.latency', 'int', d.series(lambda h, day, t: 9 + 5 * bell(h, 20.5, 2), noise=0.8, smooth=1, lo=4), value=9.4, title='Latency')
	d.add(f'{H}.wan.clients', 'int', value=47, title='Clients')
	d.add(f'{H}.wan.loss', 'int', value=0.0, title='Loss')
	power = d.series(lambda h, day, t: 190 + 190 * busy(h), noise=6, smooth=1, digits=0)
	d.add(f'{H}.power.draw', 'int', power, value=342, title='Power draw')
	d.add(f'{H}.power.today', 'int', value=5.8, title='Energy today')
	d.add(f'{H}.ups.charge', 'int', value=100, title='UPS charge')
	d.add(f'{H}.ups.runtime', 'int', value=38, title='UPS runtime')
	d.add(f'{H}.ups.load', 'int', value=41, title='UPS load')
	for name, used, total in POOLS:
		d.add(f'{H}.pool.used#{name}', 'int', value=used, title=f'{name} used')
		d.add(f'{H}.pool.share#{name}', 'int', value=round(used / total * 100), title=f'{name} share')
	for i, temp in enumerate(DISKS):
		d.add(f'{H}.disk.temperature#bay{i + 1}', 'int', value=temp, title=f'Bay {i + 1}')
	for name, state, ms in SERVICES:
		base = max(ms, 8)
		s = d.series(lambda h, day, t: base * (0.7 + 0.5 * busy(h)), noise=base * 0.12, smooth=1, lo=1, digits=0)
		d.add(f'{H}.service.response#{name}', 'int', s, value=ms, title=f'{name} response')
	blocked = d.series(lambda h, day, t: 19 + 9 * bell(h, 21, 4), noise=1, smooth=1)
	d.add(f'{H}.dns.blocked', 'int', blocked, value=23.4, title='Blocked')
	d.add(f'{H}.dns.queries', 'int', value=48211, title='Queries today')
	d.add(f'{H}.backup.age', 'int', value=26, title='Hours since backup')
	return d


THEME = {
	'extends': 'default',
	'colors': {
		'background': '#030604', 'surface': '#08110b',
		'text': '#dcffe6', 'muted': '#77b78a', 'faint': '#467256', 'rule': '#16301f',
		'accent': '#3dff7a', 'good': '#3dff7a', 'warn': '#ffb000', 'bad': '#ff3b30', 'info': '#4de3ff', 'violet': '#b48cff',
		'series-1': '#3dff7a', 'series-2': '#4de3ff', 'series-3': '#ffb000', 'series-4': '#b48cff', 'series-5': '#ff3b30', 'series-6': '#dcffe6',
	},
	'fonts': {'display': 'Doto', 'body': 'JetBrains Mono', 'mono': 'JetBrains Mono'},
}

CAP = 1.5
ZONES = [{'to': 60, 'color': '$good', 'opacity': 0}, {'from': 60, 'to': 85, 'color': '$warn', 'opacity': 0}, {'from': 85, 'color': '$bad', 'opacity': 0}]


def note(s, geom, color='$faint', **kw):
	"""A caption written as a code comment."""
	kw.setdefault('format-hint', 'heading')
	return text(s, geom, font='$mono', weight='Regular', color=color, align='BottomLeft', group='global.note', **kw)


def dots(key, geom, color='$accent', weight='Black', group='global.dots', **kw):
	"""A number in the dot-matrix face."""
	return val(key, geom, color, font='$display', weight=weight, group=group, **kw)


def mono(key, geom, color='$text', group='global.mono', align='CenterRight', weight='Medium', **kw):
	return val(key, geom, color, font='$mono', weight=weight, group=group, align=align, **kw)


def label(s, geom, color='$muted', group='global.label', align='CenterLeft', weight='Regular', **kw):
	return text(s, geom, font='$mono', weight=weight, color=color, align=align, group=group, **kw)


def seg(key, geom, n=24, color='zone', zones=ZONES, lo=0, hi=100, **kw):
	fill = {'segments': n, 'gap': '22%', 'color': color, 'cap': 'flat'}
	return bar(key, geom, lo, hi, track={'weight': '100%', 'color': '$rule', 'cap': 'flat'}, fill=fill, **({'zones': zones} if color == 'zone' else {}), **kw)


def stat(caption, key, x, y, w, color='$text', h=4.6, **kw):
	return [note(caption, g(x, y, w, CAP)), dots(key, g(x, y + CAP + 0.5, w, h), color, weight='Black', group='global.stat', **kw)]


def board():
	B = []
	# ------------------------------------------------------------ header
	B += [
		text('RACK/01', g(2, 2, 24, 6.4), font='$display', weight='Black', color='$accent', align='CenterLeft', tracking=0.04, **{'format-hint': 'RACK/01'}),
		text('homelab · 4 nodes · 41 guests · up 212 days', g(27, 4.4, 42, 2.2), font='$mono', weight='Light', italic=True, color='$muted', align='CenterLeft'),
		{'type': 'clock', 'name': 'clock', 'geometry': g(70, 2, 28, 6.4), 'items': [
			{'format': '%Y-%m-%d', 'font': '$mono', 'weight': 'Light', 'color': '$muted', 'alignment': 'CenterRight', 'margins': 0,
			 'format-hint': '0000-00-00', 'geometry': g(0, 34, 52, 36)},
			{'format': '%H:%M', 'font': '$display', 'weight': 'Black', 'color': '$text', 'alignment': 'CenterRight', 'margins': 0, 'tracking': 0.04,
			 'format-hint': '00:00', 'geometry': g(56, 0, 44, 100)},
		]},
	]
	cards = {}
	px, py = 1.3, 1.8
	Y1, H1, Y2, H2 = 10.5, 42, 54.3, 43.7
	XA, WA, XB, WB, XC, WC = 2, 31, 34.2, 37, 72.4, 25.6

	# ------------------------------------------------------------ cluster
	x, w = XA + px, WA - 2 * px
	C = cards['cluster'] = [
		note('// cluster.cpu  %', g(x, Y1 + py, w, CAP), '$accent'),
		mini(f'{H}.cluster.cpu', g(x, Y1 + 5, 17, 15), color='$accent', hours=24, past=True, lo=0, hi=100, top='35%', opacity=0.7, fill=0.3, glow=GLOW),
		dots(f'{H}.cluster.cpu', g(x, Y1 + 4.4, 17, 15), '$accent', hint='00', group='global.hero'),
		*stat('load', f'{H}.cluster.load', x + 18.6, Y1 + 4.4, 9, '$text', precision=1, hint='00.0'),
		*stat('mem %', f'{H}.cluster.memory', x + 18.6, Y1 + 12.4, 9, '$info', hint='00.0'),
		note('node', g(x, Y1 + 21.4, 7, CAP)),
		note('cpu', g(x + 7.4, Y1 + 21.4, 6, CAP)),
		{**note('%', g(x + 18.6, Y1 + 21.4, 3, CAP)), 'alignment': 'BottomRight'},
		{**note('mem', g(x + 21.8, Y1 + 21.4, 3, CAP)), 'alignment': 'BottomRight'},
		{**note('°c', g(x + 25, Y1 + 21.4, 3.2, CAP)), 'alignment': 'BottomRight'},
	]
	for i, (name, cpu, mem, temp) in enumerate(NODES):
		y = Y1 + 24 + i * 4.3
		hot = '$bad' if cpu >= 85 else '$warn' if cpu >= 60 else '$text'
		C += [
			label(name, g(x, y, 7, 3)),
			seg(f'{H}.node.cpu#{name}', g(x + 7.4, y + 0.55, 11, 1.9), n=20),
			mono(f'{H}.node.cpu#{name}', g(x + 18.6, y, 3, 3), hot, hint='00'),
			mono(f'{H}.node.memory#{name}', g(x + 21.8, y, 3, 3), '$muted', hint='00'),
			mono(f'{H}.node.temperature#{name}', g(x + 25, y, 3.2, 3), '$bad' if temp >= 65 else '$muted', hint='00'),
		]

	# ------------------------------------------------------------ network
	x, w = XB + px, WB - 2 * px
	cards['wan'] = [
		note('// wan  mbps', g(x, Y1 + py, w, CAP), '$info'),
		text('↓', g(x, Y1 + 4.4, 3, 9), font='$mono', weight='Light', color='$info', align='Center'),
		dots(f'{H}.wan.down', g(x + 3, Y1 + 4.4, 14, 9), '$info', hint='000', group='global.wan'),
		text('↑', g(x + 18, Y1 + 4.4, 3, 9), font='$mono', weight='Light', color='$violet', align='Center'),
		dots(f'{H}.wan.up', g(x + 21, Y1 + 4.4, 13, 9), '$violet', hint='000', group='global.wan'),
		{'type': 'graph', 'name': 'throughput', 'geometry': g(x, Y1 + 14.4, w, 17.4),
		 'timeframe': {'hours': 24, 'offset': {'hours': -20}},
		 'annotations': {'dayLabels': {'enabled': False}, 'hourLabels': {'alignment': 'BottomCenter', 'spacingIntervals': '6', 'height': '9%'},
		                 'lines': {'weight': 0.3}},
		 'figures': [
			 {'figure': 'down', 'margins': {'top': '6%', 'bottom': '14%'}, 'min': 0, 'max': 700,
			  f'{H}.wan.down': {'plot': {'type': 'plot', 'color': '$info', 'weight': 0.7, 'glow': GLOW, 'fill': {'opacity': 0.35, 'fade': True}}}},
			 {'figure': 'up', 'margins': {'top': '6%', 'bottom': '14%'}, 'min': 0, 'max': 700,
			  f'{H}.wan.up': {'plot': {'type': 'plot', 'color': '$violet', 'weight': 0.5, 'fill': {'opacity': 0.3, 'fade': True}}}},
		 ]},
		*stat('clients', f'{H}.wan.clients', x, Y1 + 33.4, 8, '$text', hint='00'),
		*stat('ping ms', f'{H}.wan.latency', x + 9, Y1 + 33.4, 8, '$accent', precision=1, hint='0.0'),
		*stat('loss %', f'{H}.wan.loss', x + 18, Y1 + 33.4, 8, '$accent', precision=1, hint='0.0'),
		*stat('dns blocked %', f'{H}.dns.blocked', x + 26, Y1 + 33.4, 8.4, '$warn', precision=1, hint='00.0'),
	]

	# ------------------------------------------------------------ power
	x, w = XC + px, WC - 2 * px
	cards['power'] = [
		note('// power  w', g(x, Y1 + py, w, CAP), '$warn'),
		{'type': 'realtime.gauge', 'key': f'{H}.power.draw', 'title': False, 'geometry': g(x + 1.5, Y1 + 4.6, w - 3, 26),
		 'display': {
			 'radius': '94%', 'range': {'min': 0, 'max': 600},
			 'arc': {'start-angle': -120, 'end-angle': 120, 'weight': '2%', 'color': '$rule', 'cap': 'flat'},
			 'zones': [{'from': 0, 'to': 350, 'color': '$good', 'weight': '2%'}, {'from': 350, 'to': 480, 'color': '$warn', 'weight': '2%'},
			           {'from': 480, 'to': 600, 'color': '$bad', 'weight': '2%'}],
			 'major': {'interval': 100, 'length': '7%', 'width': '2px', 'color': '$muted', 'labels': {'position': 'inside', 'height': '9%', 'offset': '4%'}},
			 'minor': {'interval': 20, 'length': '3.5%', 'color': '$faint'}, 'micro': {'enabled': False},
			 'font': '$mono',
			 'needle': {'type': 'tapered', 'length': '74%', 'width': '4%', 'tail': '12%', 'hub': '7%', 'hub-hole': '45%', 'hub-color': '$surface',
			            'color': '$warn', 'glow': GLOW},
			 'value-label': {'visible': False}, 'unit-label': {'visible': False}}},
		dots(f'{H}.power.draw', g(x + 6.5, Y1 + 22.6, w - 13, 6.4), '$warn', hint='000', align='Center', group='global.pw'),
		note('ups', g(x, Y1 + 33.4, 5, CAP)),
		bar(f'{H}.ups.charge', g(x, Y1 + 35.6, 9.6, 4.2), 0, 100, color='$good', style='battery',
		    track={'weight': '100%', 'color': '$muted'}, fill={'segments': 5, 'gap': '14%'}),
		*stat('runtime min', f'{H}.ups.runtime', x + 11.4, Y1 + 33.4, 6, '$text', hint='00'),
		*stat('kwh today', f'{H}.power.today', x + 17.4, Y1 + 33.4, 5.6, '$text', precision=1, hint='0.0'),
	]

	# ------------------------------------------------------------ storage
	x, w = XA + px, WA - 2 * px
	S = cards['storage'] = [note('// zfs  tb used', g(x, Y2 + py, w, CAP), '$violet')]
	for i, (name, used, total) in enumerate(POOLS):
		y = Y2 + 4.8 + i * 6.6
		share = used / total * 100
		color = '$bad' if share >= 85 else '$warn' if share >= 60 else '$violet'
		S += [
			label(name, g(x, y, 7, 3)),
			dots(f'{H}.pool.used#{name}', g(x + 8, y - 0.6, 9, 4), color, weight='Black', precision=1, hint='00.0', align='CenterRight', group='global.pool'),
			label(f'/ {total:g}', g(x + 17.4, y, 6, 3), '$faint'),
			mono(f'{H}.pool.share#{name}', g(x + 23, y, 5.4, 3), color, hint='00%', fmt={'suffix': '%'}),
			seg(f'{H}.pool.share#{name}', g(x, y + 3.5, w, 1.3), n=48, color=color),
		]
	y = Y2 + 25.4
	S.append(note('bays  °c', g(x, y, w, CAP)))
	bw = w / len(DISKS)
	for i, temp in enumerate(DISKS):
		key = f'{H}.disk.temperature#bay{i + 1}'
		color = '$bad' if temp >= 50 else '$warn' if temp >= 43 else '$accent'
		S += [
			bar(key, g(x + i * bw + bw * 0.14, y + 2.4, bw * 0.3, 12.6), 25, 60, color=color, orientation='vertical',
			    track={'weight': '100%', 'color': '$rule', 'cap': 'flat'}, fill={'segments': 12, 'gap': '24%', 'cap': 'flat'}),
			mono(key, g(x + i * bw + bw * 0.44, y + 11.6, bw * 0.56, 3.4), color, hint='00', align='BottomLeft', group='global.bay'),
		]

	# ------------------------------------------------------------ services
	x, w = XB + px, WB - 2 * px
	V = cards['services'] = [
		note('// services', g(x, Y2 + py, 14, CAP), '$accent'),
		{**note('state', g(x + 14, Y2 + py, 7, CAP))},
		{**note('24 h', g(x + 21.4, Y2 + py, 7, CAP))},
		{**note('ms', g(x + 28.4, Y2 + py, w - 28.4, CAP)), 'alignment': 'BottomRight'},
	]
	tone = {'OK': '$accent', 'SLOW': '$warn', 'DOWN': '$bad'}
	for i, (name, state, ms) in enumerate(SERVICES):
		y = Y2 + 4.9 + i * 5.3
		c = tone[state]
		key = f'{H}.service.response#{name}'
		V += [
			label(name, g(x, y, 13.6, 3.2), '$text' if state == 'OK' else c),
			text(state, g(x + 14, y, 7, 3.2), font='$mono', weight='Bold', color=c, tracking=0.2, align='CenterLeft', group='global.state',
			     **({'outline': 1.6} if state == 'DOWN' else {})),
			mini(key, g(x + 21.4, y + 0.2, 7, 3), color=c, hours=24, past=True, top='12%', bottom='8%', opacity=0.9, fill=0.2, weight=0.35),
			(mono(key, g(x + 28.4, y, w - 28.4, 3.2), c, hint='000') if state != 'DOWN'
			 else label('—', g(x + 28.4, y, w - 28.4, 3.2), c, align='CenterRight')),
		]

	# ------------------------------------------------------------ dns and the alert
	x, w = XC + px, WC - 2 * px
	cards['dns'] = [
		note('// dns  queries today', g(x, Y2 + py, w, CAP), '$info'),
		dots(f'{H}.dns.queries', g(x, Y2 + 4.4, w, 8), '$info', hint='00000', group='global.wan'),
		mini(f'{H}.dns.blocked', g(x, Y2 + 13, w, 6.4), color='$warn', hours=24, past=True, top='10%', opacity=0.9, fill=0.3, glow=GLOW),
		{**note('blocked %, 24 h', g(x, Y2 + 19.6, w, CAP)), 'alignment': 'BottomRight'},
	]
	A = (XC, Y2 + 24.4, WC, H2 - 24.4)
	alert = nest('alertCard', A, [
		text('BACKUP OVERDUE', g(A[0] + px, A[1] + 2.2, w, 2.4), font='$mono', weight='ExtraBold', color='$warn', tracking=0.16, align='CenterLeft',
		     **{'format-hint': 'BACKUP OVERDUE'}),
		dots(f'{H}.backup.age', g(A[0] + px, A[1] + 5.6, 10, 9.4), '$warn', hint='00', group='global.alert'),
		text('hours since', g(A[0] + px + 10.6, A[1] + 7.2, 12, 2.6), font='$mono', weight='Light', italic=True, color='$muted', align='CenterLeft', group='global.aside'),
		text('nas-02 → b2', g(A[0] + px + 10.6, A[1] + 10.4, 12, 2.6), font='$mono', weight='Medium', color='$text', align='CenterLeft', group='global.aside'),
	], fill=None, beam={'size': 'md', 'variant': 'sunset', 'fill': '#120c02', 'active': True, 'phase': 0.35, 'strength': 1.0, 'radius': 24,
	                    'glow': {'strength': 0.9, 'reach': 3.0, 'passes': 6}})

	rects = {'cluster': (XA, Y1, WA, H1), 'wan': (XB, Y1, WB, H1), 'power': (XC, Y1, WC, H1),
	         'storage': (XA, Y2, WA, H2), 'services': (XB, Y2, WB, H2), 'dns': (XC, Y2, WC, 23.2)}
	for name, items in cards.items():
		B.append(nest(f'{name}Card', rects[name], items))
	B.append(alert)
	return {'theme': THEME, 'items': [{'type': 'group', 'name': 'board', 'items': B}]}


HEADER = """
Rack: the homelab showcase. A weekday evening with one node hot, one service slow, one down and a backup overdue.

Every number is set in a dot-matrix face (Doto) and every label in a monospace one (JetBrains Mono), written as code
comments. Segmented bars for the nodes, pools and drive bays, a needle dial for the power draw, a battery for the UPS,
and a beam round the one thing that needs attention.

Invented data: everything under homelab.* (a Proxmox, UniFi, ZFS, NUT, Pi-hole and uptime plugin that do not exist yet).
Fonts: Doto and JetBrains Mono (both OFL).
"""

if __name__ == '__main__':
	write('rack', HEADER, board(), data(), FREEZE)
