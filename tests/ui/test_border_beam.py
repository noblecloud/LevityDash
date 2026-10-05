"""Border beams: the ported painters and maths, the panel decoration, and its triggers.

The first half is the pixel and maths tests of `border-beam-qt`, moved over and changed to
reach the painters through a `PanelBeam`. A beam held at a time with `phase:` is deterministic,
which is what lets a test look at pixels. The second half covers what is new here: the beam is
off by default, `active` follows a condition, `sweep` runs once per arriving value, and the
shared clock stops when no beam animates.
"""
import pytest
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage, QPainter

from LevityDash.lib.plugins.computed import computedEngine
from LevityDash.lib.ui.frontends.PySide.Modules import Panel
from LevityDash.lib.ui.frontends.PySide.Modules.beam import styles
from LevityDash.lib.ui.frontends.PySide.Modules.beam.item import PanelBeam
from LevityDash.lib.ui.frontends.PySide.Modules.beam.palettes import (
	LINE_INNER, LINE_PALETTES, LineBlob, apply_filters, hue_shift, line_hue_shift, ping_pong, theme_dark,
)
from LevityDash.lib.ui.frontends.PySide.Modules.beam.pulse_driver import PulseDriver
from LevityDash.lib.ui.frontends.PySide.Modules.beam.ring import ring_color
from LevityDash.lib.ui.frontends.PySide.Modules.beam.types import ColorVariant, Size, Theme

W, H = 260, 140


# section maths, from border-beam-qt/tests/test_palettes.py

def test_hue_shift_wraps_full_cycle():
	red = QColor(255, 0, 0)
	assert hue_shift(red, 120.0).hue() == pytest.approx(120, abs=2)
	assert hue_shift(red, -120.0).hue() == pytest.approx(240, abs=2)
	assert hue_shift(red, 360.0).hue() == hue_shift(red, 0.0).hue()


def test_apply_filters_multiplies_brightness_and_saturation():
	color = QColor(60, 120, 200)
	assert apply_filters(color, 0.5, 1.0).valueF() == pytest.approx(0.5 * color.valueF(), abs=0.02)
	assert apply_filters(color, 1.0, 2.0).saturationF() == pytest.approx(1.0)


def test_ping_pong_cosine_ease():
	assert ping_pong(0.0) == pytest.approx(0.0)
	assert ping_pong(0.5) == pytest.approx(1.0)
	assert ping_pong(1.0) == pytest.approx(0.0)
	assert ping_pong(0.25) == pytest.approx(0.5, abs=1e-3)
	assert ping_pong(0.75) == pytest.approx(0.5, abs=1e-3)


def test_line_hue_shift_oscillates_within_range():
	assert line_hue_shift(0.0, 30.0) == pytest.approx(-30.0)
	assert line_hue_shift(6.0, 30.0) == pytest.approx(30.0)
	assert line_hue_shift(12.0, 30.0) == pytest.approx(-30.0)
	assert line_hue_shift(0.0, 0.0) == pytest.approx(0.0)


def test_theme_dark():
	assert theme_dark(Theme.DARK) is True
	assert theme_dark(Theme.LIGHT) is False


def test_keyframe_interpolates_between_keys():
	keys = ((0.0, 0.0), (0.5, 10.0), (1.0, 0.0))
	assert styles.keyframe(keys, 0.25) == pytest.approx(5.0)
	assert styles.keyframe(keys, 0.5) == pytest.approx(10.0)
	assert styles.keyframe(keys, 1.0) == pytest.approx(0.0)


def test_line_values_match_upstream_keyframes():
	assert styles.line_values(0.0)['edge'] == pytest.approx(0.0)  # invisible at the very start
	assert styles.line_values(0.25)['edge'] == pytest.approx(0.625)
	assert styles.line_values(1.0)['edge'] == pytest.approx(0.0)


def test_pulse_params_defaults_per_size():
	assert styles.pulse_params(Size.SMALL, True, 2.5).sp == pytest.approx(styles.pulse_params(Size.MEDIUM, True, 2.5).sp)
	inner = styles.pulse_params(Size.PULSE_INNER, True, 2.3)
	outside = styles.pulse_params(Size.PULSE_OUTSIDE, True, 2.3)
	assert inner.sp == pytest.approx(0.28)
	assert inner.dr > outside.dr
	assert styles.pulse_params(Size.PULSE_INNER, True, 4.6).bs == pytest.approx(2 * inner.bs)


