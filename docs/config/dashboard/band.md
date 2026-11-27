# Band

A band shows a row of items and scrolls through the ones that do not fit. Use it for a bottom row of cards that holds eight cards on a screen with room for four, or a column of readings that turns on its own.

```yaml
- type: band
  name: cards
  mode: step            # step (a page at a time) or continuous (a marquee)
  visible: 4            # items in view at once; 4.5 lets the next one peek in
  gap: 1.2%             # space between items, a share of the band's length
  dwell: 10s            # step: how long each stop lasts
  transition: 700ms     # step: how long one move takes
  step: 1               # step: items per move; `page` moves a whole page
  geometry: {x: 2%, y: 68%, width: 96%, height: 30%}
  items:
    - {type: group, name: wind, ...}
    - {type: group, name: rain, ...}
```

Each item is `(band - gaps) / visible` long and as tall as the band, so it needs no `geometry`; the band gives one. Put a `group` in each slot and lay its contents out in shares of that group.

## Two modes

| `mode` | What it does | Settings |
|---|---|---|
| `step` (alias `page`) | Rests for `dwell`, glides for `transition` (ease in and out), rests again. | `dwell`, `transition`, `step` |
| `continuous` (alias `marquee`) | Moves at a steady `speed` and never stops. | `speed` (items per second, `0.25` is four seconds an item), `fps`, `cache` |

`direction` is `left` (the default: content moves left and new items come in from the right), `right`, `up` or `down`. `up` and `down` make a vertical band.

## The ring

The items sit in a ring. The one that leaves one end comes in at the other, so the wrap has no seam. A band needs at least `visible + 1` items to scroll. With fewer it shows them in a row and stands still, and it costs nothing.

## Cost

The layout is worked out once, as shares of the band. A move changes only each item's own translation, so there is no geometry update and no relayout per frame. In `continuous` mode every item is drawn into a pixmap once and the pixmap is moved (`cache: false` for an item that repaints every frame anyway, such as a graph with a live edge). In `step` mode each shown item is drawn into one picture just before a move and the pictures slide, so a frame of the move is a few blits rather than a repaint of every card; the real items come back when the move ends, and a move ends early if an item's `when:` changes mid-move. Between moves a step band does nothing at all. On a slow machine, lower `fps` (15 still looks smooth at a slow `speed`) or use `step`. A band that is hidden or off the scene does not tick.

`when:` on an item of a band takes it out of the ring while it is false: it is hidden and the others close up, and it comes back in its place when the condition holds again. Use a [switch](switch.md) inside an item to change what one slot shows instead.
