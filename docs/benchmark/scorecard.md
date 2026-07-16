# Benchmark Scorecard

One column per candidate model. Grade against `ANSWER-KEY.md` (local-only, gitignored — if that file is missing, ask Fable to regenerate it before grading).

| Item | Dimension | Max | Model: ______ | Model: ______ | Model: ______ |
|---|---|---:|---|---|---|
| 0.1 project identification | Basic comprehension | 3 | | | |
| 0.2 startTimerSafe | Basic comprehension | 3 | | | |
| 0.3 IgnoreOr sentinel | Basic comprehension | 3 | | | |
| 0.4 .levity clock block | Basic comprehension | 3 | | | |
| **Tier 0 total** (gate: ≥8; excluded from grand total) | | **12** | | | |
| A1 timer affinity | Comprehension | 2 | | | |
| A2 import legality | Comprehension | 2 | | | |
| A3 encoder leak | Comprehension | 2 | | | |
| A4 YAML hex | Comprehension | 2 | | | |
| A5 conftest env | Comprehension | 2 | | | |
| A6 derived dewpoint | Comprehension | 2 | | | |
| **Section A subtotal** | | **12** | | | |
| B1 ScheduledEvent race | Bug hunting | 5 | | | |
| B2 getOrSet rebind | Bug hunting | 5 | | | |
| B3 k/key shadowing | Bug hunting | 5 | | | |
| B4 dead timestamp | Bug hunting | 5 | | | |
| **Section B subtotal** | | **20** | | | |
| **Tier 1 total** (gate: ≥22) | | **32** | | | |
| C1 stateful facade | Navigation | 2 | | | |
| C2 dataMaps tuple | Navigation | 2 | | | |
| C3 MultiSourceContainer | Navigation | 2 | | | |
| C4 backend-mode env | Navigation | 2 | | | |
| C5 startTimerSafe | Navigation | 2 | | | |
| C6 AGENTS.md workflow | Navigation | 2 | | | |
| C7 unwired marker | Navigation | 2 | | | |
| C8 docs/source status | Navigation | 2 | | | |
| **Section C subtotal** | | **16** | | | |
| D1 value trace | Trace/reasoning | 5 | | | |
| D2 QBasicTimer burst | Trace/reasoning | 5 | | | |
| D3 off-thread painting | Trace/reasoning | 5 | | | |
| D4 StatefulMetaclass semantics | Trace/reasoning | 5 | | | |
| **Section D subtotal** | | **20** | | | |
| E branch workflow | Task execution | 3 | | | |
| E conventions | Task execution | 3 | | | |
| E suite green | Task execution | 5 | | | |
| E scope discipline | Task execution | 2 | | | |
| E test quality | Task execution | 2 | | | |
| **Section E subtotal** | | **15** | | | |
| **Tier 2 total** | | **51** | | | |
| **GRAND TOTAL** | | **83** | | | |

## Dimension rollup

| Dimension | Max | Model: ______ | Model: ______ | Model: ______ |
|---|---:|---|---|---|
| Basic comprehension (Tier 0, gate only) | 12 | | | |
| Comprehension (A) | 12 | | | |
| Bug hunting (B) | 20 | | | |
| Navigation (C) | 16 | | | |
| Trace/reasoning (D) | 20 | | | |
| Task execution (E) | 15 | | | |

Bands: ≥66 trust with briefs unsupervised · 50–65 useful with review · 33–49 QA-only · <33 pass.
