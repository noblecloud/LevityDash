---
name: orchestrate
description: Split LevityDash work into phases and run each phase as a scoped subagent, then review, render-check and merge the results. Use when a goal crosses several files or concerns (e.g. a gauge primitive plus a loader fix plus a test), when the user asks to orchestrate or fan out subagents, or when working through several docs/tasks briefs at once.
---

# Orchestrate subagents on LevityDash

Adapted from the Orchestration Protocol
(alirezarezvani/claude-skills, `orchestration/ORCHESTRATION.md`): objective →
phases → per-phase expertise → handoffs. Here the "persona" is not role-play.
It is the reviewing stance the orchestrator takes on each result. A phase's
expertise comes from its brief and the skills it loads.

## 1. Objective

Write it down before splitting it: what changes, how it is verified, what is
out of scope. If a `docs/tasks/*.md` brief covers it, that brief *is* the
objective. Do not restate it; point at it.

## 2. Phases

One phase = one subagent = one reviewable diff. Split by **file ownership**,
not by topic:

- Two phases that edit the same file run **in sequence**, or in separate
  worktrees (`isolation: "worktree"`) with the overlap called out so the merge
  is planned rather than discovered.
- Phases with disjoint files run **in parallel**, in worktrees.
- **A worktree does not start on your branch.** It starts on an old base
  (it has been `origin/main`), with none of the branch's work. Every brief
  must name the base and make re-basing step one:
  `git checkout -B <branch> <working branch>`. Commit the working branch
  first, since uncommitted files never reach a worktree.
- Read-only phases (investigate, find, measure) need no worktree.

**Pick the model per phase; never let it default to the orchestrator's.**
Pass `model` on every Agent call:

| Phase | Model |
|---|---|
| new primitive, design calls, unclear spec | `opus` |
| bounded fix, investigate-and-verify, render checks | `sonnet` |
| run a script, grep, report numbers | `haiku` |

Bounded phases go to the `levity-worker` agent (`.claude/agents/`): Sonnet at
normal effort, with the base-branch and render rules built in.

The orchestrator's review catches a weaker model's mistakes; that is what
the review step is for.

Keep a phase small enough that its result can be reviewed in one sitting. A
phase that needs its own phases is a brief for `docs/tasks/`, not a subagent.

## 3. Brief (what each subagent receives)

A subagent starts cold. Its prompt must stand alone:

```
Goal:       one sentence, the observable result
Context:    files and functions by repo path, the relevant brief section,
            decisions already made (don't make it re-derive them)
Constraints:
  - tabs; commit `type(Scope): summary` + blank line +
    `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`
  - no new imports of Qt/LevityDash from statekit/qolkit
  - stacks for uniform data/sections, relative geometry for composed
    groups (.claude/skills/levity-dashboard-design/SKILL.md)
  - never push; commit in its worktree only
Environment: the interpreter, QT_QPA_PLATFORM=offscreen, and PYTHONPATH
            pointing at the worktree's src/ (the shared venv's editable
            install points at the main checkout, not the worktree)
Verify:     the exact command(s), usually a render:
            render_widget.py --levity F --scenario hot-clear-day --name N --out P
            plus the narrowest pytest path
Report:     commits, verification output, PNG paths, anything unfinished
            or suspicious. Say "not verified" rather than implying it.
```

Load-bearing skill per kind of phase:

| Phase kind | Skill / source the brief points at |
|---|---|
| layout, gauge looks, `.levity` fragments | `levity-dashboard-design` |
| data layer, expressions, computed keys | `docs/tasks/value-sources.md`, `lib/plugins/computed.py` |
| gauge primitives (N1–N7) | `docs/tasks/gauge-presets.md`, `gauge-display.md` |
| a bug | the failing render or test, reproduced first |

## 4. Review (the orchestrator's stance)

Each result comes back to the orchestrator, never straight to the branch:

1. **Read the diff**, not just the report. Reports are optimistic.
2. **Look at the PNG** yourself. A render that "succeeded" can still show
   overlap, clipping or the placeholder dots (no value).
3. **Re-run the verify command** if the claim matters.
4. Accept, send back with a specific correction (continue the same agent),
   or drop it and say why.

## 5. Handoff and merge

Merge accepted worktree branches into the working branch one at a time,
re-rendering after each merge that touches shared files. Carry forward:

```
Done:      commits, what they prove
Decided:   choices later phases must not reopen
Open:      what the next phase or the user must resolve
```

Run `pytest` once after the last merge. Push only the designated branch.
Report to the user: commits, PNGs, failures (with cause), unfinished work.
