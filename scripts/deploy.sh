#!/usr/bin/env bash
set -euo pipefail

# ─── Configuration ───────────────────────────────────────────────────────────
REMOTE_HOST="lambda"
REMOTE_CODE_DIR="~/Code"

LOCAL_LEVITY="/Users/noblecloud/Code/LevityDash"
LOCAL_WU="/Users/noblecloud/Code/WeatherUnits"
REMOTE_LEVITY="${REMOTE_CODE_DIR}/LevityDash"
REMOTE_WU="${REMOTE_CODE_DIR}/WeatherUnits"

# ─── Rsync exclude patterns ──────────────────────────────────────────────────
# These prevent local test/layout/config changes from overwriting the deployed version.
# The actual user config lives outside the repo (via appdirs at ~/.config/LevityDash/),
# so syncing the repo won't touch it. We still exclude example-config templates and
# saves within the repo to be safe.
EXCLUDES=(
  --exclude='.git/'
  --exclude='.venv/'
  --exclude='__pycache__/'
  --exclude='*.pyc'
  --exclude='.DS_Store'
  --exclude='.idea/'
  --exclude='.vscode/'
  --exclude='.pytest_cache/'
  --exclude='.mypy_cache/'
  --exclude='.config'
  --exclude='ai-prompt.md'
  --exclude='dist/'
  --exclude='build-to-app/dist/'
  --exclude='build-to-app/build/'
  --exclude='build-to-app/releases/'
  --exclude='*.egg-info/'
  --exclude='.github/'
  --exclude='node_modules/'
  --exclude='docs/_build/'
  --exclude='docs/source/.build/'
  --exclude='stash/'
  --exclude='.stash/'
  --exclude='.run/'
  --exclude='.envrc'
  --exclude='.gitignore'
  --exclude='.syncignore'
  --exclude='.editorconfig'
  --exclude='.vale.ini'
  --exclude='.vale-styles/'
  --exclude='.claude/'
)

# ─── Help ────────────────────────────────────────────────────────────────────
usage() {
  cat <<EOF
Usage: deploy.sh [OPTIONS]

Deploy LevityDash and WeatherUnits to lambda.

Options:
  --skip-wu          Skip syncing WeatherUnits
  --skip-install     Skip poetry install on lambda
  --restart          Restart the LevityDash service after deploy
  --config-only      Only sync config/settings (not code)
  --help             Show this help

Examples:
  deploy.sh                          # Full deploy: sync code + install deps
  deploy.sh --skip-install           # Sync code only, skip dep install
  deploy.sh --restart                # Sync code, install deps, restart service
  deploy.sh --config-only            # Only sync selected config files
EOF
}

# ─── Parse args ─────────────────────────────────────────────────────────────
SKIP_WU=false
SKIP_INSTALL=false
RESTART=false
CONFIG_ONLY=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-wu) SKIP_WU=true; shift ;;
    --skip-install) SKIP_INSTALL=true; shift ;;
    --restart) RESTART=true; shift ;;
    --config-only) CONFIG_ONLY=true; shift ;;
    --help) usage; exit 0 ;;
    *) echo "Unknown option: $1"; usage; exit 1 ;;
  esac
done

# ─── Sync LevityDash code (not settings) ────────────────────────────────────
sync_levity() {
  echo "── Syncing LevityDash to ${REMOTE_HOST}:${REMOTE_LEVITY} ──"
  rsync -avz --delete \
    "${EXCLUDES[@]}" \
    -e ssh \
    "${LOCAL_LEVITY}/" \
    "${REMOTE_HOST}:${REMOTE_LEVITY}/"
}

# ─── Sync WeatherUnits ───────────────────────────────────────────────────────
sync_wu() {
  echo "── Syncing WeatherUnits to ${REMOTE_HOST}:${REMOTE_WU} ──"
  rsync -avz --delete \
    --exclude='.git/' \
    --exclude='.venv/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='.DS_Store' \
    --exclude='.idea/' \
    --exclude='.pytest_cache/' \
    --exclude='dist/' \
    --exclude='*.egg-info/' \
    --exclude='.github/' \
    --exclude='.gitignore' \
    --exclude='.syncignore' \
    --exclude='.editorconfig' \
    --exclude='.envrc' \
    --exclude='poetry.lock' \
    -e ssh \
    "${LOCAL_WU}/" \
    "${REMOTE_HOST}:${REMOTE_WU}/"
}

# ─── Post-sync: install deps + WeatherUnits in editable mode ────────────────
post_sync() {
  echo "── Post-sync on ${REMOTE_HOST} ──"
  ssh "${REMOTE_HOST}" bash -s <<'REMOTE_SCRIPT'
    set -euo pipefail

    export PATH="$HOME/.local/bin:$HOME/.poetry/bin:$PATH"

    LEVITY_DIR=~/Code/LevityDash
    WU_DIR=~/Code/WeatherUnits

    echo "  → Configuring Poetry to use local .venv..."
    poetry config virtualenvs.in-project true --local 2>/dev/null || true

    echo "  → Installing WeatherUnits deps..."
    cd "$WU_DIR"
    poetry config virtualenvs.in-project true
    poetry install --no-interaction

    echo "  → Installing LevityDash deps (picks up WeatherUnits from ../WeatherUnits) ..."
    cd "$LEVITY_DIR"
    poetry config virtualenvs.in-project true
    poetry install --no-interaction

    echo "  → Verifying WeatherUnits source..."
    python3 -c "import WeatherUnits; print(f'WeatherUnits {WeatherUnits.__version__} from {WeatherUnits.__file__}')"

    echo "✅ Deploy complete on ${REMOTE_HOST}"
REMOTE_SCRIPT
}

# ─── Main ───────────────────────────────────────────────────────────────────
main() {
  if [ "$CONFIG_ONLY" = true ]; then
    echo "Use deploy-config.sh for selective config sync"
    exit 0
  fi

  echo "═══ Deploying to ${REMOTE_HOST} ═══"

  sync_levity

  if [ "$SKIP_WU" = false ]; then
    sync_wu
  fi

  if [ "$SKIP_INSTALL" = false ]; then
    post_sync
  fi

  if [ "$RESTART" = true ]; then
    echo "── Restarting LevityDash on ${REMOTE_HOST} ──"
    ssh "${REMOTE_HOST}" "sudo systemctl restart levity-dashboard 2>/dev/null || true"
  fi

  echo "═══ Done ═══"
}

main "$@"
