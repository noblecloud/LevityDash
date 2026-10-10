# Govee plugin: multi-device rewrite

**Audit 2026-10-10: done.** Merged into `dev` on 2026-09-03 (`feat/govee-multi-device-rewrite`); the status below predates the merge.

**Status:** not started, 2026-08-04. Written as a handoff for a fresh session
(intended for Blackfish) — self-contained, no other context assumed.

## Why this exists

One evening's worth of debugging on `feat/plugin-control-plane` turned up four
separate Govee bugs, and all four trace back to the same root cause: `Govee`
is architecturally a plugin for *one* device, with two-device support
(`bedroom`/`terrarium`) bolted on afterward by scoping individual *values*
with an identity suffix (`indoor.temperature.temperature#bedroom`), while
everything else about the plugin — `self.name`, `running`, the scanner, the
config-driven byte parser — stays singular and gets fought over by whichever
device touched it most recently.

Bugs found and fixed in place (not blocking, just context):

1. `Plugin.loop`/`Plugin.future` are both `@cached_property`
   ([plugin.py:367-373](../../src/LevityDash/lib/plugins/plugin.py)).
   `stop()` resolves `future` permanently; every plugin's `bootstrap()`
   closure deletes `loop` on shutdown so the next `start()` gets a fresh one,
   but never deleted `future` — so after the *first* stop, ever, every later
   `start()` immediately self-terminates (`await self.future` returns
   instantly against the stale, already-resolved future). Fixed by adding
   `del self.future` next to every `del self.loop`, across all five builtin
   plugins that share this bootstrap shape.
2. `PluginsMenu._status_text`'s live-mode fallback did a bare `len(plugin)`
   in a `try/except`, hardcoding `'0 keys'` on any exception — Govee defines
   no `__len__`. A working fallback chain
   (`plugin.keys()` → `plugin.containers` → `len(plugin)`) already existed
   for exactly this in `_plugin_key_count()`
   ([messages.py:195](../../src/LevityDash/lib/wire/messages.py)) but wasn't
   reused.
3. `Govee.__init_device__` had an unconditional
   `self.name = self.config['device.name']` after every device-setup path,
   overwriting the plugin's stable name with whichever device's legacy
   config happened to be sitting in the flat config section. This broke:
   the Plugins-menu status in `mode=remote` (the frontend's never-started
   local Govee object stays `'Govee'`, but the backend's snapshot reported
   the renamed value, so `connection.plugins.get(plugin.name)` never
   matched); the internal command-dispatch dict in `RemoteBackend.attach()`,
   keyed by the *pre*-rename name; and is the direct cause of #4 below.
   Fixed by removing the mutation — `name` now stays `'Govee'`, like every
   other plugin.
4. **Not fixed, is what this doc is about:** the log lines and the frontend
   tooltip both used `plugin.name`/`config['device.name']` to label *which*
   device produced a reading, which was always wrong with two devices behind
   one instance (previously tracked as task #19 in the session's own todo
   list). #3's fix stops it from being actively misleading, but the
   underlying "which device was this?" question still has no per-reading
   answer anywhere except the value's own `identity` field.

