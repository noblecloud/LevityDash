# Licensing

Copyright © 2022–2026 Bryan Neal Garrison

LevityDash is available under two licenses:

1. **GNU General Public License v3.0 only** (`LICENSE.txt`). Free for anyone, personal or commercial, as long as the GPLv3 terms are met (changes and anything that includes LevityDash are released under the GPLv3 with source).
2. **A commercial license**, for use that can't meet the GPLv3 terms, such as shipping a closed-source product that includes LevityDash. Contact the author via https://levitydash.app.

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
