#!/bin/bash
# Cloud sessions only: make the container match the dev Mac.
# Python 3.14, en_US.UTF-8 locale, WeatherUnits beside the repo, Poetry env in .venv.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
	exit 0
fi

REPO="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
PYVER=3.14

# Locale: some tests format numbers and dates for en_US.
if ! locale -a 2>/dev/null | grep -qi '^en_US\.utf-\?8$'; then
	localedef -i en_US -f UTF-8 en_US.UTF-8 2>/dev/null || true
fi

# Shared libraries PySide6 needs to import offscreen.
if ! ldconfig -p | grep -q 'libEGL.so.1'; then
	apt-get update -qq
	apt-get install -y -qq libegl1 libgl1 libxkbcommon0 libfontconfig1 libdbus-1-3 \
		libglib2.0-0 libxcb-cursor0 fonts-dejavu-core
fi

# uv: the container's copy can predate the final 3.14 builds, so keep a fresh one.
UVENV="$HOME/.cache/levitydash-uv"
if [ ! -x "$UVENV/bin/uv" ]; then
	python3 -m venv "$UVENV"
fi
"$UVENV/bin/pip" install -q -U uv
UV="$UVENV/bin/uv"
"$UV" python install "$PYVER"
PY="$("$UV" python find "$PYVER")"

# WeatherUnits is a path dependency at ../WeatherUnits (develop mode, dev branch).
WU="$REPO/../WeatherUnits"
if [ ! -d "$WU/.git" ]; then
	git clone -q https://github.com/noblecloud/WeatherUnits.git "$WU"
fi
git -C "$WU" fetch -q origin dev
git -C "$WU" checkout -q -B dev origin/dev

# Dependencies into an in-project .venv on 3.14. uv makes the venv because
# `poetry env use` falls back to the system Python in this container.
cd "$REPO"
if ! .venv/bin/python -c "import sys; sys.exit(sys.version_info[:2] != (3, 14))" 2>/dev/null; then
	rm -rf .venv
	"$UV" venv -q --python "$PYVER" .venv
fi
VIRTUAL_ENV="$REPO/.venv" poetry install --no-interaction

if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
	{
		echo 'export LANG=en_US.UTF-8'
		echo 'export LC_ALL=en_US.UTF-8'
		echo 'export QT_QPA_PLATFORM=offscreen'
		echo "export VIRTUAL_ENV=$REPO/.venv"
		echo "export PATH=\"$REPO/.venv/bin:\$PATH\""
	} >> "$CLAUDE_ENV_FILE"
fi