None of this is a reason to panic — the plugin works, data flows, the fixes
above are real and tested (`tests/plugins/test_plugin_lifecycle.py` pins #1).
But every one of these was a symptom of the same shape mismatch, and patching
symptoms one at a time is going to keep finding new ones as more devices or
device models get added. Worth fixing the shape once instead.

## What Home Assistant does (and why it's the right reference)

Home Assistant ships an official `govee_ble` integration
([home-assistant/core](https://github.com/home-assistant/core/tree/dev/homeassistant/components/govee_ble))
for the exact same device family, and its Bluetooth platform has already
solved "one shared scanner, many independently-tracked devices" as generic,
reusable infrastructure — not something each integration author reinvents.

**The pattern:**

- **One shared scanner for the whole process**, not one per integration and
  not one per device. HA's `bluetooth` component owns it.
- **A coordinator instance per device**, not per integration. Govee's
  `GoveeBLEBluetoothProcessorCoordinator` subclasses the platform's
  `PassiveBluetoothProcessorCoordinator[SensorUpdate]` and is constructed
  with one device's BLE `address` plus a device-data parser
  (`GoveeBluetoothDeviceData()`). The address-based filtering — "only feed
  this coordinator advertisements from this one device" — is handled
  *inside the base class*, not written per-integration.
  `async_setup_entry()` does, per configured device: read `address` from
  `entry.unique_id`, build a coordinator for it, call
  `coordinator.async_start()`. That's the entire per-device setup path.
- **Passive vs. active is a named, first-class distinction.** Govee sensors
  are advertisement-only (`PassiveBluetoothProcessorCoordinator` — no
  connection ever made); integrations that need to poll or connect use the
  active variant. Worth adopting the vocabulary even if not the exact
  classes: it clarifies that Govee's `BleakScanner.stop()`/`start()`
  lifecycle dance ([Govee.py:401-429](../../src/LevityDash/lib/plugins/builtin/Govee.py))
  is solving a harder problem than the device actually presents — nothing
  is ever connected to.

**What this means for the rewrite:** the "shared scanner + N per-device
handlers" split isn't bespoke work. Most of current `Govee.py`'s
`start()`/`bootstrap()`/`asyncStart()`/scanner-lifecycle machinery
(lines 367-433) is the generic 20% that should stop being
per-plugin/per-device code entirely, in favor of one shared piece. `Govee`
itself should shrink to just the parser — "these bytes, from this model,
mean this temperature" — matching HA's `GoveeBluetoothDeviceData`.

## How HA's `govee_ble` supports multiple device *models* (not just multiple physical devices)

This is the part directly answering "how to support other devices,"
distinct from the multi-instance question above. Today, LevityDash's model
support is entirely manual: the default config
([Govee.py:185-201](../../src/LevityDash/lib/plugins/builtin/Govee.py))
hand-codes byte-slice math expressions for one tested model (GVH5102) and
tells the user in `_plugin_description` to hand-adjust
`temperature.slice`/`humidity.slice`/`battery.slice` for anything else. No
model detection exists.

HA's integration depends on a separate library,
[`govee-ble`](https://github.com/Bluetooth-Devices/govee-ble) (PyPI,
MIT-licensed, `govee-ble==1.4.0` per the integration's
[manifest.json](https://github.com/home-assistant/core/blob/dev/homeassistant/components/govee_ble/manifest.json)),
which does model detection and byte parsing for ~25 model families. Its
`parser.py` has no single dispatch table — it's sequential `if` matching on,
in order: advertisement payload length, local device name substring (e.g.
`"H5074"`, `"GV5121"`), manufacturer ID, service UUID, and for the encrypted
models, fields recovered after decryption. A sample of the range it covers:

| Model family | Detected by | Payload | Notes |
|---|---|---|---|
| H5072/H5075/H5129 | name or mfr ID `0xEC88` | 6 bytes | Same family as the currently-tested GVH5102 |
| H5074 | name or mfr ID `0xEC88` | 7 bytes | Little-endian temp/humidity |
| H5100-H5108 | name variants or mfr ID `0x0001` | 6-8 bytes | One handler covers 6 models |
| H5178/H5179 | name or mfr ID `0x0001`/`0x8801` | 9 bytes | Multi-sensor (primary + remote probe) |
| H5181-H5198 | name or mfr ID/UUID | 14-20 bytes | Multi-probe thermometers, alarm temps |
| H5121-H5130 | name or decrypted `model_id` | 24 bytes | **Encrypted payload** |

`manifest.json`'s Bluetooth matchers (29 entries) are what tells HA's
central Bluetooth manager which advertisements to even hand to this
integration at all — a mix of local-name-prefix patterns (`Govee*`,
`GVH5*`, `GV5121-GV5126*`, ...) and manufacturer-ID/service-UUID pairs, all
marked `connectable: false` (passive-only, matching the "never connects"
point above).

**Two real options for the rewrite, worth deciding explicitly rather than
defaulting into one:**

1. **Depend on `govee-ble` directly.** It's MIT-licensed, already handles
   ~25 models including several that are outright hard (encrypted payloads,
   multi-probe sensor-ID mapping) that would be a lot of unglamorous work to
   reimplement and get subtly wrong. Trade-off: a new runtime dependency,
   and its data model (`SensorUpdate`, HA's `BluetoothServiceInfo`) would
   need a thin adapter into LevityDash's `Schema`/`ObservationRealtime`
   shape rather than a straight lift.
2. **Port just the detection table**, keep LevityDash's own
   config-driven `BLEPayloadParser` (slice + math expression) as the
   per-model definition mechanism, and use `govee-ble`'s `parser.py` purely
   as a reference for what byte offsets/expressions to ship as *built-in
   presets* per model (so `device.model = GVH5075` selects a known-good
   preset instead of requiring the user to hand-derive slices). Less
   capable (no encrypted-model support without real work) but no new
   dependency and keeps the existing, already-tested config surface.

Given LevityDash only has two physical devices to actually test against
right now (both in the H5072/H5075/H5102 family), option 2 — port the
detection *table*, not the whole library, and ship presets for the model
families closest to what's already working — is probably the pragmatic
starting scope, with option 1 kept as an explicit escape hatch if a future
device turns out to need encrypted-payload support. **This is a real
decision for whoever picks this up, not one I'm making here.**

## Proposed shape for LevityDash

Not a full design — enough for Blackfish to start from, structured the way
HA's module split suggests:

- **A generic BLE-scanning base** (shared `BleakScanner`, address/name-based
  routing to whichever device wants a given advertisement, the
  start/stop/restart lifecycle that's currently duplicated per-plugin in
  five `bootstrap()` closures). Candidate home: either a mixin/base class
  near `Plugin` itself, or a new `lib/plugins/ble.py` that `Govee` (and any
  future BLE plugin) builds on rather than reimplementing.
- **One lightweight instance per configured device** instead of one `Govee`
  handling N devices via value-identity scoping. `[device:bedroom]` /
  `[device:terrarium]` config sections already are, structurally, HA's
  "config entry per device" — the gap is only that they currently feed one
  shared instance instead of spawning one each.
- **Open design question to flag, not resolve:** if each device becomes its
  own `Plugin` instance with its own `.name` (e.g. distinguishing themselves
  as separate *sources*), does the existing `identity`/`device_scoped_key`
  mechanism ([Govee.py:143-155](../../src/LevityDash/lib/plugins/builtin/Govee.py))
  become redundant for this case — since `MultiSourceContainer` already
  reconciles by *source* — or does it stay needed for some other reason?
  `CategoryItem` deliberately keeps `source` and `identity` as orthogonal
  concepts (see the `Keys` section of the repo's `CLAUDE.md`); worth
  understanding *why* before collapsing them, not assuming they're the same
  thing just because they'd coincide for Govee specifically.
- **Model support as data, not code-per-model**, using the HA table above as
  the reference for what a "preset" needs to encode (byte offsets, units,
  endianness, encrypted vs. plaintext).

## Explicitly out of scope for a first pass

- A `config_flow`-style interactive per-device setup UI — LevityDash's
  existing `@ask()`/`@askChoose()` onboarding-string config mechanism is
  good enough; this is about the runtime architecture, not the config UX.
- Encrypted-payload models (H5121-H5130 and similar) — real, non-trivial
  work (`govee-ble`'s own handling for these is the most complex part of
  its parser); punt unless a physical device actually needs it.
- Migrating away from `identity`-scoped keys before the open question above
  is actually answered.

## Verification

- Existing `tests/plugins/test_govee.py` (device-section parsing, identity
  resolution, key scoping) should keep passing basically unchanged if the
  config surface (`[device:bedroom]` etc.) is preserved — that's a good
  regression signal that the rewrite didn't silently change user-facing
  config behavior.
- `tests/plugins/test_plugin_lifecycle.py` (added this session) pins the
  `loop`/`future` cached_property reset behavior — if the generic BLE base
  absorbs that lifecycle code, the test's *intent* (fresh future/loop per
  start) should move with it, not get dropped.
- Real hardware test: both configured devices (bedroom, terrarium)
  reporting live data simultaneously, through at least one manual
  stop/start cycle each via the Plugins-menu control-plane commands, is the
  actual end-to-end proof this is fixed — that's exactly the scenario that
  surfaced all four bugs above in the first place.
