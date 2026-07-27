# A wrapper `.app` so BLE work doesn't need iTerm

**Status:** idea, not started. Recorded 2026-07-27.
**Priority:** low — there is a working workaround. This is a convenience
unlock for AI agents and anyone whose shell isn't a granted terminal.

## The problem

Bluetooth work (the Govee plugin, `devtools/ble_scan.py`, any `bleak` script)
**cannot run from Claude Code's shell**. The process dies with `SIGABRT`
(exit 134) and prints *nothing at all* — no traceback, no error.

Today's workaround is to launch through iTerm over AppleScript. It works, but
it needs a GUI terminal, spawns windows, and makes output awkward to collect.

## Root cause — read this before designing anything

macOS enforces **two independent gates** for a TCC-protected resource:

1. The OS reads the **responsible process's bundle** `Info.plist` for
   `NSBluetoothAlwaysUsageDescription`. Missing → the process is **killed
   before TCC is consulted at all**. This is a kill, not a denial, which is
   why there's no output. The crash report says
   `Termination Reason: Namespace TCC` and names the missing key.
2. *Only if that passes* does macOS consult the user's grant (the toggle in
   System Settings → Privacy & Security → Bluetooth).

Measured on this machine 2026-07-27:

| bundle | identifier | `NSBluetoothAlwaysUsageDescription` |
|---|---|---|
| `/Applications/Claude.app` | `com.anthropic.claudefordesktop` | ✅ |
| `…/Claude/claude-code/<ver>/claude.app` | `com.anthropic.claude-code` | ❌ |
| `/Applications/iTerm.app` | `com.googlecode.iterm2` | ✅ |
| pyenv `Python.app` | `org.python.python` | ❌ |

Claude Code's shell is responsible to the **claude-code helper**, which lacks
the key. Granting Bluetooth to *Claude* in System Settings does nothing: it's
a different bundle, and gate 1 kills the process before gate 2 is reached.

## Proposed fix

A minimal `.app` bundle in `src/LevityDash/devtools/` whose only job is to
declare the usage string and `exec` a Python script. Launched with `open -a`,
**it** becomes the responsible process, clearing gate 1. The user grants it
Bluetooth once at gate 2, and from then on any shell can run BLE work.

Rough shape:

```
BLEHost.app/Contents/
  Info.plist          CFBundleIdentifier, CFBundleExecutable,
                      NSBluetoothAlwaysUsageDescription, LSBackgroundOnly
  MacOS/blehost       shell script: exec "$PYTHON" "$@"
```

## ⚠️ Falsify the core assumption first — it's ~10 minutes

**Everything above rests on "a process launched via `open -a` is responsible
to that app rather than to the caller."** That is the whole idea, and it is
worth proving before building anything.

Cheapest test: build the skeleton bundle, have its script run
`devtools/ble_scan.py 5`, launch it with `open -a`, and see whether it scans
or exits 134. If it still dies, **stop** — the responsibility chain doesn't
work the way this brief assumes, and the rest of the design is void.

(A related check if it fails: `posix_spawnattr_set_disclaim_np` and
`launchctl` make a process responsible for *itself*, which would then be
`org.python.python` — also missing the key, so those routes are dead ends.
That's why a bundle *we* control is the proposal.)

## Gotchas

- **`open` detaches.** No stdout/stderr by default. Either redirect inside the
  wrapper script, or use `open --wait-apps --stdout <file> --stderr <file>`.
  The existing scripts already write to a file and poll — keep that pattern.
- **Arguments** go through `open -a BLEHost.app --args …`.
- **Sign it ad-hoc** (`codesign --force --sign - BLEHost.app`). TCC keys the
  grant to the bundle's code identity; unsigned or re-created bundles can lose
  the grant and re-prompt on every rebuild.
- **Name it clearly** — the name shows up in the user's Bluetooth privacy list
  forever. `LevityDash BLE Host` beats `blehost`.
- **Generate, don't commit, the bundle.** A `.app` is a directory; a small
  build script keeps it transparent, re-signable, and reviewable in a diff.
  It's dev-only and must never ship with the app.
- **Don't patch pyenv's `Python.app`.** Considered and rejected: it's ad-hoc
  *linker-signed*, so editing `Info.plist` breaks even that and needs a
  re-sign; it changes the user's Python globally; and a pyenv upgrade silently
  wipes it.
- **Never patch a third-party signed bundle** (Claude.app, iTerm) — it breaks
  their signature.

## Verification

1. `open -a` the wrapper running `devtools/ble_scan.py 20`; expect the Govee
   thermometers (`GVH5102_*`, service `ec88`) in the output, not exit 134.
2. Confirm the app appears in System Settings → Privacy & Security →
   Bluetooth after the first run.
3. Re-run after a rebuild + re-sign; the grant should persist (this is what
   the ad-hoc signing gotcha is about).
4. Confirm the normal app is unaffected — this is additive dev tooling and
   must not change how `LevityDash` or `LevityDash-backend` launch.

## If it works

- Document it in `CLAUDE.md`'s Bluetooth gotcha as the preferred route, with
  osascript → iTerm demoted to the fallback.
- Update the agent memory note `ble-testing-via-iterm` (it currently says
  iTerm is the only way).

## Also worth doing regardless

The real fix is upstream: **the `claude-code` helper bundle should ship
`NSBluetoothAlwaysUsageDescription`**, the way `Claude.app` already does.
Worth filing with Anthropic — it affects any BLE/hardware work from Claude
Code on macOS, and the failure mode (silent SIGABRT, no output) is
particularly hard to diagnose.

## Suggested branch

`feat/ble-launcher-app`

## Related

- `CLAUDE.md` → Gotchas → macOS Bluetooth/TCC
- [govee-multi-device.md](govee-multi-device.md) — the work that needed BLE
- `src/LevityDash/devtools/ble_scan.py` — the script to test with
