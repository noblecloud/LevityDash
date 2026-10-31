import ast
from pathlib import Path

SOURCE = Path(__file__).parents[2] / 'src/LevityDash/lib/ui/frontends/PySide/Modules/Displays/Realtime.py'


def test_approximate_realtime_callback_is_passed_not_called():
	"""approximateRealtimeOnLastAttempt handed itself to notifyOnRequirementsMet *called*, so a
	realtime-approximate source recursed until RecursionError (found by the soak test)."""
	tree = ast.parse(SOURCE.read_text())
	for fn in ast.walk(tree):
		if isinstance(fn, ast.FunctionDef) and fn.name == 'approximateRealtimeOnLastAttempt':
			for call in ast.walk(fn):
				if isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == fn.name:
					raise AssertionError('approximateRealtimeOnLastAttempt calls itself')
			return
	raise AssertionError('approximateRealtimeOnLastAttempt not found')
