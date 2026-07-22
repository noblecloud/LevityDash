
LevityDash runs in two modes: `live` (default, one process) or `remote` (Qt frontend attaches to a standalone backend over WebSocket).

### Live mode

Everything in one process — simplest for daily desktop use.

```bash
poetry run LevityDash
```

### Remote mode

Two processes: a headless backend (plugins + data pipeline) and the Qt frontend.

Start the backend:

```bash
poetry run LevityDash-backend
```

In your config (`config.ini`), set the frontend to remote mode:

```ini
[Backend]
mode = remote
```

Then launch the frontend as usual:

```bash
poetry run LevityDash
```

The backend serves all built-in plugins and can support multiple frontends simultaneously.

