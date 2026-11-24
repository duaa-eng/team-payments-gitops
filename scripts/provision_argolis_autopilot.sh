#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GCLOUD="/Users/duaahassan/Downloads/google-cloud-sdk/bin/gcloud"
KUBECTL="/Users/duaahassan/Downloads/google-cloud-sdk/bin/kubectl"
[[ -x "$GCLOUD" ]] || GCLOUD="gcloud"
[[ -x "$KUBECTL" ]] || KUBECTL="kubectl"

PROJECT_ID="${1:-duaa-fabric-proj}"
REGION="${2:-europe-west2}"
CLUSTER_NAME="${3:-day3-demo-autopilot}"
VPC_NAME="day3-demo-vpc"
SUBNET_NAME="day3-demo-subnet"

echo "=================================================================="
echo " Provisioning Argolis GKE Autopilot Demo Environment"
echo " Project : $PROJECT_ID"
echo " Region  : $REGION"
echo " Cluster : $CLUSTER_NAME"
echo "=================================================================="

echo "-> Step 1/5: Verifying Argolis authentication..."
if ! "$GCLOUD" projects describe "$PROJECT_ID" >/dev/null 2>&1; then
  echo "   Session expired—opening browser login for Argolis (with ADC)..."
  "$GCLOUD" auth login --update-adc
fi

echo "-> Step 2/5: Enabling Compute, GKE & Managed Prometheus APIs on $PROJECT_ID..."
"$GCLOUD" services enable \
  compute.googleapis.com \
  container.googleapis.com \
  monitoring.googleapis.com \
  logging.googleapis.com \
  --project="$PROJECT_ID" \
  --quiet

echo "-> Step 3/5: Ensuring Argolis-compliant Private Google Access VPC ($VPC_NAME)..."
if ! "$GCLOUD" compute networks describe "$VPC_NAME" --project="$PROJECT_ID" --quiet >/dev/null 2>&1; then
  "$GCLOUD" compute networks create "$VPC_NAME" \
    --subnet-mode=custom \
    --project="$PROJECT_ID" \
    --quiet
fi

if ! "$GCLOUD" compute networks subnets describe "$SUBNET_NAME" --region="$REGION" --project="$PROJECT_ID" --quiet >/dev/null 2>&1; then
  "$GCLOUD" compute networks subnets create "$SUBNET_NAME" \
    --network="$VPC_NAME" \
    --region="$REGION" \
    --range="10.40.0.0/20" \
    --enable-private-ip-google-access \
    --project="$PROJECT_ID" \
    --quiet
fi

echo "-> Step 4/5: Creating GKE Autopilot cluster '$CLUSTER_NAME' (~5-7 minutes on fresh create)..."
if ! "$GCLOUD" container clusters describe "$CLUSTER_NAME" --region="$REGION" --project="$PROJECT_ID" --quiet >/dev/null 2>&1; then
  "$GCLOUD" container clusters create-auto "$CLUSTER_NAME" \
    --project="$PROJECT_ID" \
    --region="$REGION" \
    --network="$VPC_NAME" \
    --subnetwork="$SUBNET_NAME" \
    --enable-private-nodes \
    --quiet
else
  echo "   Cluster '$CLUSTER_NAME' already exists—reusing it!"
fi

echo "-> Step 5/5: Fetching kubeconfig & deploying payments-prod incident workloads..."
"$GCLOUD" container clusters get-credentials "$CLUSTER_NAME" --region="$REGION" --project="$PROJECT_ID" --quiet
"$KUBECTL" apply -f "$REPO_ROOT/live-cluster-lab/deploy-live-oom-demo.yaml"

cat > "$REPO_ROOT/.demo_env.json" <<EOF
{
  "mode": "live",
  "project_id": "$PROJECT_ID",
  "cluster": "$CLUSTER_NAME",
  "location": "$REGION",
  "namespace": "payments-prod"
}
EOF

echo ""
echo "=================================================================="
echo " ✅ LIVE ARGOLIS GKE AUTOPILOT DEMO READY!"
echo " Autopilot will provision nodes in ~60-90s, after which:"
echo "   - ledger-cache     -> Running (0 restarts, warm Linux page cache)"
echo "   - payments-worker  -> CrashLoopBackOff (OOMKilled / Exit Code 137)"
echo ""
echo " Watch live pod status with:"
echo "   $KUBECTL get pods -n payments-prod -w"
echo "=================================================================="
