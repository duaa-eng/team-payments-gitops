# Day 3 Live Demo — Antigravity AI Ops for Hybrid GKE & GDC

This workspace powers the **Day 3 Module 3 Live Demo** (*Unified Observability, Systematic Triage & AI-Powered Operations*).

## Modes Supported
1. **Zero-Wi-Fi Replay Mode (Default — Works Instantly):** Simulates live Connect Gateway + Managed Prometheus (GMP) + Scoped Cloud Logging + VPA `'Off'` telemetry across `gdc-bm-fra1` (Frankfurt Bare Metal) and `gke-prod-usc1` (Cloud GKE).
2. **Live GKE Cluster Mode (Optional):** Run `./scripts/deploy_live_gke.sh <PROJECT_ID> <CLUSTER_NAME> <LOCATION>` in your macOS Terminal beforehand to deploy real `ledger-cache` and `OOMKilled` `payments-worker` pods to a sandbox GKE cluster (with automatic replay fallback if Wi-Fi drops).

## Resetting Between Practice Runs
```bash
./scripts/reset_demo.sh
```
