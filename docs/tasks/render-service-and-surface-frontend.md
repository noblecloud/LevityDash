# Render service → surface-pushing frontend

**Status:** **step 1 shipped 2026-07-27** (`devtools/render_service.py`); step 2
is still a design note. Recorded 2026-07-27.

Author's framing: *"a lil service that runs in the background that keeps things
warm rather than creating a fresh instance"* and *"a backend that does the
rendering and the frontend just updates the surfaces or is just one static image
all together."*

**These are the same thing at two scales.** A warm render service is a dev
convenience that pays for itself immediately; it is also, structurally, the
prototype of a server-side-rendering backend. Build it as step one and the
architecture question becomes an increment rather than a rewrite.

## Why this is unusually cheap here

Most projects proposing server-side rendering have to invent dirty-tracking and
a per-region render path. This codebase already has both:

| needed | already exists |
|---|---|
| render one item to an image | `RendererScene.renderItem` (`PySide/utils.py`) |
| render an arbitrary region | `devtools/_boot.render_rect` |
| know what changed | the Qt scene graph's own dirty/update mechanism |
| push per-source updates to a client | `lib/wire/` — server, client, codec, messages |
| a client that reconnects and replays | `RemoteConnection` + `WireServer._latest` |

So the work is mostly *connecting* things, not inventing them.

## Step 1 — the warm render service ✅ shipped

`devtools/render_service.py`, on `127.0.0.1:8670`. Endpoints came out as
proposed (`/render`, `/render/<name>`, `/items`, `/reload`) plus `/health` and
`/status` for parity with `backend_watch.py`.

**Measured:** ~85ms per full 1800×1015 render, ~52ms for a single item at 3×,
against ~6s of boot for a one-shot `render_dashboard.py` run (9.5s wall). So
roughly a 70× improvement on the iterate-on-a-layout loop.

**Verified** as the section below proposed — same dashboard through the service
and through `render_dashboard.py`: identical dimensions and pixel-identical
layout, type and spacing. A byte-diff is *not* achievable and shouldn't be
expected: the clock advances and live values move between two renders, so ~5% of
sampled pixels differ for legitimate reasons.

**Surprise worth keeping:** the `QGraphicsEffect` caveat is a *cold*-render
problem, not a `scene.render()` problem. The moon's glow renders flat in a
one-shot render but correctly through the warm service — the effect has had time
to initialise. That makes the warm service the more faithful renderer, and it
also removes the main worry this approach carried for step 2 (see the effects
bullet below, now substantially less scary).

Threading came out as designed: aiohttp on its own thread, Qt on the main thread
running `exec()`, renders marshaled across by queued signal — the same two-hop
shape as `RemoteBackend.handle_ts_request`, deliberately not a second idiom.

Tests (`tests/devtools/test_render_service.py`) cover the routing/argument
contract against a stand-in renderer via aiohttp's `TestClient`; they never boot
Qt, since a 6s boot per test is the exact cost this tool exists to remove.

### Original design notes

A long-lived process holding a booted, loaded dashboard, exposing "render this
and give me a PNG."

Today every render pays ~6s of boot (`_boot.boot`: init, `load_dashboard`,
settle). Iterating on a layout means that cost per look, which is why design
sessions drift toward changing several things at once — and then you can't tell
which change did what.

**Shape:** reuse the watcher's pattern (`devtools/backend_watch.py`) — aiohttp
on a local port, JSON status, plus:

- `GET /render?w=1800&h=1090&scale=1` → full dashboard PNG
- `GET /render/<name>?scale=3&pad=8` → one named item (see `render_widget.py`)
- `GET /items` → the addressable names, as `--list` does
- `POST /reload` → re-read the `.levity` without re-booting Qt

**Design notes / traps already known:**

- **Rendering must happen on the Qt thread.** `scene.render()` touches the scene
  graph. Marshal from the aiohttp thread the way `RemoteBackend.handle_ts_request`
  does — `_QtInvoker` + a future — rather than rendering off-thread.
- **Resize after `load_dashboard`,** which restores a saved geometry and will
  otherwise silently clobber it. This cost a debugging round already; see
  `_boot.boot`.
