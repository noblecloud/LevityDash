# Gauge Studio: distance guides, ratio snapping and drag gearing

**Status:** done. Gearing and the wheel in #87, ratio targets and distance guides in #89, wireframe and guideline layers in the PR after it. Kept for the reasoning.

Suggested branch: `feat/studio-snapping` off `feat/value-sources`. Start this after
`fix/studio-sliders-contrast` (sliders, unit selectors, stage size and zoom, the
undo/reset fixes) has merged. Both touch `devtools/_studio_handles.py`.

## What the user asked for

> as things are being moved around, it would be awesome if it drew hairline distance
> indicators with different snapping values. the snapping values should be based on
> normal integers/fractions like normal, but also at specific design ratios like golden
> and phi, stuff like that. ideally when the value is displayed when snapped into so the
> user knows. Oh, and there needs to be a modifier key to temporary disable snapping for
> finer movements. and maybe another modifier that changes the sensitivity (bigger drags
> mean less movement/gear reduction). Also, when the modifier key is pressed, the
> scrollwheel adjusts the sensitivity. (which as it's changing the value is temporarily
> shown on the screen)

## Expected change

All of this lives in the Studio overlay (`_studio_handles.py`, plus a small module for
snap logic if it grows). Gauge.py does not change.

1. **Distance guides while dragging.** Draw hairlines (1 device px, ignoring zoom)
   between the dragged element and the things it measures against: the card edges, the
   dial centre, the arc, and other labels. Each guide shows its length as a small label.
   For angle handles, draw the arc between the handle and its reference angle and show
   the angle in degrees.
2. **Snap targets.** A drag snaps to the nearest target within a few screen pixels. The
   targets are:
   - whole numbers and simple fractions of the property's natural unit: 1/2, 1/3,
     2/3, 1/4, 3/4, 1/8, and whole percents;
   - design ratios of the reference length: golden ratio (φ ≈ 1.618 and 1/φ ≈ 0.618,
     1/φ² ≈ 0.382), √2, √3, 3:2, 4:3, 16:9, and rule of thirds;
   - for angles, multiples of 15° and 45°, and the golden angle (≈ 137.5°).
   Keep the list as data, so new ratios are a one-line addition. Show a Studio setting
   to switch each family (fractions, design ratios, angles) on or off.
3. **Show the snap.** When a drag lands on a target, highlight the guide and label it
   with the target's name and value, for example `1/φ · 61.8%` or `2/3 · 66.7%`.
4. **Snap-off modifier.** While Cmd (Ctrl on other platforms) is held, snapping is off
   and the drag moves freely. Releasing the key turns snapping back on mid-drag.
5. **Gearing modifier.** While Option (Alt) is held, the drag is geared down: the
   value moves by the drag distance divided by the gear ratio. The default ratio is 4:1.
   The gearing anchors at the point where the key went down, so the handle does not
   jump when the key is pressed or released.
6. **Scroll to set the gear ratio.** While Option is held, the scroll wheel changes the
   gear ratio (for example 1:1 to 20:1, in steps). A transient overlay near the cursor
   shows the new ratio and fades out about 1 s after the last change.
7. Shift was the "fine steps" key in Studio v2. Gearing replaces it, so free Shift for
   axis or angle constraint, or leave it unbound. Update the Studio help text and the
   `gauge_studio.py` paragraph in `CLAUDE.md`.

## Wireframe mode and guideline layers

The user also asked for "a wireframe mode with optional guidelines". It shares
geometry with the snap targets, so build both from one source: a function that
collects every element's geometry from the live gauge (dial rect, centre, track
radii, tick extents, each label's layout box and ink box, needle path, value strip,
card rect, padding, inset). Snapping reads that function, and both overlays draw it.

8. **Wireframe toggle (W).** Hide the painted gauge, or dim it to about 15%, and draw
   every element as a 1 px outline in its own colour:
   - the arc track as its centre line and its inner and outer edges;
   - each tick as its line;
   - each label's layout box solid and its ink box dashed;
   - the needle path, the pivot, the dial rect and the card rect with its padding.
   Elements that overlap are drawn red, so collisions show up without hunting.
9. **Guideline layers (G opens a menu).** Each layer switches on or off on its own,
   and the choice persists as a Studio setting:
   - centre crosshair;
   - radius circles at the track, the ticks and the labels;
   - angle rays at start, end and every 15° or 45°;
   - thirds and golden-ratio lines over the card;
   - baseline, cap height and x-height of the value text;
   - a safe-area inset.
   Guidelines draw in both normal and wireframe mode. During a drag, the guideline
   that the drag snaps to is highlighted.
10. Neither overlay changes the export or the undo stack.

## Verification

Use real runs, not new unit tests. A short test for the pure snap-target maths is fine.

- In a real window, drag the value label with snapping on. Take a screenshot mid-drag
  showing the hairlines, the distance labels and a highlighted golden-ratio snap with its
  label.
- Repeat with Cmd held, and show that the value lands between snap targets.
- Hold Option, scroll, and screenshot the gear-ratio overlay. Then drag 100 px and
  show that the value moved a quarter as far as an ungeared 100 px drag.
- Confirm that one drag is still one undo step, at any modifier state.
- Take screenshots of one gauge in wireframe mode and with all guideline layers on.
  Then set a `below` value label on a full ring, which overlaps today. Show that the
  overlap is drawn red in wireframe mode.
- Run `pytest tests -q -p no:cacheprovider` and check the result against the baseline
  of 492 passed, 1 skipped.
