# Emissive render instability — is it pre-existing upstream?

**Status: CLOSED 2026-10-06 (answered).** The verdict below stands, and the
follow-up is settled: `Graph.py`'s zero-range divide is guarded now, yet a frozen
clock still destabilises a graph preset, so `emissive` keeps its `NO_FREEZE`
exemption. Re-measured on `dev` `b2499da` — frozen 4/4 dirty (2 SIGSEGV, 2 with
7 and 12 tracebacks), live 4/4 clean; numbers in
[meter-harness-status](meter-harness-status.md).

**Question.** `docs/design-references/presets/emissive.levity` (the only preset that
uses `glow:`) renders unreliably in the meter worktree: exit `-11` (SIGSEGV) at
shutdown with `RuntimeError: libshiboken: Internal C++ object (LevitySceneView)
already deleted` in the `Annotations.limitRect -> app.viewScale` path, a
`Graph.py:863: RuntimeWarning: divide by zero encountered in divide`, intermittent
missing PNG, and ~3k pixels of run-to-run drift between two captures of the same
code. Is that pre-existing on `feat/value-sources` at `a31af10`, or introduced by
`refactor/meter` (merged tip `5dea824`)?

**Verdict.** **Not introduced by the refactor/meter app changes.** Under an identical
render harness, upstream `a31af10` app code reproduces the *exact* same instability —
same `-11` SIGSEGV, same intermittent no-PNG, the same `limitRect -> viewScale ->
LevitySceneView already deleted` traceback and `Graph.py:863` divide-by-zero, and a
comparable ~2.8k–4.0k px two-run graph drift — and every crashing module
(`Graph.py`, `Annotations.py`, `app.py`, `shared.py`) is byte-identical across the two
trees. The segfault is in fact triggered by the branch's new **dev-only**
`--freeze-time` harness feature (`_boot.freeze_time`, `render_diff.py` default), not
by the shipped app: with the freeze off, *both* trees render cleanly (exit `0` + PNG).
So the underlying defect is a pre-existing zero-length-time-range bug in `Graph.py`
(unchanged) that the branch's new harness exposes; the meter/Gauge refactor is not the
cause.

## Setup

* Upstream baseline worktree: `git worktree add
  /Users/noblecloud/Code/LevityDash/.claude/worktrees/emissive-check a31af10`
  (`a31af10` is exactly parent-2 of `5dea824` — the `origin/feat/value-sources`
  commit the meter branch merged; `poetry install` there). Left in place, not removed.
  *(Note: `git fetch` has since moved `origin/feat/value-sources` to `dd241a0`, an
  `a31af10` descendant; `emissive.levity` is byte-identical across `a31af10`, `dd241a0`
  and the meter tip — blob `dc3b1ae86a0cfe5d3e32be304beb90b37d788938`.)*
* Meter worktree: the branch advanced mid-session from `5dea824` to `fa72444`
  ("docs(Tasks)…", **docs-only — 0 files under `src/` change**, so app code is
  identical). Meter runs a–c were captured at `5dea824`; d–h at `fa72444`; the pixel
  comparisons (d/e/f/h) are all within `fa72444` and internally consistent. Both are
  the same app code as `5dea824`.
* Preset, scenario and seed are the same for both trees: `emissive.levity` blob is
  identical; the harness-generated `_scenario.yaml` + staged `_seed/` from a meter
  capture were reused for the upstream runs.

### Why not the prescribed `--python` route

`render_diff.py capture … --python <other-tree>/.venv/bin/python` does **not** swap the
LevityDash source: `render_dashboard.py` does
`sys.path.insert(0, <its own tree>/src)` before `import LevityDash`, so the tree the
script lives in always wins. Verified: with another interpreter,
`import LevityDash; print(LevityDash.__file__)` still resolves to the meter tree's
`src/LevityDash/__init__.py`.

**Adaptation used** — hold the harness constant, swap only the app code:
1. copy the branch's three dev-only harness files (`render_diff.py`,
   `render_dashboard.py`, `_boot.py`) into the upstream worktree's
   `src/LevityDash/devtools/` (untracked/dev-only; `git status` = 2 modified + 1
   new), and
2. run the upstream worktree's venv, which imports the upstream `LevityDash` package
   (its `Gauge.py` is the pre-refactor 5959-line file; **no `meter/` package exists
   there** — confirmed). The only branch code in these runs is the dev harness itself.
3. Control: also ran the **native upstream renderer** (branch harness removed
   entirely — `git checkout --` the two files, `rm render_diff.py`) to prove the
   harness is the trigger.

Emissive size 1600x900 requested; scene renders 1600x830. PySide6 6.11.1 in both venvs
(Python 3.14.3 meter / 3.14.7 upstream — minor, noted).

## Raw results — branch harness, freeze on (the reported configuration)

| run | exit | secs | PNG written | tracebacks | notable |
|---|---|---|---|---|---|
| upstream a31af10 (a) | -11 | 25.6 | **no** | 0 | |
| upstream a31af10 (b) | -11 | 18.2 | yes | 2 | shiboken `LevitySceneView already deleted`; `Graph.py:863` div0 |
| upstream a31af10 (c) | -11 | 17.8 | **no** | 0 | |
| upstream a31af10 (d) | -11 | 24.3 | yes | 1 | `QBasicTimer…another thread`; `Graph.py:863` div0 |
| meter 5dea824 (a) | -11 | 16.7 | **no** | 0 | |
| meter 5dea824 (b) | -11 | 17.1 | **no** | 0 | |
| meter 5dea824 (c) | -11 | 17.3 | **no** | 0 | |
| meter 5dea824 (d) | -11 | 18.6 | yes | 2 | `labelFactory`/`TimestampLabel`; `Graph.py:863` div0 |
| meter 5dea824 (e) | -11 | 18.6 | yes | 2 | shiboken `LevitySceneView already deleted` ×2 |
| meter 5dea824 (f) | -11 | 18.4 | yes | 2 | shiboken `LevitySceneView already deleted` ×2 |
| meter 5dea824 (g) | -11 | 16.6 | **no** | 0 | |
| meter 5dea824 (h) | -11 | 18.7 | yes | 2 | `app.viewScale -> ViewScale(self.view.transform()…)` |

