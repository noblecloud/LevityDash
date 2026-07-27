# Two Govee thermometers at once (`#identity` keys)

**Status:** designed and agreed 2026-07-27, acceptance tests written and
failing. Groundwork landed; the rework itself is not started.

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

## Acceptance tests (written, currently xfail-strict)

`tests/plugins/test_govee.py` — real captured advertisements, not invented
bytes. The three `xfail(strict=True)` cases define the target API and will
error if they start passing unnoticed:

- `resolve_device_identity(name, devices)` prefers a configured alias
- …and falls back to the advertised name when unconfigured
- `device_scoped_key(...)` produces `indoor.temperature.temperature#bedroom`

The passing tests pin the shipped GVH5102 slices against both real payloads,
plus a guard that the two fixtures genuinely differ — otherwise the
multi-device tests could pass vacuously.

## Already landed

**`CategoryWildcard` was returning the string `'None'` for every wildcard** — a
walrus in `__new__` rebound `value` to `None` before it was used as both the
dict key and the string contents. So `str(CategoryItem('a.*.b'))` was
`'a.None.b'`, the registry grew a spurious `None` entry, and `hasWildcard`
never matched, meaning the wildcard branches in `observation.py:1445` and
`schema/__init__.py:689` **had never once fired**. Masked because
`CategoryWildcard.__eq__` returns True between any two wildcards. Fixed; 218
tests still pass. This had to come first — `#identity` matching builds directly
on wildcards.

## Still to design

- **`#identity` in `CategoryItem` itself.** Parser + hashing in `categories.py`,
  and the rule that an identity-bearing key is *never* merged across devices
  (unlike `@source`, which is reconciled). Note `str()`/constructor round-trip
  is currently **broken for sourced keys** — `source='WeatherFlow'` is exploded
  character-by-character by the `source` setter (`isinstance(value, Iterable)`
  catches `str`), yielding `W:e:a:t:h:e:r:F:l:o:w:…`. CLAUDE.md documents that
  round-trip as the contract. Fix alongside.
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
