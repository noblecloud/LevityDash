# Duplicate CategoryItem keys in `dispatcher._values`

**Status:** open, root cause not closed. No observed user-visible symptom.
**Found:** 2026-09-03, live, while verifying the Govee multi-device merge.

## The symptom

After a `mode=remote` frontend has been up ~18s against a live backend with two
Govee devices, `LevityDashboard.dispatcher._values` — a plain `dict` — holds
**more entries than it has distinct keys**:

```
len(_values)    = 95
len(set(keys))  = 91      # and on a later run: 95, i.e. it varies
```

Four key strings appear twice, always the same four, always `#bedroom`, never
`#terrarium`:

```
indoor.temperature.temperature#bedroom
indoor.temperature.dewpoint#bedroom
indoor.temperature.heatIndex#bedroom
indoor.humidity.humidity#bedroom
```

`indoor.rssi.rssi#bedroom` and `indoor.battery.battery#bedroom` are *not*
duplicated. The four affected keys are the ones the loaded dashboard references.

Impact today is limited: `_values[a] is _values[b]` is True, so lookups return
the same container and no wrong data reaches the screen. It inflates iteration
and `len()`, and it is a corrupted dict — a latent correctness risk for anything
that walks keys or reasons about identity.

## What is established

A plain dict cannot hold two keys that are `==` with equal `hash()`. So at the
moment the second was inserted the pair must have differed, and they became
equal afterwards. `__eq__` compares `identity`, so the likely shape is: one was
inserted with `identity=None`, and its `__identity` was later set to
`'bedroom'`.

Measured facts, all reproduced:

- **The objects mutate during the run.** `len(set(_values))` was 91 on one run
  and 95 on the next, from the same script. In one probe `hasIdentity` read
  `True` on one object and `False` on the other while their raw
  `_CategoryItem__identity` attributes compared equal *in the same pass* — the
  value changed between two reads. A wire thread is decoding messages and
  constructing keys continuously.
- **`__init__` re-runs on interned instances.** `__new__` returns a cached
  instance, and Python still calls `__init__` on it, which rewrote `source`,
  `__identity`, and set `__hash = None` on a key already in use as a dict key.
  Fixed (see below), but it did **not** remove the duplicates.
- **`copy`, `deepcopy` and `pickle` all bypass interning**, producing distinct
  objects. They are not the cause: the twins are `==` with equal hashes, so a
  dict merges them (verified: `len(d) == 1` after inserting both).
- **`convertToCategoryItem` (`observation.py:81`) is a no-op today.** It does
  `key.source = source or key.source`, and all five callers pass `source=None`,
  so it self-assigns and the setter normalises to the same tuple. It is still a
  landmine — it mutates a shared interned instance through a public setter that
  does not invalidate the cached hash.
- **`__id` is dead.** `__new__` does `kwargs['id'] = id` on its own local dict;
  that never reaches `__init__`, so `self.__id` is always `None`. Harmless, but
  it means `__id` cannot be used to tell instances apart.
- **`__separator` is a class attribute** that `__new__` writes whenever
  `separator is not None`. Nothing currently passes anything but `'.'`, but a
  single call with a different separator would change `str()` and `hash()` for
  *every* key in the process at once.

## What was fixed

`CategoryItem.__init__` now returns immediately if the instance is already
initialised (`categories.py`). Re-initialising a shared interned object is
wrong on its own terms — identity and source are part of the interning key, so
a re-init can only write back what is already there — and it was clearing the
cached hash of live dict keys. This is hardening; it did not close the symptom.

## Where to look next

1. Instrument `dict.__setitem__` on `_values` — subclass it temporarily and log
   `(str(key), identity, hash, id(key))` plus a stack summary on every insert.
   The two inserts for one string will show which call paths disagree.
2. Focus on the four affected keys: they are dashboard-referenced, and the
   dashboard parses its `key:` strings independently of the wire. Compare the
   key the dashboard builds against the key the wire decodes.
3. Check the wire decode path specifically — `codec.py:56`
   `decode_category_item` is `CategoryItem(value)`, and the module docstring
   already warns it is not round-trip safe for a key with `.source` set, since
   `__str__` emits a `source:path` prefix the constructor does not parse back.

## Reproducing

Boot a headless frontend in remote mode against a running backend (no local
plugins start, so no BLE is needed):

```python
os.environ['LEVITYDASH_CONFIG_DEBUG'] = '1'
os.environ['LEVITYDASH_CONFIG_SEED'] = '<real config dir>'   # read-only source
os.environ['LEVITYDASH_BACKEND_MODE'] = 'remote'
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
# LevityDashboard.init(); plugins.load_all(); app.init_app(); load_dashboard; pump 18s
v = LevityDashboard.dispatcher._values
print(len(v), len(set(v)))
```

Both env vars must be set **before the first LevityDash import** — they are read
in a class body at import time.
