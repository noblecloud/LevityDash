# Intro <!-- {docsify-ignore} -->

LevityDash is a lightweight, desktop native, fully modular, multi-source dashboard without a required web frontend. The current frontend is built on PySide6/Qt 6. A key goal of this project is to support multiple frontends and platforms, including embedded — it can easily be deployed on a Raspberry Pi or similar single board computer.

*Note: This project is in beta – it works and is used daily, but expect rough edges.*

# Quick Start <!-- {docsify-ignore} -->

> [!WARNING]
> The package on PyPI is an old 0.1.x release from the PySide2 era. Until 0.2.0 ships, install from source.

```bash
git clone https://github.com/noblecloud/LevityDash.git
cd LevityDash
poetry install --without dev
poetry run LevityDash
```

Python 3.11–3.14 is required (3.14 recommended). See [Getting Started](/getting-started.md) for details.
