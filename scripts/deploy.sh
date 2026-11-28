#!/usr/bin/env bash
set -euo pipefail

# ─── Configuration ───────────────────────────────────────────────────────────
REMOTE_HOST="lambda"
REMOTE_CODE_DIR="~/Code"

LOCAL_LEVITY="/Users/noblecloud/Code/LevityDash"
LOCAL_UC="/Users/noblecloud/Code/unitcorn"
REMOTE_LEVITY="${REMOTE_CODE_DIR}/LevityDash"
REMOTE_UC="${REMOTE_CODE_DIR}/unitcorn"

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

Deploy LevityDash and UnitCorn to lambda.

Options:
  --skip-uc          Skip syncing UnitCorn (--skip-wu still works)
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
SKIP_UC=false
SKIP_INSTALL=false
RESTART=false
CONFIG_ONLY=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-uc|--skip-wu) SKIP_UC=true; shift ;;
    --skip-install) SKIP_INSTALL=true; shift ;;
    --restart) RESTART=true; shift ;;
    --config-only) CONFIG_ONLY=true; shift ;;
    --help) usage; exit 0 ;;
    *) echo "Unknown option: $1"; usage; exit 1 ;;
  esac
done

# ─── Rename handling ─────────────────────────────────────────────────────────
# The library checkout used to be called WeatherUnits. LevityDash's pyproject now
# path-depends on ../unitcorn, so a checkout under the old name would not resolve;
# both sides are renamed in place on the first deploy.
check_local_rename() {
  local old="${LOCAL_UC%/*}/WeatherUnits"
  if [ ! -d "${LOCAL_UC}" ] && [ -d "${old}" ]; then
    mv "${old}" "${LOCAL_UC}"
    echo "  → renamed ${old} to ${LOCAL_UC}"
    echo "  → run 'poetry install' in ${LOCAL_LEVITY} to relink the local env to ../unitcorn"
  fi
}

# Same one-time move on lambda, keeping its .venv (poetry install relinks it).
migrate_remote() {
  ssh "${REMOTE_HOST}" "cd ${REMOTE_CODE_DIR} && if [ ! -d unitcorn ] && [ -d WeatherUnits ]; then mv WeatherUnits unitcorn && echo '  → renamed ${REMOTE_CODE_DIR}/WeatherUnits to unitcorn'; fi"
}

# ─── Sync LevityDash code (not settings) ────────────────────────────────────
sync_levity() {
  echo "── Syncing LevityDash to ${REMOTE_HOST}:${REMOTE_LEVITY} ──"
  rsync -avz --delete \
    "${EXCLUDES[@]}" \
    -e ssh \
    "${LOCAL_LEVITY}/" \
    "${REMOTE_HOST}:${REMOTE_LEVITY}/"
}

# ─── Sync UnitCorn ───────────────────────────────────────────────────────
sync_uc() {
  echo "── Syncing UnitCorn to ${REMOTE_HOST}:${REMOTE_UC} ──"
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
    "${LOCAL_UC}/" \
    "${REMOTE_HOST}:${REMOTE_UC}/"
}

# ─── Post-sync: install deps + UnitCorn in editable mode ────────────────
post_sync() {
  echo "── Post-sync on ${REMOTE_HOST} ──"
  ssh "${REMOTE_HOST}" bash -s <<'REMOTE_SCRIPT'
    set -euo pipefail

    export PATH="$HOME/.local/bin:$HOME/.poetry/bin:$PATH"

    LEVITY_DIR=~/Code/LevityDash
    UC_DIR=~/Code/unitcorn

    echo "  → Configuring Poetry to use local .venv..."
    poetry config virtualenvs.in-project true --local 2>/dev/null || true

    echo "  → Installing unitcorn deps..."
    cd "$UC_DIR"
    poetry config virtualenvs.in-project true
    poetry install --no-interaction

    echo "  → Installing LevityDash deps (picks up unitcorn from ../unitcorn) ..."
    cd "$LEVITY_DIR"
    poetry config virtualenvs.in-project true
    poetry install --no-interaction

    echo "  → Verifying unitcorn source..."
    poetry run python -c "import unitcorn, importlib.metadata as m; print(f'unitcorn {m.version(\"unitcorn\")} from {unitcorn.__file__}')"

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

  if [ "$SKIP_UC" = false ]; then check_local_rename; fi
  migrate_remote
  sync_levity

  if [ "$SKIP_UC" = false ]; then
    sync_uc
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
