# Studio

Studio is the editor for dashboard files. It shows the dashboard as it will look, a tree of its items, and the settings of the item you pick. You can edit the file with it, or with any text editor. Studio saves only what you changed, so the rest of the file stays as you wrote it.

Start it from the source folder:

```bash
poetry run python src/LevityDash/devtools/studio.py            # an empty dashboard
poetry run python src/LevityDash/devtools/studio.py FILE.levity # open a dashboard
```

Studio uses fixture data, not your sensors, so it runs without the backend or any plugin.

## The item tree

The tree on the left lists every item in the dashboard, in the order it is drawn.

- **Filter.** The box above the tree shows only the rows whose text contains what you type, with the containers around them. Clear the box to see the whole tree again.
- **Kind.** A small coloured square shows what kind of item a row is. Blue is a container (a stack, a group, a grid). Green is a display (a reading, a graph, a clock). Purple is an item that uses a preset. Grey is an item kept as written, which Studio does not edit.
- **Hover.** Move the pointer over a row, or over an item on the stage, and that item gets a thin outline on both. The outline does not select the item.
- **Menu.** Right-click a row for Copy, Paste, Duplicate, Delete, Put in group, Ungroup and Align in parent.

## Groups

- **Put in group** (Ctrl+G) wraps the selected item in a new group. The group takes the item's place, position, and `when:`, so the item stays where it was on the stage.
- **Ungroup** (Ctrl+Shift+G) replaces a group with the items inside it. A group that has its own placement must hold exactly one item, so that the item can take the placement back. Otherwise Studio says why and changes nothing.

Studio does not group the dashboard itself, or an item kept as written.

## Align in parent

The **Align in parent** submenu moves the selected item to the left, centre or right edge of its parent, or to its top, middle or bottom edge. It sets the item's `x` or `y` as a share of the parent.

## Move, copy and undo

- Alt+Up and Alt+Down move the item up or down in its parent.
- Ctrl+D duplicates the item. Ctrl+C and Ctrl+V copy and paste it.
- Delete removes the item.
- Ctrl+Z undoes the last change. Redo uses the standard redo key for your system. The undo history covers the whole dashboard.

## Zoom and pan the preview

- Hold Ctrl and turn the mouse wheel to zoom. The zoom stays on the point under the pointer. The largest zoom is 8 times.
- Drag with the middle button to pan.
- Press 0 to show the whole dashboard again.

Zoom changes only the preview. It is not saved.

## Size groups

Studio has a size groups tab. It lists each group and the labels in it. A label that names a panel which the dashboard does not have is flagged there. See [Size groups](/config/dashboard/size-groups.md).

## Layout

The Item tab has a **Layout** section with `flex` and `grid` popovers. These edit the same keys as in [Flex and grid](/config/dashboard/layout.md).
