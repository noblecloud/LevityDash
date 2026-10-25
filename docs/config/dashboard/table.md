# Table

`preset: table` lays out readings as rows and columns with the labels written once: each row's label once on the left, each column's name and unit once in its head. The cells show only the number. It is a preset whose item is built from its properties, so it is used like any other preset and saves back in the short form.

```yaml
- preset: table
  geometry: {x: 4%, y: 6%, width: 92%, height: 40%}
  props:
    columns:
      - {head: Temp, unit: °F, key: 'indoor.temperature.temperature#{row}', precision: 1}
      - {head: Humidity, unit: '%', key: 'indoor.humidity.humidity#{row}'}
    rows:
      - {label: Bedroom, row: bedroom}
      - {label: Office, row: office}
```

A full example is `docs/design-references/table.levity` (scenario `house-day`).

## Properties

| Property | Meaning |
| --- | --- |
| `columns` | One entry per column: `head` (the name), `unit` (written after the name, once), `key`, `precision`, `format`, `color`. `{row}` in a `key` becomes the row's `row` name, so one key serves every row. |
| `rows` | One entry per row: `label`, `row` (the name that `{row}` takes), `keys` (one key per column, `null` for an empty cell; replaces the columns' keys for this row), `color` (of the label). |
| `labelWidth`, `headHeight` | Grid track sizes of the label column and the head row. The data columns and the other rows share the rest equally. |
| `gutter`, `rowGap` | Space between columns and between rows. Defaults are the theme sizes `$space_4` and `$space_1`. |
| `numberAlign` | `decimal` (default), `end` or `none`; see `number-align` in the dashboard reference. |
| `alignment` | `Left`, `Center` (default) or `Right`: where the heads and numbers sit in their column. |
| `titleGroup`, `valueGroup` | Size groups of the heads and row labels, and of the numbers. Defaults `global.title` and `global.value`, so the table reads like every other row on the dashboard. |
| `font` | Font of the numbers. |
| `textHeight` | One text height (such as `4.5mm`) for every head, label and number. Tables of different row heights then read at one size; without it each is fitted to its own cells, and a size group splits them into tiers by cell height. |
| `dividers` | Passed to the grid, for example `{enabled: true}`. |

Any other field on the use (`geometry`, `name`, `when`) goes to the grid. A mistake (no columns, an unknown column setting, a `{row}` key with no `row` name, `keys` of the wrong length) makes an error tile that says what is wrong.

The unit is not drawn in the cells, so a value in a column must be in the unit the head names. Keys that publish another unit show the wrong figure under the head; add a conversion to the key instead.
