#!/usr/bin/env bash
set -euo pipefail

# ─── Configuration ───────────────────────────────────────────────────────────
REMOTE_HOST="lambda"

# ─── Help ────────────────────────────────────────────────────────────────────
usage() {
  cat <<EOF
Usage: deploy-config.sh [WHAT]

Selectively sync config/settings to lambda. Only syncs what you explicitly ask for.

Options:
  plugins       Sync plugin configs (plugins.ini + per-plugin configs)
  dashboards    Sync dashboard layout files (.levity)
  panels        Sync panel config files (.levityPanel)
  config        Sync main config.ini only
  all           Sync everything (plugins + config, NOT dashboards/panels)
  --help        Show this help

Examples:
  deploy-config.sh plugins       # Push plugin config changes to lambda
  deploy-config.sh config        # Push config.ini changes to lambda
  deploy-config.sh all           # Push plugins + config (not dashboards/panels)
EOF
}

# ─── Parse args ─────────────────────────────────────────────────────────────
WHAT="${1:-}"
if [ -z "$WHAT" ] || [ "$WHAT" = "--help" ]; then
  usage
  exit 0
fi

# ─── Determine what to sync ─────────────────────────────────────────────────
# Local user config is at ~/Library/Application Support/LevityDash (macOS)
# Remote user config is at ~/.config/LevityDash (Linux)
LOCAL_CONFIG="${HOME}/Library/Application Support/LevityDash"
REMOTE_CONFIG="~/.config/LevityDash"

RSYNC_OPTS=(-avz --delete -e ssh)

case "$WHAT" in
  plugins)
    echo "── Syncing plugin configs ──"
    rsync "${RSYNC_OPTS[@]}" \
      "${LOCAL_CONFIG}/plugins/" \
      "${REMOTE_HOST}:${REMOTE_CONFIG}/plugins/"
    ;;
  config)
    echo "── Syncing config.ini ──"
    rsync "${RSYNC_OPTS[@]}" \
      "${LOCAL_CONFIG}/config.ini" \
      "${REMOTE_HOST}:${REMOTE_CONFIG}/config.ini"
    ;;
  dashboards)
    echo "── Syncing dashboard layouts ──"
    rsync "${RSYNC_OPTS[@]}" \
      "${LOCAL_CONFIG}/saves/dashboards/" \
      "${REMOTE_HOST}:${REMOTE_CONFIG}/saves/dashboards/"
    ;;
  panels)
    echo "── Syncing panel configs ──"
    rsync "${RSYNC_OPTS[@]}" \
      "${LOCAL_CONFIG}/saves/panels/" \
      "${REMOTE_HOST}:${REMOTE_CONFIG}/saves/panels/"
    ;;
  all)
    echo "── Syncing plugins + config (not dashboards/panels) ──"
    rsync "${RSYNC_OPTS[@]}" \
      "${LOCAL_CONFIG}/plugins/" \
      "${REMOTE_HOST}:${REMOTE_CONFIG}/plugins/"
    rsync "${RSYNC_OPTS[@]}" \
      "${LOCAL_CONFIG}/config.ini" \
      "${REMOTE_HOST}:${REMOTE_CONFIG}/config.ini"
    ;;
  *)
    echo "Unknown option: $WHAT"
    usage
    exit 1
    ;;
esac

echo "✅ Config sync complete"
