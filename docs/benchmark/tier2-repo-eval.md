# LevityDash Repo Evaluation (Tier 2)

You have this repository checked out. This evaluation tests whether you can navigate, reason about, and contribute to it the way a real collaborator would. Expected effort: about 90 minutes.

**Start by reading `AGENTS.md` at the repo root in full.** The workflow it describes is in force for Section E, and knowing its contents is itself part of the evaluation.

Ground rules:

- Answer Sections C and D in prose, citing file paths (and symbols/line regions where helpful). Answers must come from reading the current code — not from guessing at conventions common in other projects.
- **Do not use `git log`, `git blame`, or any other history inspection to answer questions.** Answers derived from commit messages score zero. (Section E permits normal git usage for its own branch/commits.)
- If you believe a question contains a wrong premise, say so and explain — that scores full credit when correct.

---

## Section C — Codebase navigation (8 questions, 2 points each)

**C1.** App code needs `Stateful`/`StateProperty`. Which module is it supposed to import them from, and why does that module exist instead of importing `statekit` directly?

**C2.** In `src/LevityDash/lib/plugins/builtin/OpenWeatherMap.py`, the schema contains:

```python
'dataMaps': {
	'weather': {'realtime': ()},
},
```

What does the empty tuple mean here, and why does it make sense for this particular plugin's API response shape?

**C3.** What job does `MultiSourceContainer` (`lib/plugins/dispatcher.py`) do, and what does it mean for a key to be "anonymous" in this system?

**C4.** The config supports `[Backend] mode = loopback`, but there is also a `LEVITYDASH_BACKEND_MODE` environment variable that overrides it. Why does the environment override need to exist — what about *when* the relevant object is constructed makes the config file alone insufficient for programmatic use (e.g. from a test)?

**C5.** What problem do `startTimerSafe`/`stopTimerSafe` (`lib/utils/shared.py`) solve, mechanically — what do they check and what do they do in each case? Name at least two modules that call them.

**C6.** Per `AGENTS.md`: after finishing a task on your own branch, what exactly are you supposed to do with it, and what are you never supposed to do — even locally? Where does this clone's `origin` point?

**C7.** What does the `unwired` pytest marker mean in this repo, and what happens to a test carrying it?

**C8.** The repo contains `docs/source/` (Sphinx files). What is its status, and how would you find that out without asking anyone?

---

## Section D — Trace and reasoning (3 questions, 5 points each)

**D1.** Trace the path of a single realtime value — say, outdoor temperature from the Open-Meteo plugin — from the moment the HTTP response arrives to the moment the number changes on screen in a `Realtime` text panel. Name each major hop (class/mechanism) the value passes through and which thread each hop runs on where relevant. You don't need line numbers; you do need the actual class names in order.

**D2.** On startup with a graph-containing dashboard, the console prints a burst of `QBasicTimer::start: Timers cannot be started from another thread` warnings that stops once the dashboard finishes populating. With a clock-only dashboard, there is no burst. Explain: (a) why the burst correlates with graph dashboards and asynchronous data arrival, (b) why the app still works despite it, and (c) which documented design decision in `docs/roadmap.md` is expected to eliminate this class of bug, and why it does.

**D3.** This codebase has an "off-thread painting" rule: worker threads may paint into a `QImage`, but every read of the scene graph must be resolved to plain values on the GUI thread *before* the work is handed to a `Worker`. Explain why the resolve-before-handoff step is necessary (what goes wrong without it), and describe how `Graph.py`'s render path implements the pattern.

---

## Section E — Micro-task (15 points)

Execute the following small task, exactly per the workflow in `AGENTS.md`.

**Task: golden-fixture schema tests for the PirateWeather plugin.**

`tests/plugins/test_openweathermap.py` established the pattern: a captured, realistic API response tested against the plugin's data-shaping — no network, no full `Plugin` bootstrap. Extend that idea to `src/LevityDash/lib/plugins/builtin/PirateWeather.py`. Note that unlike OpenWeatherMap, PirateWeather has **no `normalizeData`** — its shaping is entirely schema-driven, so your tests validate the `schema` dict against a realistic response shape.

Deliver `tests/plugins/test_pirateweather.py` containing at least:

1. A realistic, sanitized PirateWeather API response fixture (the `currently` block at minimum — consult https://pirateweather.net/ docs or infer the shape from the schema's `sourceKey`s).
2. A coverage test relating the fixture's keys to the schema's `sourceKey`s — the regression class to guard against is "a key arrives that the schema can't resolve." Choose the direction(s) of the check deliberately and justify the choice in a comment.
3. A sparse-response test: many API fields are conditional (no precipitation, calm wind). Show that partial data doesn't break the relationship your coverage test asserts.

Constraints:

- Follow the repo's conventions (indentation style, test layout) — discover them, don't assume.
- Work on a branch as `AGENTS.md` prescribes; finish with the branch pushed and a clean working tree.
- The full test suite must pass: `poetry run pytest`.
- Stay in scope: touch nothing outside the new test file. If your tests reveal what looks like a real bug in the plugin or schema engine, **report it in your summary instead of fixing it**.

When done, report: branch name, files added, test results, and anything you flagged.

---

*End of Tier 2. Total: 46 points (C: 16, D: 15, E: 15).*
