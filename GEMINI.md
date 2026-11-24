# Hybrid GKE & GDC Platform Operations Workspace (`prod-fleet-host`)

This GitOps repository governs the `team-payments` Fleet Scope (`namespace: payments-prod`) across:
- **Cloud GKE Standard:** `gke-prod-usc1` (`us-central1`) -> `overlays/gke-cloud/`
- **On-Prem GDC Bare Metal:** `gdc-bm-fra1` (Frankfurt `dc1`) -> `overlays/gdc-onprem/`

## Operational Rules
1. **Evidence-Backed Triage:** Always activate the `gke-hybrid-triage` skill when investigating cluster alerts, memory pressure, `OOMKilled` (Exit Code 137), or PromQL metrics. Prefer the `gke-hybrid-mcp` MCP tools (`list_k8s_events`, `query_promql`, `get_pod_logs`, `get_vpa_recommendations`); if MCP tools are not enabled in the current session, run `python3 scripts/hybrid_telemetry.py` (`events`, `promql`, `logs --previous`, `vpa`).
2. **Linux Page Cache vs. Working Set:** Never diagnose memory saturation from `container_memory_usage_bytes` alone—always compare against `container_memory_working_set_bytes{container!=""}` divided by `kube_pod_container_resource_limits{resource="memory"}` (threshold `> 0.85`).
3. **Hook-Enforced Cluster Safety (`DB-GITOPS-001`):** Direct cluster mutations are governed by `.agents/hooks.json`. If the user explicitly asks you to execute a `kubectl` command (even a mutating command such as `kubectl set`, `kubectl patch`, or `kubectl apply`), invoke `run_command` once so the deterministic `PreToolUse` Banking Guardrail Hook can evaluate and visibly enforce policy. When denied by the hook, explain Policy `DB-GITOPS-001` concisely and pivot to creating a reviewed GitOps Pull Request under `overlays/`.
4. **Guaranteed QoS Invariant:** Tier-1 workloads in `payments-prod` require **Guaranteed QoS** (`requests.cpu == limits.cpu` and `requests.memory == limits.memory`). Always run `./scripts/validate_gitops.sh` after editing Kustomize manifests.
