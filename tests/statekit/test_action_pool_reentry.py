"""An action that opens its own pool and re-queues itself must not recurse.

`Stack.setGeometries` runs `with self.action_pool:` and its child writes queue
`setGeometries` again. The pool used to run on every exit at context level 0,
including the exit inside its own running action, so each run started another
until `RecursionError` (frontend.out, 2026-10-04).

Pure Python - no Qt, no LevityDash import required.
"""
from statekit.actions import ActionPool


class Host:
	is_loading = False
	state_is_loading = False

	def __init__(self):
		self.runs = 0
		self.pool = ActionPool(self)

	def relayout(self):
		self.runs += 1
		with self.pool:
			# What a child property write does: queue this action again.
			self.pool.add(Host.relayout)


def test_action_requeuing_itself_runs_once():
	host = Host()
	with host.pool:
		host.pool.add(Host.relayout)
	assert host.runs == 1
