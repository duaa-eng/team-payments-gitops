---
name: gke-hybrid-triage
description: Systematic Day-2 incident triage and GitOps remediation workflow across Hybrid Cloud GKE and On-Prem GDC clusters using Managed Prometheus (GMP), Scoped Cloud Logging, VPA 'Off' recommendations, and Kustomize overlays.
---

# Hybrid GKE & GDC Incident Triage Skill

Follow this deterministic 4-step workflow when investigating live alerts in `prod-fleet-host`:

## Step 1: Parallel Read-Only Telemetry Collection
Gather proof across Events, GMP PromQL, `--previous` Container Logs, and VPA `'Off'` targets:
- **If `gke-hybrid-mcp` MCP tools are available**, call:
  1. `list_k8s_events(cluster="gdc-bm-fra1", namespace="payments-prod")` (and compare with `cluster="gke-prod-usc1"`).
  2. `query_promql(query='container_memory_working_set_bytes{container!=""} / kube_pod_container_resource_limits{resource="memory"}')`
  3. `get_pod_logs(pod="payments-worker", cluster="gdc-bm-fra1", namespace="payments-prod", previous=True)` and `get_pod_logs(pod="ledger-cache-0", cluster="gdc-bm-fra1", namespace="payments-prod", previous=False)`
  4. `get_vpa_recommendations(namespace="payments-prod")`
- **Fallback (if MCP tools are not listed in your declarations)**, run via `run_command`:
  - `python3 scripts/hybrid_telemetry.py events --cluster gdc-bm-fra1 -n payments-prod`
  - `python3 scripts/hybrid_telemetry.py promql -q 'container_memory_working_set_bytes{container!=""} / kube_pod_container_resource_limits{resource="memory"}'`
  - `python3 scripts/hybrid_telemetry.py logs --pod payments-worker --cluster gdc-bm-fra1 --previous`
  - `python3 scripts/hybrid_telemetry.py vpa -n payments-prod`

## Step 2: Correlate Local GitOps Overlays
Inspect `overlays/gke-cloud/memory-patch.yaml` vs. `overlays/gdc-onprem/memory-patch.yaml` to identify environment drift explaining why Cloud GKE survived while Frankfurt GDC (`gdc-bm-fra1`) hit `OOMKilled` (`Exit Code 137`).

## Step 3: Inline Visual RCA Summary (When Requested)
If the user asks for an inline RCA dashboard/chart, activate the `generative_ui` skill and embed a compact (`< 440px` tall) HTML card via `<agent-embed>` comparing:
1. `ledger-cache-0`: `usage_bytes` (`96.4%`) vs. `working_set_bytes` (`36.3%`) — **False Alarm (9.62 GiB Reclaimable Linux Page Cache)**.
2. `payments-worker` (`gdc-bm-fra1`): `working_set_bytes` climbing past the **85% Precursor** at `T-15m` (`148/s` major page faults) -> **100% (`4.0 GiB`) `OOMKilled` (Exit 137)** vs. `gke-prod-usc1` (`6.0 GiB` ceiling, peaked safely at `82%`).

## Step 4: Safe GitOps Remediation (`overlays/gdc-onprem/`)
Never mutate clusters directly. When asked to remediate via GitOps:
1. Create a feature branch (e.g., `git checkout -b fix/gdc-payments-worker-6gi`).
2. Update `overlays/gdc-onprem/memory-patch.yaml` so **both** `requests.memory` and `limits.memory` are `"6Gi"` (preserving **Guaranteed QoS** and matching VPA `'Off'` target).
3. Add a GMP `Rules` manifest (`overlays/gdc-onprem/oom-precursor-rules.yaml`, `apiVersion: monitoring.googleapis.com/v1`, `kind: Rules`) alerting when `container_memory_working_set_bytes{container!=""} / kube_pod_container_resource_limits{resource="memory"} > 0.85` for `5m`, and reference it in `overlays/gdc-onprem/kustomization.yaml`.
4. Run `./scripts/validate_gitops.sh` to verify Kustomize rendering, Guaranteed QoS, and CIS/GitOps guardrails, stage & commit the changes, and then run `python3 scripts/create_github_pr.py` (with `BypassSandbox: true` so it can reach `api.github.com`) to push the branch and open a live GitHub Pull Request—sharing the clickable GitHub PR URL in your summary!
