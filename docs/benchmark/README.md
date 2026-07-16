# LevityDash LLM Benchmark — Admin Guide

A repeatable audition for candidate AI models, testing the abilities that predict usefulness on *this* codebase: comprehension, bug hunting, cross-module reasoning, and disciplined task execution. Internal-only, like `docs/tasks/` — never publish this directory to the docs branch/site.

## Files

| File | Committed? | Who sees it |
|---|---|---|
| `tier0-basics.md` | yes | pasted to candidates (small/local models especially) |
| `tier1-screener.md` | yes | pasted to candidates (no repo access needed) |
| `tier2-repo-eval.md` | yes | candidates with the repo checked out |
| `scorecard.md` | yes | you, while grading |
| `ANSWER-KEY.md` | **NO — gitignored** | you only |

The answer key is gitignored because everything committed on `dev` syncs to candidate-accessible clones. If it ever goes missing, ask Fable to regenerate it (the answers derive from real fixed bugs in git history plus current-code facts).

## Running Tier 0 (basic comprehension, ~15 min of candidate effort)

The floor check, built for small local models (e.g. 7–14B quantized on the Mac Mini): four short paste-only items — identify the project from its README, explain a small function, explain a small class, describe what a YAML layout block renders. The whole pack is deliberately tiny so it fits limited context windows; paste it alone into a fresh session with no system-prompt extras.

**Gate: ≥8/12 to bother with Tier 1.** Tier 0 is a pure gate — it doesn't count toward the 78-point total. A model that fails it can't reliably read code at all, and no further tier will change that conclusion. For frontier/API models you can skip Tier 0 entirely and start at Tier 1.

## Running Tier 1 (chat screener, ~30 min of candidate effort)

1. Paste the entire contents of `tier1-screener.md` into a fresh session of the candidate model — no repo, no other context.
2. Grade against the key. **Gate: ≥22/32 (~70%) to proceed.** Section B (bug hunting) is the strongest signal — a model that misses 3+ of the 4 planted real bugs won't be a useful fixer here no matter how well it talks.

## Running Tier 2 (repo-in-hand, ~90 min of candidate effort)

1. Reset the candidate clone to a clean, current state (this also wipes the previous candidate's work so nobody grades against — or peeks at — a predecessor's branch):

   ```bash
   cd ~/Code/LevityDash-deepseek        # or whichever clone the candidate uses
   git fetch origin
   git checkout dev
   git reset --hard origin/dev
   git clean -fd
   # delete any prior candidates' branches:
   git branch | grep -v ' dev$\|main' | xargs -r git branch -D
   ```

2. Point the candidate (OpenCode or similar) at the clone and give it the contents of `tier2-repo-eval.md` as its task.
3. Grade C/D answers against the key; grade E by inspecting the pushed branch (the key has the rubric, including instant-zero conditions like merging into `dev`).
4. Optional but recommended: before wiping for the next candidate, note whether the Section E branch is actually mergeable — a good submission is real work you can keep.

## Scoring

Fill a column per model in `scorecard.md`. The dimension rollup at the bottom matters more than the grand total: a model strong on comprehension but weak on task execution is a reviewer, not a contributor; the reverse is a contributor who needs tight briefs.

Bands (out of 83): **≥66** trust with `docs/tasks/` briefs unsupervised · **50–65** useful with review · **33–49** QA/rubber-duck only · **<33** pass.

## Integrity notes

- Tier 1's Section B bugs are real (they're in this repo's git history, already fixed) — that's why Tier 1 is chat-paste only. A repo-in-hand candidate could `git log` its way to the answers.
- Tier 2 forbids history inspection for Sections C/D (stated in the doc). Not mechanically enforceable — spot-check suspiciously commit-message-flavored answers.
- Don't reuse Section E's task once a merged solution exists on `dev` (the candidate could read it). Swap in an equivalent micro-task (OpenMeteo or WeatherFlow golden-fixture tests per `docs/tasks/schema-golden-fixture-tests.md`) and adjust the key's E-notes accordingly.
- Calibration: consider dry-running Tier 1 on a known-weak model and a known-strong one first, to sanity-check that the spread is real before burning it on candidates you care about.
