"""The container flags `Realtime.py` reads must exist on both container kinds.

`startConnecting` asked a container for `isTimeSeriesOnly` while every container spells it `isTimeseriesOnly`, so a
display whose preferred source offered only an approximate realtime value raised an AttributeError (and in
mode=remote, which hits that branch at once, printed a traceback per display). The branch is deep inside a
closure, so this reads the flags it names instead of driving it.
"""
import re
from pathlib import Path

import pytest

from LevityDash.lib.plugins.observation import Container
from LevityDash.lib.wire.containers import RemoteContainer

SOURCE = Path(__file__).parents[2] / 'src/LevityDash/lib/ui/frontends/PySide/Modules/Displays/Realtime.py'


def flagsRead() -> set:
	return set(re.findall(r'\b(?:trueRealtimeContainer|preferredTrueRealtimeContainer)\.(is[A-Z]\w*)', SOURCE.read_text()))


def test_realtime_reads_some_flags():
	assert 'isRealtimeApproximate' in flagsRead()


@pytest.mark.parametrize('kind', [Container, RemoteContainer], ids=['live', 'remote'])
def test_every_flag_realtime_reads_exists(kind):
	missing = sorted(flag for flag in flagsRead() if not hasattr(kind, flag))
	assert not missing, f'{kind.__name__} has no {missing}'
