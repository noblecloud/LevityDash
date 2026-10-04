# Handoff: two Realtime panels sharing one expression key

Goal: two `realtime.text` panels with the same expression key both show the value and share one computed key, and deleting one leaves the other working. Fix whatever breaks.

Branch: `agent-realtime-expr2`, based on `feat/value-sources` (`dadd840`). The worktree's original base (`29991c6`) and local `dev` (`063bd15`) predate the computed-keys work, and `git merge dev` conflicts in `Panel.py`. Base this work on `feat/value-sources`, not `dev`.

## Check results

| Check | Result |
|---|---|
| Both panels render 99° (`hot-clear-day`, 400x200) | **passed** |
| Refcount of the computed key is 2 with both panels | **not run** |
| Refcount drops to 1 after deleting one panel | **not run** |
| The remaining panel still updates after the delete | **not run** |
| Saving the remaining panel keeps the expression text as `key` | **not run** |

No code was changed and nothing is fixed.

## Files (scratchpad, not in the repo)

`/tmp/claude-0/-home-user-LevityDash/7f7f9324-ce71-5a44-ab8b-aebb9d0db62b/scratchpad/shared/`
- `two-highs.levity`: a horizontal `stack` holding `high-a` and `high-b`, both keyed `max(environment.temperature.temperature, today)`
- `two-high-a.png`, `two-high-b.png`: both show "Today's high 99°"

**There is no throwaway script yet.** It was never written.

Render command (run from the worktree):

    PYTHONPATH=$PWD/src QT_QPA_PLATFORM=offscreen /home/user/LevityDash/.venv/bin/python \
      src/LevityDash/devtools/render_widget.py --levity <frag> --scenario hot-clear-day \
      --name high-a --out <png> --size 400x200

## Next steps

1. Write the script in the scratchpad. Copy the setup from `render_widget.py`, which seeds the fixture scenario and then calls `_boot.boot(levity=...)`. After that:
   - find the panels with `_boot.named_items(app.scene)` (or whatever `render_widget.py` uses to get the scene)
   - check `computedEngine().refcount(panel.key) == 2`
   - call `delete()` on `high-a`, pump events, and check the refcount is 1
   - publish a new value through the Fixture plugin, or re-trigger the engine, and confirm `high-b` changes
   - check `high-b.state['key']` (or the encoded state) equals the expression text
2. Code to suspect:
   - `utils.py` `loadRealtime`, line 185: it matches `Realtime(key=ns.key)`, which compares a computed `CategoryItem` with the raw expression string. When the dashboard is reloaded over existing panels, check that this doesn't fall back to `_bestMatch`.
   - `Realtime.key` setter (`Realtime.py` ~193): when the key is unchanged, it releases the newly acquired source so the refcount stays balanced. Confirm that `state =` on a panel that is reused during a reload does not double-count.
3. Make any fix minimal. Add a regression test under `tests/ui` if it fits `tests/conftest.py`. Commit format: `fix(UI.Realtime): ...`.
