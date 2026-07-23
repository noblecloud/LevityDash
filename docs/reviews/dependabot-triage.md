# Dependabot alert triage

*2026-07-22. 109 open alerts (2 critical, 30 high, 50 moderate, 27 low) as of GitHub's last scan, across 20 unique packages — all flagged via `poetry.lock`, none via a hand-written `pyproject.toml` constraint. Fetched via `gh api repos/noblecloud/LevityDash/dependabot/alerts --paginate`.*

None of the 20 flagged packages are imported anywhere in LevityDash's own source (`grep -rn "^import <pkg>\|^from <pkg>" src` came up empty for every one) — everything below is a dependency of a dependency (mostly `python-semantic-release`, `twine`, `pyinstaller`, `sentry-sdk`, `sphinx`/`numpydoc`, `pytest`), with one exception: `aiohttp`, which *is* a direct top-level dependency and the transport library the wire protocol (`lib/wire/`) is built on.

## Already resolved — no action needed

Either already at (or past) the patched version, or no longer even present in the dependency tree. These should self-clear on GitHub's next rescan.

| Package | Alerts | Status |
|---|---|---|
| `msgpack` | 1 (high) | Locked at `1.2.1`, exactly the patched version. |
| `pyinstaller` | 2 (high) | Locked at `6.21.0`, already well past both patched versions (`5.13.1`, `6.0.0`). |
| `bleach` | 2 (medium, low) | Not present in `poetry.lock` anymore. |
| `flask` | 2 (low, high) | Not present in `poetry.lock` anymore. |
| `future` | 1 (high) | Not present in `poetry.lock` anymore. |
| `memray` | 1 (low) | Not present — was in the now-removed `profiling` dependency group. |
| `werkzeug` | 9 (medium×6, high×2, low×1) | Not present in `poetry.lock` anymore. |

**18 alerts, zero action.**

## Bumped — safe, transitive-only, verified

All pulled in transitively by dev/build tooling with wide-open version constraints — nothing in LevityDash's own code touches their APIs, so the only real risk was "does it still resolve and build," not "does our code break." Bumped via `poetry update <package>`, then `poetry install`, `poetry run pip install -e . --no-deps` (dependency churn unlinks the editable install — the documented gotcha, not a bump-induced regression), `poetry run pytest` (154 passed, 1 skipped — unchanged from before), and a live boot smoke test. All clean.

