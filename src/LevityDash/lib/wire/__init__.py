"""Wire protocol for the backend/frontend process split (Phase 4).

codec.py      - (de)serialize the value types that cross the boundary.
                 Qt-free by design - the eventual real socket client
                 (Phase 4.3) shares this module with the backend.
containers.py - RemoteContainer/RemoteSource/RemotePublisher: frontend-side
                 stand-ins for observation.Container/Plugin/Publisher.
                 Qt-allowed (they're frontend-only) and hold wire-pushed
                 state rather than owning live plugin connections. Full
                 timeseries support (.hourly/.daily/.timeseries) is
                 deferred to Phase 4.4 - see the module docstring.
bridge.py     - LoopbackBridge: proves the codec + RemoteContainer
                 round-trip in-process (Phase 4.1, `[Backend] mode =
                 loopback` / LEVITYDASH_BACKEND_MODE=loopback), ahead of
                 any real process or socket existing.
"""