- **`QGraphicsEffect`s don't composite through `scene.render()`** — the moon's
  glow renders flat. Fine for layout, not for effects. If effects ever matter,
  that's a real limitation of this whole approach and needs solving here.
- A changed `--size` changes *layout*, not just output scale, so treat size as
  part of the render request rather than a fixed property of the service.

## Step 2 — surfaces over the wire

The frontend stops laying anything out. It receives images and blits them.

Two modes, both worth supporting:

**a) Single frame.** The service sends one composited image per update. Dead
simple; the client is `while True: draw(recv())`. Right for an e-ink panel, a
tiny SBC, or a "just show me the board" web page. Costs a full frame per update.

**b) Per-surface deltas** — the author's *"updates the surfaces"*, and the
interesting one. Each panel/item is a surface. When an item's value changes,
only that item re-renders and only that surface is pushed.

```
surface_update  { id, rect: [x,y,w,h], z, format: 'png', bytes }
surface_remove  { id }
frame_config    { width, height, scale, background }
```

A wind reading changing pushes a ~130×295 region, not 1800×1015. That's the
difference between "viable over wifi to a Pi" and not.

**Why this fits:** it maps onto the existing update flow. `RemoteBackend`
already fans out per-source changes; a surface push is the same shape with an
image instead of a value. `WireServer._latest` already replays state to late
joiners — surfaces need exactly that, or a reconnecting client shows a blank
screen until something happens to change.

## How this relates to baked layout

The roadmap carries a *"fixed"/baked layout mode* note — ship resolved rects and
font sizes so a thin client draws strings at known coordinates without
`Groups.py`.

Surface pushing is **strictly lighter**: the client doesn't draw text at all, so
it needs no font matching, no text shaping, no layout engine — just a blit.

They aren't rivals, and the choice is about where the tradeoff bites:

| | baked layout | surfaces |
|---|---|---|
| client must | draw text, load fonts | blit images |
| bandwidth | tiny (values only) | moderate (image deltas) |
| fonts must match | yes — a missing font wrecks it | no |
| client can restyle/scale | somewhat | no, server decides |
| effects/gradients | client must implement | free, already rendered |

Baked layout suits a client that *can* draw and wants low bandwidth. Surfaces
suit a client that can barely do anything. A Pi-class board could take either;
an e-ink badge or a microcontroller can only take surfaces.

## Open questions — decide before building step 2

- **DPI and scale.** The server picks the raster size, so it needs to know each
  client's resolution and pixel ratio. That belongs in a client hello, alongside
  the existing wire handshake.
- **Update rate.** Values change every few seconds; re-rendering a surface per
  change is fine, but a graph animating is not. Needs coalescing, probably the
  same render-coalescing the Graph pipeline already does.
- **Format.** PNG is easy and lossless but slow to encode; raw ARGB is fast and
  large; WebP splits the difference. Measure before choosing — encode time on
  the *server* may matter more than bytes on the wire.
- **Does interactivity die?** For a HUD, mostly fine. But the current frontend
  supports editing/dragging panels, and that cannot survive a pixel-only client.
  Likely answer: surfaces are a *display* mode, and editing stays with the full
  Qt frontend.
- **Multiple clients at different sizes** means multiple render targets, so the
  service holds N scenes or re-renders per client. Cheap for two, not for twenty.

## Verification

Step 1 is easy to prove: render the same dashboard through the service and
through `render_dashboard.py` and diff the PNGs — they should be identical, and
the service should answer in milliseconds after the first boot rather than ~6s.

Step 2 wants a throwaway client: a page or a script that opens the socket, blits
what it receives, and shows nothing else. If that can display a live dashboard,
the architecture works. Resist building a good client first — the point is to
find out whether a *bad* one is sufficient.

## Suggested branch

`feat/render-service`

## Related

- `src/LevityDash/devtools/_boot.py`, `render_dashboard.py`, `render_widget.py`
- `src/LevityDash/lib/wire/` — the existing protocol to extend
- `docs/roadmap.md` → Long-term vision → baked layout note
- `.claude/skills/levity-dashboard-design/` — the design side of the same work