def test_pulse_values_breathe_shape():
	pm = styles.pulse_params(Size.PULSE_INNER, True, 2.3)
	v0 = styles.pulse_values(pm, 0.0)
	vpeak = styles.pulse_values(pm, 0.5 * pm.ss * 0.9)
	assert vpeak['bw1'] > v0['bw1']
	assert v0['bw1'] == pytest.approx(1 - pm.sp)
	assert vpeak['bw1'] == pytest.approx(1 + pm.sp * 1.1)


def test_themes_have_expected_preset_keys():
	for dark in (True, False):
		for size in Size:
			preset = styles.THEME_PRESETS[size]['dark' if dark else 'light']
			for key in ('saturation', 'stroke_opacity', 'inner_opacity', 'bloom_opacity', 'inner_shadow'):
				assert key in preset, f'{size} {dark}: missing {key}'


def test_line_palettes_are_lineblobs():
	for variant in ColorVariant:
		for blob in LINE_PALETTES[variant]['dark']:
			assert isinstance(blob, LineBlob)
		for blob in LINE_INNER[variant]:
			assert isinstance(blob, LineBlob)


def test_frame_and_ring_masks_shape():
	frame = styles.frame_fade_mask(100, 80)
	assert frame.pixelColor(50, 40).alpha() == 0  # centre punched out
	assert frame.pixelColor(1, 1).alpha() == 255  # corner: both strips overlap
	assert frame.pixelColor(1, 40).alpha() == 241  # edge strip only
	assert frame.pixelColor(29, 40).alpha() == 0  # past the 28px band
	ring = styles.ring_mask(100, 80, 12.0, 1.0)
	assert ring.pixelColor(50, 40).alpha() == 0
	assert ring.pixelColor(0, 40).alpha() > 0


def test_conic_wedge_rotate_direction():
	# CSS `from 0deg` puts the head at the bottom-left and moves it clockwise as the angle grows.
	# QConicalGradient runs counter-clockwise, so the port negates the angle.
	def dominant(css_angle: float) -> str:
		mask = styles.conic_wedge_mask(100, 100, css_angle)
		points = {'top': (50, 5), 'left': (5, 50), 'bottom': (50, 95), 'right': (95, 50)}
		return max(points, key=lambda k: mask.pixelColor(*points[k]).alpha())

	assert [dominant(a) for a in (0.0, 90.0, 180.0, 270.0)] == ['bottom', 'left', 'top', 'right']


def test_ring_color_uses_levitydash_oklch():
	# The ring colours come from lib/ui/colors/oklch.py, so they match its chain exactly.
	from LevityDash.lib.ui.colors.oklch import display_color, oklch_color
	r, g, b = display_color(oklch_color(145.0))
	expected = QColor(round(r * 255), round(g * 255), round(b * 255))
	assert ring_color(0, 0.0) == expected
	assert ring_color(3, 0.0) == expected  # the ring has three hues and wraps


# section pixels, from border-beam-qt/tests/test_rendering.py

@pytest.fixture
def clock():
	"""The shared clock, thawed again after the test."""
	driver = PulseDriver.shared()
	yield driver
	driver.unfreeze()


@pytest.fixture
def sandbox(dashboard):
	box = Panel(parent=dashboard.scene.base, geometry={'x': '0%', 'y': '0%', 'width': '10%', 'height': '10%'})
	yield box
	if box.scene() is not None:
		box.scene().removeItem(box)


def make_beam(sandbox, size, **settings) -> PanelBeam:
	"""A beam on a 260x140 panel, held at `phase` (0 when none is given)."""
	sandbox.setRect(QRectF(0, 0, W, H))
	settings = {'size': size, 'active': True, 'phase': 0.0, **settings}
	sandbox.state = {'beam': settings}
	return sandbox.beamProp


def render(beam: PanelBeam) -> QImage:
	"""The card, the halo and the beam, painted the way the scene paints the two layers."""
	halo = styles.PULSE_HALO if beam.size is Size.PULSE_OUTSIDE else 0
	image = QImage(W + 2 * halo, H + 2 * halo, QImage.Format.Format_ARGB32_Premultiplied)
	image.fill(0)
	painter = QPainter(image)
	painter.translate(halo, halo)
	painter.setBrush(QColor('#1d1d1d'))
	painter.setPen(QColor('#3a3a3a'))
	beam.paintBehind(painter)
	painter.drawRoundedRect(QRectF(0.5, 0.5, W - 1, H - 1), 16, 16)
	beam.paint(painter, None)
	painter.end()
	return image


def sat_pixels(image: QImage):
	"""Locations that read as glow: saturated, and bright enough."""
	pixels = []
	for y in range(image.height()):
		for x in range(image.width()):
			c = image.pixelColor(x, y)
			if c.hsvSaturationF() > 0.2 and c.valueF() > 0.25:
				pixels.append((x, y, c))
	return pixels


