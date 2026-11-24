#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GCLOUD="/Users/duaahassan/Downloads/google-cloud-sdk/bin/gcloud"
KUBECTL="/Users/duaahassan/Downloads/google-cloud-sdk/bin/kubectl"
[[ -x "$GCLOUD" ]] || GCLOUD="gcloud"
[[ -x "$KUBECTL" ]] || KUBECTL="kubectl"

if [[ "${1:-}" == "--replay" ]]; then
  rm -f "$REPO_ROOT/.demo_env.json"
  echo "✅ Switched back to Zero-Wi-Fi Replay Mode (no live GCP network required)."
  exit 0
fi

if [[ $# -lt 3 ]]; then
  echo "Usage:"
  echo "  Connect real GKE cluster: $0 <GCP_PROJECT_ID> <CLUSTER_NAME> <ZONE_OR_REGION>"
  echo "  Switch to offline replay: $0 --replay"
  exit 1
fi

PROJECT_ID="$1"
CLUSTER="$2"
LOCATION="$3"

echo "1. Fetching GKE credentials for $CLUSTER ($LOCATION) in project $PROJECT_ID..."
"$GCLOUD" container clusters get-credentials "$CLUSTER" --location="$LOCATION" --project="$PROJECT_ID"

echo "2. Deploying payments-prod demo workloads (healthy ledger-cache + OOMKilling payments-worker)..."
"$KUBECTL" apply -f "$REPO_ROOT/live-cluster-lab/deploy-live-oom-demo.yaml"

cat > "$REPO_ROOT/.demo_env.json" <<EOF
{
  "mode": "live",
  "project_id": "$PROJECT_ID",
  "cluster": "$CLUSTER",
  "location": "$LOCATION",
  "namespace": "payments-prod"
}
EOF

echo "✅ Live GKE mode activated (.demo_env.json written)! Wait ~45 seconds for payments-worker to hit OOMKilled (Exit 137)."
echo "   Tip: Run '$0 --replay' anytime if conference Wi-Fi is unstable."
