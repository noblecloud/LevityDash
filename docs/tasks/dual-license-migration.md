# Dual-license migration (currently plain MIT — the planned change never landed)

**Status:** open. **Urgency: do before accepting any outside human contribution** —
today the maintainer is the sole human copyright holder (agent commits are
directed tools), so relicensing is a unilateral decision; after external
contributors it requires CLAs/permission-chasing.

## Facts
- LICENSE.txt, pyproject `license = "MIT"`, and the README badge are all MIT.
- Versions already published under MIT remain MIT permanently; only future
  releases can carry the new license.
- MIT cannot anchor dual licensing (nothing left to sell). Viable anchors:
  **AGPL v3 + commercial** (the Qt/Grafana model — apt, given the Qt stack) or
  **source-available** (BSL 1.1 / FSL, converts to open after N years).

## The task (decision first, mechanics second)
1. Maintainer picks the model — recommend getting one hour of an actual IP
   lawyer's time; this doc is not legal advice.
2. Mechanics once chosen: replace LICENSE.txt (+ commercial-license contact
   stub), update pyproject `license`, README badge + a "Licensing" section,
   per-file headers if the chosen license expects them, note in docs site.
3. Consider a CLA/DCO requirement at the same time so future outside
   contributions don't re-block step 1 ever again.

## Context for the "why"
The business model is deployable metrics dashboards + sold data streams +
software licensing (weather is the demo vertical). Dual licensing is the
third leg; it only works if the open license is strong enough that commercial
users need to buy out of it.
