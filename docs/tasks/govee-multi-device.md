# Two Govee thermometers at once (`#identity` keys)

**Status:** 2026-07-27 — `#identity` and the config/identity layer are
**done and tested**. What remains is the plugin's own data path (§"Still to
do" at the bottom): unbinding `self.name` from the device and routing each
device into its own observation.

The author has two GVH5102 thermometers. With both powered on, the data "isn't
handled very well" — because the plugin is **single-device by construction**,
not because of a key collision alone.

## Why it fails today

Four separate things, in the order data hits them:

1. **`self.name` *is* the device name.** `Govee.py` ends `__readConfig` with
   `self.name = self.config['device.name']`, and `__dataParse` opens with
   `if device.name != self.name: return`. So whichever thermometer won the
   config is the only one whose advertisements get past the door. The second
   device is dropped before any key is built.
2. **`get_device_observation()` is never called from anywhere.** `__dataParse`
   ends with `self.realtime.update(data)` — one shared realtime observation for
   the whole plugin, so even past the guard both devices would write into the
   same containers.
3. That method also contains a **no-op statement** — a bare `(self, device)`
   expression where something like
   `self.devices_observations[device] = obs` was clearly intended. It is
   unfinished, not merely unused. **Leave it in place** — it's the seed of this
   feature (cf. Grid.py's preserved snap-to-grid WIP).
4. **The schema only device-scopes battery and rssi** (`indoor.@deviceName.battery`).
   `indoor.temperature.temperature` and `indoor.humidity.humidity` have no
   device component at all — precisely the values that matter.

## Identity anchors on the advertised name

Confirmed against both real devices (scan, 2026-07-27):

| advertised name | address | reading |
|---|---|---|
| `GVH5102_527D` | `76270FCE-FFB6-E857-54B3-48FA6B868D48` | 23.26 °C, 62.6 % (terrarium) |
| `GVH5102_6736` | `3A092DB0-D44A-91AC-6C1B-4C9C11A8A7A4` | 22.45 °C, 47.7 % (room) |

- Names are **model + last 4 of the MAC**, so they're unique and stable.
- ⚠️ **The address is a macOS-generated UUID, not a hardware MAC.** macOS
  randomises it per machine, so a config keyed on address would not survive
  moving to another Mac, let alone a Pi. Use it only as a same-machine
  tiebreaker.
- ⚠️ `device.uuid` in the current config is the **service** UUID
  (`0000ec88-…`), identical on every Govee. It identifies nothing.

## Config shape (agreed)

```ini
[plugin]
enabled = True
; GVH5102 defaults, inherited by every device below
temperature.slice = [4:10]
temperature.expression = val / 10000
humidity.slice = [4:10]
humidity.expression = payload % 1000 / 1000
battery.slice = [10:12]

[device:bedroom]
name = GVH5102_6736

[device:terrarium]
name = GVH5102_527D
address = 76270FCE-FFB6-E857-54B3-48FA6B868D48   ; optional tiebreaker
```

The section header **is** the human-readable identity, and lands in keys as
`indoor.temperature.temperature#bedroom`.

Why sections rather than a flat `[devices]` name→alias map:

- **Per-device parser overrides come free.** A GVH5075 needs different byte
  slices, and the plugin's own description promises compatibility "with any
  Govee BLE thermometer by adjusting the payload parser in the config". A
  device just overrides `temperature.slice` and inherits the rest.
- The file reads as a list of real devices rather than a lookup table.
- **Backward compatible:** an existing flat `device.name` under `[plugin]` is
  one unnamed device — migrate it into `[device:<its name>]` on first load so
  current configs keep working.

**No alias configured ⇒ identity falls back to the advertised name**
(`#GVH5102_6736`), so two thermometers work out of the box and aliasing is a
readability upgrade, not a requirement.

## Landed: `#identity` on `CategoryItem`

`categories.py` now carries an `identity` alongside `source`, separated by
`#` (not `@`, which is a registered wildcard used for schema placeholders
like `@deviceName`):

```python
CategoryItem('indoor.temperature.temperature#bedroom').identity  # 'bedroom'
key.withIdentity('garage')      # scope a key to a device
key.withoutIdentity             # the 'any device' form
```

Semantics: **source is reconciled, identity never is.** Two sources for one
key merge into a single value; two identities are different values. So
identity participates in equality and hashing, and an unqualified key is not
a stand-in for a qualified one — callers wanting "any device" ask via
`withoutIdentity`.

Three things that needed care, each now covered by a regression test:

- **`#` must be split before the atom regex.** `#` is outside the atom
  character class, so a naive parse silently drops the separator and leaves
  the identity as an extra path segment (`a.b#bedroom` → `('a','b','bedroom')`).
- **Identity is part of the `__existing__` interning key.** `CategoryItem`
  caches instances by `hash((*atoms, *source))`; without identity in that
  tuple, `…#bedroom` and `…#terrarium` would be *the same object*.
- **Rebuilds must carry it through.** `anonymous` and `replaceVar`
  reconstruct the key and would otherwise drop identity silently.

## Landed: `__ne__` was bypassing `__eq__` entirely

Found while testing the above, and it **predates identity**. `CategoryItem`
subclasses `tuple`, and tuple supplies its own `__ne__`; Python only derives
`__ne__` from `__eq__` when the base class doesn't provide one. So `!=` was
doing an element-wise tuple comparison that ignored **source and identity**,
and `a == b` / `a != b` could both be False simultaneously — two keys from
different sources included. Fixed with an explicit `__ne__`.

## Landed: config device sections

`parse_device_sections`, `resolve_device_identity`, `device_scoped_key` in
`Govee.py`, all pure functions of config + advertised name, so they test
without a Plugin bootstrap. Legacy flat `device.name` under `[plugin]` is
surfaced as a single device aliased to its own advertised name, so the
shipped single-device `Govee.ini` keeps working untouched.

## Acceptance tests

`tests/plugins/test_govee.py` — real captured advertisements, not invented
bytes. Pins the shipped GVH5102 slices against both payloads, with a guard
that the two fixtures genuinely differ (otherwise the multi-device tests
could pass vacuously), plus identity resolution and device-section parsing.
`tests/plugins/test_categories.py` covers `#identity` and the `__ne__` fix.

⚠️ These were written first as `xfail(strict=True)` and flipped to passing
once implemented — strict is what made them announce themselves rather than
sit around as stale xfails.

## Also landed earlier

**`CategoryWildcard` was returning the string `'None'` for every wildcard** — a
walrus in `__new__` rebound `value` to `None` before it was used as both the
dict key and the string contents. So `str(CategoryItem('a.*.b'))` was
`'a.None.b'`, the registry grew a spurious `None` entry, and `hasWildcard`
never matched, meaning the wildcard branches in `observation.py:1445` and
`schema/__init__.py:689` **had never once fired**. Masked because
`CategoryWildcard.__eq__` returns True between any two wildcards. Fixed; 218
tests still pass. This had to come first — `#identity` matching builds directly
on wildcards.

## Confirmed: separate observations are NOT needed

Verified 2026-07-27 by reading the substitution path rather than assuming.
`schema/__init__.py:236` resolves a key's `@var` atoms from **that datagram's
own** `sourceData`/`metaData` (`findVar`) and rewrites the key with
`replaceVar`. `__dataParse` already puts `deviceName` in every result dict and
the schema marks `@deviceName` as `sourceData`, so substitution happens
per-advertisement.

So a single shared `self.realtime` can hold both devices under distinct keys.
`get_device_observation` / `devices_observations` — the half-built
per-device-observation route — is **not required** for this, which removes the
deepest part of the original plan.

⚠️ **But `@deviceName` substitutes a path *segment*, not an identity.** Using
it directly renames `indoor.temperature.temperature` to
`indoor.GVH5102_527D.temperature`, which breaks any dashboard pointing at the
old key — including the author's current one. Two options:

1. **Attach identity in the datagram path** (preferred): keep the key shape and
   add `#<alias>`, so `indoor.temperature.temperature` keeps existing and
   `…#terrarium` appears alongside. Needs a new hook parallel to `replaceVar` —
   `device_scoped_key` already exists to do the attaching, it just isn't called
   from anywhere in the datagram path yet.
2. Use `@deviceName` and migrate the dashboard. Cheaper to implement, breaks
   existing `.levity` files, and gives ugly key names unless aliases are also
   substituted.

## ⚠️ OPEN BUG: scoped keys never leave the backend

Both thermometers reach the observation — the control plane reports
`GVH5102_6736: keys=9` — but **`lastPublish=None`**: nothing is ever
published, so a `mode=remote` frontend shows blank Indoor *and* Terrarium
panels while the network plugins update normally.

Backend log (2026-07-27 12:33):

```
indoor.temperature.temperature#terrarium was not found in
    {timestamp: {...}, indoor: {}}
GVH5102_6736:indoor.temperature.temperature#terrarium: failed to encode for
    wire push, skipping this key: AttributeError("'NoneType' object has no
    attribute 'get'")
```

Chain: `RemoteBackend._on_published` calls `encode_container(plugin[key])`;
`Plugin.__getitem__` falls off the end and returns **None** for a scoped key
(neither the `item in self` nor the endpoint branch matches);
`encode_container(None)` raises; the per-key `except` skips it; every key
skips, so `updates` is empty and the method returns **before** recording
`lastPublish`.

**Root cause: there is a second schema lookup that does not strip identity.**
`Schema.getUnitMetaData` was fixed (which is why values reach the observation
at all — 9 keys), but the containment/lookup path used by
`Plugin.__contains__` → `item in endpoint` → schema resolution has its own
"not found" site at `schema/__init__.py:738` (the wildcard-match branch,
~L689–738) that still sees the raw `…#terrarium` key.

Fix direction: strip identity at that lookup too — ideally factor a single
`_base_key(key)` helper used by every schema lookup, rather than a third
ad-hoc `withoutIdentity` call. Note the log's `indoor: {}` — worth confirming
which `Schema` instance is being consulted there, since an empty `indoor`
subtree suggests it may not be the plugin's fully-built schema.

Verify with: `poetry run python <scratchpad>/probe.py ws://127.0.0.1:8667/ws`
— `lastPublish` must become a timestamp, not None. The control plane is the
fastest way to see this; the backend log is the second.

## Still to do — the plugin's data path

Nothing below is designed away; it's the four root causes at the top, and
none of it is touched yet:

1. **Unbind `self.name` from the device** so `__dataParse`'s
   `device.name != self.name` guard stops dropping the second thermometer.
   The plugin's name should be `Govee`; the device is a separate axis.
2. ~~**Route per device** via `get_device_observation()`~~ — **not needed**,
   see the section above; per-datagram var substitution already separates the
   devices within one observation. Leave the half-built code alone regardless.
3. **Scope the schema keys** — temperature/humidity/dewpoint/heatIndex need
   identity attached at update time via `device_scoped_key`.
4. **Scanner setup** must accept several devices rather than one
   `device.id`.

## Still open, unrelated to the above

- **`str()` round-trip is broken for sourced keys.** `source='WeatherFlow'`
  is exploded character-by-character by the `source` setter
  (`isinstance(value, Iterable)` catches `str`), yielding
  `W:e:a:t:h:e:r:F:l:o:w:…`. CLAUDE.md documents that round-trip as the
  contract. Identity round-trips correctly; source does not.
- How an unqualified `indoor.temperature.temperature` resolves when several
  identities exist — a configured default device, or ambiguous-and-loud.

## Testing without Bluetooth

Develop against stand-in devices driving `__dataParse`; it's deterministic and
runs in CI. Live BLE is only for capturing real advertisement shapes, and
**cannot run from Claude Code's shell at all** — launch via osascript → iTerm
(see the memory note; the nested `claude-code` helper bundle lacks
`NSBluetoothAlwaysUsageDescription`, so macOS SIGABRTs the process before any
permission check).

## Suggested branch

`feat/govee-multi-device`
