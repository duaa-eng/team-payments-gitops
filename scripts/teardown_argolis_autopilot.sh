#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GCLOUD="/Users/duaahassan/Downloads/google-cloud-sdk/bin/gcloud"
[[ -x "$GCLOUD" ]] || GCLOUD="gcloud"

PROJECT_ID="${1:-duaa-fabric-proj}"
REGION="${2:-europe-west2}"
CLUSTER_NAME="${3:-day3-demo-autopilot}"

echo "Deleting GKE Autopilot cluster '$CLUSTER_NAME' in $PROJECT_ID ($REGION)..."
"$GCLOUD" container clusters delete "$CLUSTER_NAME" --region="$REGION" --project="$PROJECT_ID" --quiet
rm -f "$REPO_ROOT/.demo_env.json"
echo "✅ Cluster deleted and demo switched back to Zero-Wi-Fi Replay Mode."
