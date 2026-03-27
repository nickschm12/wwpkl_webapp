#!/bin/bash
# Deploy all Cloud Functions. Run from anywhere: bash scripts/deploy.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

GCLOUD="/Users/nschmidt/Downloads/google-cloud-sdk/bin/gcloud"
PROJECT="wwpkl-309615"
REGION="us-central1"
RUNTIME="python312"
MEMORY="256MB"
TIMEOUT="120s"
SOURCE="$SCRIPT_DIR"
ENV_VARS="PROJECT_ID=484894850064,DB_SECRET_ID=wwpkl_db,DB_SECRET_VERSION=2,YAHOO_SECRET_ID=wwpkl_yahoo,YAHOO_SECRET_VERSION=8"

echo "==> Syncing packages..."
mkdir -p "$SCRIPT_DIR/packages"
rsync -a --delete "$REPO_ROOT/packages/" "$SCRIPT_DIR/packages/"

deploy() {
  local NAME=$1
  local ENTRY=$2
  echo "==> Deploying $NAME (entry: $ENTRY)..."
  $GCLOUD functions deploy "$NAME" \
    --project="$PROJECT" \
    --region="$REGION" \
    --runtime="$RUNTIME" \
    --memory="$MEMORY" \
    --timeout="$TIMEOUT" \
    --trigger-http \
    --entry-point="$ENTRY" \
    --source="$SOURCE" \
    --set-env-vars="$ENV_VARS" \
    --no-gen2 \
    --quiet
  echo "    Done."
}

deploy init_season            init_season
deploy update_league_settings update_league_meta
deploy update_season_stats    season_stats
deploy update_weekly_stats    weekly_stats

echo ""
echo "All functions deployed."
