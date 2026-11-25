# A band card goes missing for a whole step move, then pops in

**Status: FIXED 2026-11-25.** Branch `fix/band-step-card-appears-late` (off `dev` at `9132f1cb`).

## Symptom

Reported by the owner watching a step band (the `cards` row of the shipped OpenMeteo
template / the showcase `home` board): *"when the scrolling band switches to showing a
new card, every once in a while that card does not appear until after the scrolling band
has stopped and the card pops into the view without animation."*

One card's slot is empty for the whole `transition` (900 ms). The other cards slide
normally, and the missing card appears at its final place the instant the move ends, with
no travel.

## Cause

A step band does not move the real cards during a move. `Band._freeze()`
(`Modules/Containers/Band.py`) draws each shown card once with `renderSubtree()`
(`PySide/snapshot.py`) and sets the real card's opacity to 0, then `place()` slides the
`Snapshot` pixmaps. So a card is visible during a move **only** by its picture, and the
real card comes back in `_arrive()` → `_thaw()`. A blank picture is indistinguishable
from a missing card, and it comes back exactly when the move ends — the reported pop.

`renderSubtree` used to find the card's drawing with

```python
region = root.mapRectToScene(local)
items = [item for item in scene.items(region, IntersectsItemBoundingRect, AscendingOrder)
         if item is root or root.isAncestorOf(item)]
```

`QGraphicsScene.items(rect)` answers from the scene's BSP index, which only covers the
scene rectangle. A band card waiting its turn sits outside the band, and the card that is
about to come in sits past the right edge — outside `sceneRect` on a window the band does
not fill. For a query rect there, the index returns **nothing**, so `items` was empty,
`renderSubtree` painted into a transparent pixmap and returned it (not None, so the caller
kept it), `Snapshot` hid the real card, and an empty picture slid in.

Measured (real window, 1512x945, retina, `LEVITYDASH_FIXTURE=stormy-day`), freeze-time
inside `_freeze`:

```
('windCard', 'ok 5403', {})
('rainCard', 'BLANK', {'opacity': 1.0, 'eff': 1.0, 'items': 0, ...})
```

and headless, one card translated away from the band:

```
dx= 1200 sceneRect_x=  1229.7 query_x=  1175.4 items= 57 alpha=5475
dx= 2000 sceneRect_x=  2029.7 query_x=  1975.4 items=  0 alpha=0      <- blank
```

"Every once in a while" is the ring: only the card parked past the edge of the scene
rectangle is affected, which is one card at a time and only while it waits there.

## Fix

- `snapshot.py`: `renderSubtree` takes the subtree with `_paintOrder(root)`, a recursive
  walk of `childItems()` (an item, then its children by `zValue()`, stable, which is the
  order Qt paints siblings in). No scene index, no `region`, no `isAncestorOf` filter, and
  it is cheaper than the scene-wide query.
- `Band._stopClock()`: a move cut short (an item's `when:` changing, the band hidden, a
  reload) used to leave the ring at a fractional position — every card a fraction of a
  stride off for the rest of the lap. It now lands on the nearer whole slot and re-places
  the cards. Separable, but the same "a move that did not finish" family.

## Verification

- `tests/ui/test_band.py::test_a_picture_is_drawn_for_a_card_outside_the_scene` — a card
  translated 4000 units right of the scene must still render ink. Fails on the old
  `snapshot.py` with *"the picture of a card outside the scene came out blank"*, passes
  now.
- `tests/ui/test_band.py::test_a_move_cut_short_lands_on_a_slot` — mid-move `_stopClock()`
  leaves every card on a whole slot.
- `env -u PYTHONPATH PYTHONPATH=$PWD/src <main-checkout>/.venv/bin/python -m pytest
  tests/ui/test_band.py -q` → 15 passed.
- Live check: real window, retina, dwell cut to 3 s for the run, 15 moves sampled each
  frame — no card is ever frozen without a picture (was: a blank picture on ~half the
  moves).

## Scope / don't chase

- `tests/test_showcase.py::test_the_files_match_their_generator[atmos|tide|default|home]`
  fails on this tree and is unrelated: the generator stamps an epoch hour that differs by
  14400 s (4 h) from the checked-in file, i.e. a timezone-dependent fixture, not a band or
  snapshot change.
- `renderSubtree` still refuses (returns None) a subtree with an enabled `QGraphicsEffect`
  or one over `MAX_PIXELS`, and the band still moves those cards live. That is by design.
- Not touched: continuous mode (no snapshots), `_layout`/share arithmetic, the `band`
  docs' claim that "a step band does nothing at all between moves" (now also inaccurate
  about the pictures — corrected in `docs/config/dashboard/band.md`).

## Related

[blask-perf-plan](blask-perf-plan.md) — the frame-timing work the snapshot path came from
(`d6f8cda4`), which is the commit that introduced this.