| Package | Was → Now | Alerts cleared | Pulled in by |
|---|---|---|---|
| `cryptography` | 41.0.7 → 49.0.0 | 13 (high×5, low×4, medium×4) | `secretstorage` (`>=2.0`, wide open) |
| `gitpython` | 3.1.40 → 3.1.54 | 9 (high×6, medium×1, critical×2) | `python-semantic-release` (`<4`) |
| `idna` | 3.6 → 3.18 | 2 (medium×2) | `requests`, `yarl` |
| `jinja2` | 3.1.2 → 3.1.6 | 5 (medium×5) | `sphinx`, `numpydoc` |
| `pygments` | 2.17.2 → 2.20.0 | 2 (low, medium) | `pytest`, `sphinx`, `rich`, `readme-renderer` |
| `requests` | 2.31.0 → 2.32.5 | 3 of 4 (medium×3) — see note below | `python-semantic-release`, `pirateweatherlib`, `python-gitlab`, `logtail-python`, `twine`, `sphinx` |
| `sentry-sdk` | 1.39.1 → 1.45.1 | 2 (low, high) | Direct optional dependency (`monitoring` extra); `^1.29.2` pin already permitted this — no constraint change needed. One direct call site (`lib/log.py`'s `sentry_sdk.init(...)`), a stable top-level API unchanged across 1.x. |
| `setuptools` | 69.0.3 → 83.0.0 | 2 (high×2) | `pyinstaller` (build-time only, zero runtime exposure) |
| `tqdm` | 4.66.1 → 4.69.0 | 1 (low) | `twine` |
| `urllib3` | 2.1.0 → 2.7.0 | 8 (high×5, medium×3) | `requests`, `sentry-sdk`, `twine` |
| `zipp` | 3.17.0 → 4.1.0 | 1 (medium) | `importlib-metadata` (`>=0.5`) — crossed a major version; zipp's majors track dropped *old*-Python support, irrelevant on our 3.14 floor, but noting since it's more than the "patch/minor" bar this task otherwise held to |

**48 alerts cleared** (45 from the 10 fully-transitive/optional packages above + 3 of `requests`'s 4). `cryptography`'s jump (41→49) is the largest and has C/Rust build steps — explicitly re-verified `poetry install` succeeds and the full suite is green, not just that the lock resolves.

**`requests` note:** one of its 4 alerts (medium, needs `>=2.33.0`) is *not* clearable by a normal bump — see the `certifi` finding below, which is the actual blocker.

## Needs a deliberate decision — reported, not bumped

- **`aiohttp`** — 40 alerts (high×3, medium×22, low×15), the single biggest chunk. Locked at `3.9.1` (pinned `^3.8.5` in `pyproject.toml`), patched versions needed range up to `3.14.1`. This is exactly the case this task's brief calls out by name: a direct dependency LevityDash uses non-trivially — the entire `lib/wire/` transport layer (`WireServer`, `WireClient`) is built on it. A jump from 3.9 to 3.14 spans real API changes (connector/session behavior, deprecated params, error-hierarchy adjustments) that could plausibly touch what `lib/wire/server.py`/`client.py` actually calls (`web.Application`, `WebSocketResponse`, `ClientSession.ws_connect`, `WSMsgType`). **Recommend**: a dedicated follow-up task — not a triage-batch bump — that bumps the constraint deliberately, checks the changelog across 3.9→3.14 against `lib/wire/`'s actual usage, and re-runs `tests/wire/` (which exercises real sockets) plus a live two-process manual check.

- **`certifi`** — 2 alerts (low, high), needs `>=2024.7.4`. **Not a transitive alert** — `certifi` is a *direct* dependency, pinned `^2022.12.7` in `pyproject.toml` (twice: line 79 in the `build`/`build-to-app` extras, line 96 in the main group), which Poetry's caret semantics resolve to `>=2022.12.7,<2023.0.0`. Checked `git log -p -- pyproject.toml`: this pin has been carried forward unchanged across every refactor since Poetry was adopted, with no commit ever explaining it — unlike `pyside6`'s pin, which the roadmap documents a concrete reason for (a 6.11-vs-6.6 breakage). This reads like a caret-operator/calendar-versioning mismatch (`certifi` has no real "breaking API," just periodic CA-bundle refreshes) rather than a deliberate security-conscious choice, but per the brief's explicit caution ("don't loosen a deliberately tightened pin — check git blame first"), I'm reporting this rather than changing it myself, especially with no stated rationale to weigh against.
  - **Concrete, demonstrable cost of leaving it**: this pin is *also* why `requests` can't clear its 4th alert above. `poetry add requests@latest --dry-run` fails with `requests (2.34.2) depends on certifi (>=2023.5.7), and levitydash depends on certifi (<2023.0.0), so requests is forbidden` — i.e. this one pin is blocking a security-relevant CA-bundle update *and* holding back an otherwise-clearable `requests` alert. **Recommend**: relax to `certifi = "^2023.7.22"` (or looser) unless there's a reason to keep 2022 specifically that isn't in the git history.

**43 alerts, flagged for follow-up rather than resolved here** (40 `aiohttp` + 2 `certifi` + 1 `requests` blocked transitively by the `certifi` pin).

## Summary

| Category | Count |
|---|---|
| Already resolved / not present | 18 |
| Bumped this pass (safe, transitive/optional) | 48 |
| Flagged for deliberate follow-up (`aiohttp`) | 40 |
| Flagged for a pin decision (`certifi`, incl. the `requests` alert it blocks) | 3 |
| Fixed (GitHub's own pre-existing state, not counted in the 109 open) | 1 |
| **Total (109 open + 1 already-fixed)** | **110** |

## What NOT touched, per the task brief

- `pyside6`/`pyside6-essentials` — not in the alert list, but noting per the brief's explicit caution: still pinned exact, deliberately, for a documented reason (see `docs/roadmap.md`).
- `multidict`/`yarl`/`frozenlist` — not in the alert list either; left untouched regardless since they were bumped specifically for Python 3.14 wheel availability, not for Dependabot reasons.