@pytest.mark.parametrize('size', [s.value for s in Size])
def test_all_presets_render_beam_pixels(sandbox, size):
	beam = make_beam(sandbox, size, phase=3.0 if size.startswith('pulse') else 1.0)
	assert len(sat_pixels(render(beam))) > 20, f'{size}: beam essentially empty'


def test_rotate_beam_travels_around_ring(sandbox):
	# At progress 0 the centroid sits on the middle of the bottom edge, so start a little after it.
	# The inner mask is (conic and vertical) or horizontal, so the left and right strips stay lit.
	# The travel shows as the glow centroid on the edge sweeping clockwise: BL, TL, TR, BR.
	beam = make_beam(sandbox, 'md')
	cycle = beam.cycle
	quads = []
	for progress in (0.02, 0.25, 0.5, 0.75):
		beam.phase = progress * cycle
		image = render(beam)
		xs, ys = [], []
		for y in range(3, H - 3):
			for x in range(3, W - 3):
				if not (x < 6 or y < 6 or x >= W - 6 or y >= H - 6):
					continue
				c = image.pixelColor(x, y)
				if c.hsvSaturationF() > 0.2 and c.valueF() > 0.2:
					xs.append(x)
					ys.append(y)
		cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
		quads.append(('BL' if cx < W / 2 else 'BR') if cy > H / 2 else ('TL' if cx < W / 2 else 'TR'))
	assert quads == ['BL', 'TL', 'TR', 'BR'], quads


def test_mono_variant_is_desaturated(sandbox):
	image = render(make_beam(sandbox, 'md', variant='mono'))
	for y in range(0, H, 8):
		for x in range(0, W, 8):
			c = image.pixelColor(x, y)
			if c.red() > 40:  # beam brightness; the card is #1d1d1d
				assert c.saturationF() < 0.05


def test_strength_zero_is_invisible_and_strength_scales(sandbox):
	assert len(sat_pixels(render(make_beam(sandbox, 'md', strength=0.0)))) == 0
	cycle = sandbox.beamProp.cycle
	weak = len(sat_pixels(render(make_beam(sandbox, 'md', strength=0.2, phase=0.25 * cycle))))
	full = len(sat_pixels(render(make_beam(sandbox, 'md', strength=1.0, phase=0.25 * cycle))))
	assert full > weak


def test_pulse_breathes_brighter(sandbox):
	# bop-tl peaks at t=0.95 s and troughs at t=0 for the 2.3 s baseline.
	beam = make_beam(sandbox, 'pulse-inner')

	def band_sum(t: float) -> float:
		beam.phase = t
		image = render(beam)
		total = 0.0
		for y in range(H):
			for x in range(W):
				if x < 28 or x >= W - 28 or y < 28 or y >= H - 28:
					c = image.pixelColor(x, y)
					if c.hsvSaturationF() > 0.2:
						total += c.valueF()
		return total

	assert band_sum(0.95) > 1.25 * band_sum(0.0)


def test_pulse_outside_spills_past_the_card(sandbox):
	image = render(make_beam(sandbox, 'pulse-outside', phase=3.0))
	halo = styles.PULSE_HALO
	assert image.width() == W + 2 * halo
	outside = [
		(x, y) for y in range(image.height()) for x in range(image.width())
		if x < halo or y < halo or x >= halo + W or y >= halo + H
	]
	assert sum(1 for x, y in outside if image.pixelColor(x, y).alpha() > 0) > 500


def test_line_is_invisible_at_the_start_and_visible_mid_travel(sandbox):
	assert len(sat_pixels(render(make_beam(sandbox, 'line', phase=0.0)))) == 0
	beam = make_beam(sandbox, 'line')
	beam.phase = 0.25 * beam.cycle
	assert len(sat_pixels(render(beam))) > 100


def test_oklch_color_space_changes_the_colours(sandbox):
	hsv = render(make_beam(sandbox, 'pulse-inner', phase=0.95))
	oklch = render(make_beam(sandbox, 'pulse-inner', phase=0.95, **{'color-space': 'oklch'}))
	assert hsv != oklch
	assert len(sat_pixels(oklch)) > 20


# section the decoration

def test_a_panel_has_no_beam_unless_it_asks(sandbox):
	assert sandbox.beamProp is None
	assert not sandbox.state.get('beam')


