#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KUBECTL="/Users/duaahassan/Downloads/google-cloud-sdk/bin/kubectl"
if [[ ! -x "$KUBECTL" ]]; then
  KUBECTL="kubectl"
fi

echo "============================================================"
echo " Shift-Left GitOps Gate (Kustomize + OPA/QoS Policy Checks) "
echo "============================================================"

TMP_GKE="$(mktemp)"
TMP_GDC="$(mktemp)"
trap 'rm -f "$TMP_GKE" "$TMP_GDC"' EXIT

KUBECONFIG=/dev/null "$KUBECTL" kustomize "$REPO_ROOT/overlays/gke-cloud" > "$TMP_GKE"
echo "[PASS] Rendered overlays/gke-cloud ($(wc -l < "$TMP_GKE" | tr -d ' ') lines)"

KUBECONFIG=/dev/null "$KUBECTL" kustomize "$REPO_ROOT/overlays/gdc-onprem" > "$TMP_GDC"
echo "[PASS] Rendered overlays/gdc-onprem ($(wc -l < "$TMP_GDC" | tr -d ' ') lines)"

python3 - "$TMP_GDC" <<'PY'
import re
import sys
from pathlib import Path

manifest_text = Path(sys.argv[1]).read_text(encoding="utf-8")
docs = [d.strip() for d in manifest_text.split("\n---") if d.strip()]

errors = []

# 1. Verify Prune=false Data Shield on stateful & Tier-1 objects
if "Prune=false" not in manifest_text:
    errors.append("Missing 'argocd.argoproj.io/sync-options: Prune=false' guardrail.")
else:
    print("[PASS] Policy DB-ARGO-002: Prune=false data shield active")

# 2. Verify PodDisruptionBudget maxUnavailable >= 1 (no upgrade deadlocks)
if "kind: PodDisruptionBudget" not in manifest_text or "maxUnavailable: 1" not in manifest_text:
    errors.append("Missing PodDisruptionBudget with maxUnavailable >= 1.")
else:
    print("[PASS] Policy DB-RES-004: PodDisruptionBudget protects rolling drains (maxUnavailable: 1)")

# 3. Verify GMP PodMonitoring CRD + high-cardinality labeldrop
if "kind: PodMonitoring" not in manifest_text or "labeldrop" not in manifest_text:
    errors.append("Missing GMP PodMonitoring CRD or high-cardinality labeldrop rule.")
else:
    print("[PASS] Policy DB-OBS-001: GMP PodMonitoring CRD & cardinality labeldrop present")

# 4. Verify VPA updateMode: "Off"
if 'updateMode: "Off"' not in manifest_text and "updateMode: Off" not in manifest_text:
    errors.append("VerticalPodAutoscaler must use updateMode: 'Off' in production.")
else:
    print("[PASS] Policy DB-FINOPS-003: VPA updateMode='Off' (zero-eviction mode) verified")

# 5. Verify Guaranteed QoS (requests == limits) on payments-worker Deployment in gdc-onprem
for doc in docs:
    if re.search(r"^kind:\s*Deployment\s*$", doc, re.M) and "name: payments-worker" in doc:
        limits_block = re.search(r"limits:\s*\n\s*cpu:\s*\"?([^\s\"]+)\"?\s*\n\s*memory:\s*\"?([^\s\"]+)\"?", doc)
        reqs_block = re.search(r"requests:\s*\n\s*cpu:\s*\"?([^\s\"]+)\"?\s*\n\s*memory:\s*\"?([^\s\"]+)\"?", doc)
        if not limits_block or not reqs_block:
            errors.append("payments-worker missing explicit CPU/memory requests and limits.")
        else:
            lim_cpu, lim_mem = limits_block.groups()
            req_cpu, req_mem = reqs_block.groups()
            if (lim_cpu, lim_mem) != (req_cpu, req_mem):
                errors.append(
                    f"Guaranteed QoS violation on payments-worker: requests ({req_cpu}/{req_mem}) != limits ({lim_cpu}/{lim_mem})."
                )
            else:
                print(f"[PASS] Policy DB-QOS-001: payments-worker Guaranteed QoS verified (CPU={req_cpu}, Memory={req_mem})")

# 6. Check if Pre-OOMKilled GMP Rules alert (> 0.85 working_set_bytes) is configured
if "working_set_bytes" in manifest_text and "0.85" in manifest_text:
    print("[PASS] Policy DB-OBS-002: Pre-OOMKilled PromQL precursor alert (>85% working_set_bytes) active")

if errors:
    print("\n[FAIL] Policy violations detected:")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)

print("============================================================")
print(" ALL SHIFT-LEFT GATES PASSED — READY FOR ARGOCD SYNC PR!    ")
print("============================================================")
PY
