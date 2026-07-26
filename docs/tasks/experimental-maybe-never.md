# Experimental — the "we'll probably never mess with this" list

Ideas worth recording but not worth scheduling. Nothing here is a bug, and
nothing here blocks anything.

---

## Distance-tolerant size matching

**Recorded 2026-07-26.**

`SizeGroup` currently applies one shared scale to every member of a cluster:
`scale = min(i.getTextScale() for i in aligned)`. Exact agreement.

The idea: allow members to differ *slightly* — "off juuuust a smidge" — when
they are far enough apart that no one can compare them directly. Two values
side by side must match exactly or it reads as a mistake; two values at
opposite ends of the window do not, and forcing them to agree drags both
down to whatever the most cramped one can manage.

Partly present already: `SizeGroup._clusters` partitions a tier by spatial
adjacency using `reach`, so distant items are already in separate clusters.
What is missing is the middle ground — a tolerance band rather than a hard
in-or-out, so near-neighbours match exactly and distant ones are allowed to
drift by some small percentage.

The hard part is the one that makes this experimental: **there is no way to
tell how much drift is perceptible.** It depends on viewing distance, screen
size, and what else is between the two items. Any threshold is a guess, and
a wrong guess looks like a bug rather than a design choice. Worth trying
only with a real dashboard in front of you and an honest willingness to
revert.
