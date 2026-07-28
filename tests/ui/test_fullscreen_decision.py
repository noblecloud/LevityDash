"""The window-size heuristic must not override an explicit fullscreen setting.

Reported 2026-07-27: the app opened fullscreen on a small display despite
`fullscreen = False` in config.ini. Configured sizes are clamped to the screen,
so on a display smaller than the requested size both axes clamp to the screen
bounds, `similarity` reaches ~1.0, and the heuristic won.
"""
import pytest

from LevityDash.lib.ui.frontends.PySide.app import (
	FULLSCREEN_SIMILARITY_THRESHOLD,
	shouldStartFullscreen,
)

FILLS_THE_SCREEN = 1.0
HALF_THE_SCREEN = 0.5


def test_explicit_false_beats_the_size_heuristic():
	"""The reported bug: config says no, window happens to fill the screen."""
	assert not shouldStartFullscreen(
		fullscreen=False, isExplicit=True, forcedByArgv=False, similarity=FILLS_THE_SCREEN
	)


def test_heuristic_still_applies_when_nothing_is_configured():
	assert shouldStartFullscreen(
		fullscreen=False, isExplicit=False, forcedByArgv=False, similarity=FILLS_THE_SCREEN
	)


def test_heuristic_leaves_a_small_window_alone():
	assert not shouldStartFullscreen(
		fullscreen=False, isExplicit=False, forcedByArgv=False, similarity=HALF_THE_SCREEN
	)


def test_explicit_true_wins_at_any_size():
	assert shouldStartFullscreen(
		fullscreen=True, isExplicit=True, forcedByArgv=False, similarity=HALF_THE_SCREEN
	)


def test_argv_overrides_an_explicit_false():
	"""`--fullscreen` is a deliberate per-launch act, so it outranks config."""
	assert shouldStartFullscreen(
		fullscreen=False, isExplicit=True, forcedByArgv=True, similarity=HALF_THE_SCREEN
	)


@pytest.mark.parametrize(
	'similarity, expected',
	[
		(FULLSCREEN_SIMILARITY_THRESHOLD - 0.01, False),
		(FULLSCREEN_SIMILARITY_THRESHOLD, False),  # strictly greater than
		(FULLSCREEN_SIMILARITY_THRESHOLD + 0.01, True),
	],
)
def test_threshold_boundary(similarity, expected):
	assert shouldStartFullscreen(
		fullscreen=False, isExplicit=False, forcedByArgv=False, similarity=similarity
	) is expected
