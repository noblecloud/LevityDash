# Licensing

Copyright © 2022–2026 Bryan Neal Garrison

LevityDash is available under two licenses. You choose one.

1. **GNU General Public License v3.0 only** (`LICENSE.txt`). Free for anyone, personal or commercial, as long as the GPLv3 terms are met (changes and anything that includes LevityDash are released under the GPLv3 with source).
2. **A commercial license**, for use that can't meet the GPLv3 terms, such as shipping a closed-source product that includes LevityDash. The draft terms are in [`COMMERCIAL-LICENSE.md`](COMMERCIAL-LICENSE.md). Contact the author via https://levitydash.app to get one.

## Which one do I need?

| What you're doing | License |
|---|---|
| Running LevityDash at home, at work, or at a business, including your own modified copy for internal use | GPLv3, nothing to pay or publish |
| Building your own dashboards, plugins or configs and using them yourself | GPLv3 |
| Distributing LevityDash, modified or not, and publishing the full source of your version under the GPLv3 | GPLv3 |
| Shipping LevityDash inside a closed-source product or device, or distributing modifications without publishing them | Commercial license |
| Offering a hosted service built on LevityDash with the source of your changes kept private | Commercial license (see the GPLv3 and the draft terms for what counts) |

The GPLv3 is not a "noncommercial" license: companies can use LevityDash under it. The commercial license is for people who need to avoid the copyleft conditions, and you don't need it just because you're a business.

This is a plain-language summary, not legal advice. If you're unsure, ask the author or a lawyer.

## Contributing

The author holds the copyright to all code in this repository so that both licenses can be offered. By opening a pull request you agree that your contribution may be distributed under the GPLv3 and under the commercial license (that is, you grant the author a perpetual, worldwide, non-exclusive, royalty-free license to relicense it, and confirm that you have the right to submit it). You keep the copyright in your contribution. *(Draft wording, to be reviewed before outside contributions are accepted.)*

Releases published before this change (GitHub v0.2.0-beta.3 and earlier, PyPI 0.1.0b*) stay under the MIT license (`LICENSE-MIT-HISTORIC.txt`).

`unitcorn` (the units library LevityDash depends on) is licensed separately, under the LGPLv3.

## Third-party components

Dependencies keep their own licenses. The notable ones:

| Component | License | Notes |
|---|---|---|
| PySide6 / Qt (Core, Gui, Widgets, OpenGLWidgets) | LGPLv3 | Dynamically linked; keep Qt replaceable in packaged builds |
| Qt Canvas Painter (optional `renderer = canvas`) | GPLv3 or commercial Qt | A commercial (proprietary) LevityDash build must not include it without a commercial Qt license |
| skia-python (optional `renderer = skia`) | BSD-3 | |
| Border beam painters (`Modules/beam/`) | MIT, © 2026 Jakub Antalik | Notice in `beam/__init__.py` |
| govee-ble detection table (`plugins/govee/models.py`) | Apache-2.0, Bluetooth-Devices | Ported data |
| Fonts: Barlow Condensed, Nunito | SIL OFL 1.1 | `resources/fonts/*/LICENSE.txt` |
| Fonts: Roboto, Roboto Mono | Apache-2.0 | `resources/fonts/*/LICENSE.txt` |
| Icon fonts: Font Awesome Free, Material Design Icons, Weather Icons | OFL 1.1 / Apache-2.0 / OFL 1.1 | See `src/LevityDash/resources/icons/LICENSES.md` |

Weather data providers (Open-Meteo, OpenWeatherMap, PirateWeather, WeatherFlow) have their own terms of service. Check them before commercial use.