def test_a_declared_beam_is_off_until_active_or_swept(sandbox, clock):
	sandbox.state = {'beam': {'size': 'md'}}
	beam = sandbox.beamProp
	assert not beam.isVisible()
	assert not beam.wanted
	assert clock.subscriberCount == 0
	assert not clock.running


def test_settings_round_trip(sandbox):
	settings = {
		'size': 'line', 'variant': 'ocean', 'theme': 'light', 'color-space': 'oklch', 'duration': 2.0,
		'strength': 0.5, 'radius': 8.0, 'active': 'environment.temperature.temperature > 90',
	}
	sandbox.state = {'beam': settings}
	saved = sandbox.beamProp.state
	for key, value in settings.items():
		assert saved[key] == value, key
	assert 'phase' not in saved  # defaults stay out of the file


def test_an_unknown_size_falls_back_with_a_warning(sandbox):
	sandbox.state = {'beam': {'size': 'enormous'}}
	assert sandbox.beamProp.size is Size.MEDIUM


def test_active_true_runs_the_clock_and_active_false_stops_it(dashboard, sandbox, clock):
	sandbox.setRect(QRectF(0, 0, W, H))
	sandbox.state = {'beam': {'size': 'md', 'active': True}}
	beam = sandbox.beamProp
	assert beam.isVisible()
	assert clock.running and clock.subscriberCount == 1
	dashboard.wait_until(lambda: beam._fade >= 1.0, timeout=3, message='fade in')

	sandbox.state = {'beam': {'size': 'md', 'active': False}}
	dashboard.wait_until(lambda: not clock.running, timeout=3, message='the clock stops after the fade out')
	assert not beam.isVisible()
	assert clock.subscriberCount == 0


def test_a_frozen_clock_stays_stopped(sandbox, clock):
	clock.set_time(1.25)
	sandbox.setRect(QRectF(0, 0, W, H))
	sandbox.state = {'beam': {'size': 'pulse-inner', 'active': True}}
	assert not clock.running
	assert clock.t == pytest.approx(1.25)


def test_active_follows_a_condition(dashboard, sandbox, clock):
	expression = 'environment.temperature.temperature > 90'
	sandbox.setRect(QRectF(0, 0, W, H))
	sandbox.state = {'beam': {'size': 'md', 'active': expression}}
	beam = sandbox.beamProp
	engine = computedEngine()
	key = beam._activeBinding.source.key
	assert not beam.wanted

	engine._publish(engine._entries[key], True)
	dashboard.wait_until(lambda: beam.wanted, message='the beam turns on when the condition holds')
	assert clock.running

	engine._publish(engine._entries[key], False)
	dashboard.wait_until(lambda: not beam.wanted, message='the beam turns off when the condition fails')
	dashboard.wait_until(lambda: not clock.running, timeout=3, message='the clock stops after the fade out')

	sandbox.scene().removeItem(sandbox)
	assert engine.refcount(key) == 0, 'removing the panel releases the value source'


def test_sweep_runs_once_per_arriving_value(dashboard, sandbox, clock):
	sandbox.setRect(QRectF(0, 0, W, H))
	sandbox.state = {'beam': {'size': 'md', 'duration': 0.3, 'sweep': 'max(environment.temperature.temperature, today)'}}
	beam = sandbox.beamProp
	engine = computedEngine()
	key = beam._sweepBinding.source.key
	assert not beam.wanted, 'the value that was there when the beam opened is not news'
	assert not clock.running

	engine._publish(engine._entries[key], 70.0)
	dashboard.wait_until(lambda: beam.wanted, message='a new value starts a sweep')
	assert clock.running
	dashboard.wait_until(lambda: not beam.wanted, timeout=3, message='the sweep ends by itself')
	dashboard.wait_until(lambda: not clock.running, timeout=3, message='the clock stops after the sweep')
	assert not beam.isVisible()

	engine._publish(engine._entries[key], 71.0)
	dashboard.wait_until(lambda: beam.wanted, message='the next value sweeps again')
	dashboard.wait_until(lambda: not clock.running, timeout=3)


def test_the_clock_is_shared_by_every_beam(dashboard, clock):
	boxes = []
	for _ in range(3):
		box = Panel(parent=dashboard.scene.base, geometry={'x': '0%', 'y': '0%', 'width': '10%', 'height': '10%'})
		box.setRect(QRectF(0, 0, W, H))
		box.state = {'beam': {'size': 'pulse-inner', 'active': True}}
		boxes.append(box)
	try:
		assert clock.subscriberCount == 3
		assert clock.running
	finally:
		for box in boxes:
			box.scene().removeItem(box)
	assert clock.subscriberCount == 0, 'a beam that leaves the scene gives up its subscription'
	assert not clock.running