Both trees: **every run SIGSEGVs**; ~half write a PNG, ~half do not. The upstream
traceback is character-for-character the reported one — `Text.py:405 limitRect =
self.limitRect` -> `Annotations.py … viewScale = self.scene().viewScale` ->
`app.py:156 … ViewScale(self.view.transform().m11(), …)` ->
`RuntimeError: libshiboken: Internal C++ object (LevitySceneView) already deleted.`

## Two-run pixel verdicts (harness compare, level >30/255)

| tree | pair | differing px | share | where |
|---|---|---|---|---|
| upstream a31af10 | b vs d | **4037** | 0.30 % | y456–829; 3622/4037 (90 %) in graph band (y≥495) |
| meter 5dea824 | d vs e | **2861** | 0.22 % | y456–829; 2585 in graph band |
| meter 5dea824 | d vs f | **2763** | 0.21 % | y456–829; 2487 in graph band |
| meter 5dea824 | e vs h | **3017** | 0.23 % | y456–829; 2726 in graph band |

Same order of magnitude, same image region (the graph, ~90 %), both trees. The
earlier "3239 px" for the meter tree sits inside this range.

## Isolation — what actually triggers it

Direct `render_dashboard.py` runs on **upstream app code** (branch `_boot`/`render_dashboard`):

| variant | freeze | fixture `end` delay | exit | PNG | `divide by zero` |
|---|---|---|---|---|---|
| A ×2 | off | off | **0** | yes | 0 |
| B ×2 | off | on | **0** | yes | 0 |
| C ×2 | on | on | **139** (SIGSEGV) | no | 0 |
| D ×2 | on | off | **139** (SIGSEGV) | no | 1 |
| native upstream renderer ×2 | off | off | **0** | yes | 0 |

Symmetric controls on the **meter app**: emissive with `--no-freeze-time` ×2 → exit `0`,
PNG yes, no div0; a graph-free preset (`wrap-compass`) with freeze on ×2 → exit `0`,
PNG yes.

**Conclusion:** freeze on + a preset with a graph = SIGSEGV; freeze off, or a graph-free
preset, = clean. Identical on both trees.

## Root cause (unchanged code)

`Graph.py:862-863` (identical blob in both trees):

```python
seconds = self.figure.figureTimeRangeMaxMin.total_seconds()
x = (x - start.timestamp()) / seconds
```

A frozen clock collapses the Fixture-supplied series to a zero-length time range
(`seconds == 0`) -> divide-by-zero -> NaN geometry, and the Graph's deferred /
annotation work races the already-deleted `LevitySceneView` during teardown -> SIGSEGV
before the PNG is saved (hence the intermittent missing PNG). Without the freeze the
clock is live, the range is non-zero, and no such run appeared.

## Byte-identity across the two trees

`emissive.levity`, `Graph.py`, `Annotations.py`, `app.py`, `shared.py` — all identical.
`git diff a31af10 HEAD -- src/` touches only: `Gauge.py` (-5959) -> new `meter/`
package, plus the dev harness (`_boot.py`, `render_dashboard.py`, new `render_diff.py`)
and `GaugeShowcase.levity`. No glow/colour/Graph/Annotations change.

## Command log (scratch: `/Users/noblecloud/.hermes/cache/scratch/emissive-check`)

```
git worktree add …/emissive-check a31af10          # parent-2 of 5dea824
cd …/emissive-check && poetry install
cp …/blackfish-meter/src/LevityDash/devtools/{render_diff.py,render_dashboard.py,_boot.py} …/emissive-check/src/LevityDash/devtools/
cd …/emissive-check && .venv/bin/python src/LevityDash/devtools/render_diff.py capture $S/upstream-{a,b,c,d} --only emissive --jobs 1
cd …/blackfish-meter && .venv/bin/python src/LevityDash/devtools/render_diff.py capture $S/meter-{a..h} --only emissive --jobs 1
.venv/bin/python …/render_diff.py compare $S/upstream-b $S/upstream-d
.venv/bin/python …/render_diff.py compare $S/meter-d $S/meter-e
# controls
cd …/emissive-check && .venv/bin/python src/LevityDash/devtools/render_dashboard.py OUT.png --levity …/emissive.levity --seed $S/meter-d/_seed --scenario $S/meter-d/_scenario.yaml --size 1600x900 --settle 14 [--freeze-time]
cd …/blackfish-meter && … render_diff.py capture $S/meter-nofreeze-{1,2} --only emissive --no-freeze-time
cd …/blackfish-meter && … render_diff.py capture $S/meter-wrap-{1,2} --only wrap-compass
```

### Worktree state

`/Users/noblecloud/Code/LevityDash/.claude/worktrees/emissive-check` is **left in place**
(as required). Its `src/LevityDash/devtools/` currently holds the branch harness overlay
(`_boot.py` + `render_dashboard.py` modified, `render_diff.py` untracked) — `git status
--short` = ` M _boot.py`, ` M render_dashboard.py`, `?? render_diff.py`. The user's main
checkout and all other worktrees were not touched. Nothing was committed or pushed.
