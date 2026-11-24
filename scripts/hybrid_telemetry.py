#!/usr/bin/env python3
"""
Dual-Mode Hybrid GKE & GDC Observability Engine (Live GKE/GMP + Zero-Wi-Fi Replay).

Used by both:
1. scripts/mcp_gke_observability.py (Model Context Protocol Stdio Server)
2. Direct CLI fallback (`python3 scripts/hybrid_telemetry.py <subcommand> ...`)
"""

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = REPO_ROOT / ".demo_env.json"
GCLOUD_BIN = "/Users/duaahassan/Downloads/google-cloud-sdk/bin/gcloud"
KUBECTL_BIN = "/Users/duaahassan/Downloads/google-cloud-sdk/bin/kubectl"


def load_demo_config() -> dict:
    if ENV_FILE.exists():
        try:
            return json.loads(ENV_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "mode": "replay",
        "fleet_project": "prod-fleet-host",
        "primary_cluster": "gdc-bm-fra1",
        "cloud_cluster": "gke-prod-usc1",
        "fleet_scope": "team-payments",
        "namespace": "payments-prod",
    }


def iso_minutes_ago(mins: int) -> str:
    ts = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=mins)
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def try_live_kubectl(args: list[str], timeout: int = 6) -> str | None:
    kubectl = KUBECTL_BIN if os.path.exists(KUBECTL_BIN) else "kubectl"
    try:
        res = subprocess.run(
            [kubectl, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True,
        )
        return res.stdout.strip()
    except Exception:
        return None


def try_live_promql(project_id: str, query: str) -> dict | None:
    gcloud = GCLOUD_BIN if os.path.exists(GCLOUD_BIN) else "gcloud"
    try:
        tok_res = subprocess.run(
            [gcloud, "auth", "print-access-token"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        token = tok_res.stdout.strip()
        params = urllib.parse.urlencode({"query": query})
        url = (
            f"https://monitoring.googleapis.com/v1/projects/{project_id}"
            f"/location/global/prometheus/api/v1/query?{params}"
        )
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            if payload.get("status") == "success" and payload.get("data", {}).get("result"):
                return payload
    except Exception:
        return None
    return None


def list_k8s_events(cluster: str = "gdc-bm-fra1", namespace: str = "payments-prod") -> dict:
    cfg = load_demo_config()
    if cfg.get("mode") == "live":
        raw = try_live_kubectl(["get", "events", "-n", namespace, "-o", "json"])
        if raw:
            parsed = json.loads(raw)
            items = parsed.get("items", [])
            if items:
                return {
                    "source": "LIVE_GKE_API",
                    "cluster": cfg.get("cluster", cluster),
                    "namespace": namespace,
                    "event_count": len(items),
                    "events": [
                        {
                            "lastTimestamp": e.get("lastTimestamp") or e.get("eventTime"),
                            "type": e.get("type"),
                            "reason": e.get("reason"),
                            "involvedObject": f"{e.get('involvedObject', {}).get('kind')}/{e.get('involvedObject', {}).get('name')}",
                            "message": e.get("message"),
                        }
                        for e in items[-15:]
                    ],
                }

    # Replay telemetry across Hybrid Fleet (gdc-bm-fra1 & gke-prod-usc1)
    if cluster == "gke-prod-usc1":
        return {
            "source": "FLEET_CONNECT_GATEWAY_TELEMETRY",
            "fleetHostProject": "prod-fleet-host",
            "fleetScope": "team-payments",
            "cluster": "gke-prod-usc1 (Cloud GKE Standard • us-central1)",
            "namespace": namespace,
            "events": [
                {
                    "timestamp": iso_minutes_ago(28),
                    "type": "Normal",
                    "reason": "Started",
                    "object": "Pod/payments-worker-7c4d8b9f5-m92lq",
                    "message": "Started container payments-worker (limits.memory=6Gi, QoS=Guaranteed, 0 restarts)",
                },
                {
                    "timestamp": iso_minutes_ago(25),
                    "type": "Normal",
                    "reason": "Started",
                    "object": "Pod/ledger-cache-0",
                    "message": "Started container ledger-cache with Hyperdisk Balanced PVC (0 restarts)",
                },
            ],
        }

    return {
        "source": "FLEET_CONNECT_GATEWAY_TELEMETRY",
        "fleetHostProject": "prod-fleet-host",
        "fleetScope": "team-payments",
        "cluster": f"{cluster} (On-Prem GDC Bare Metal • Frankfurt dc1)",
        "namespace": namespace,
        "events": [
            {
                "timestamp": iso_minutes_ago(42),
                "type": "Normal",
                "reason": "VolumeBound",
                "object": "PersistentVolumeClaim/data-ledger-cache-0",
                "message": "WaitForFirstConsumer bound PVC to local NVMe PV on node bm-fra1-rack2-04 (0 errors)",
            },
            {
                "timestamp": iso_minutes_ago(41),
                "type": "Normal",
                "reason": "Running",
                "object": "Pod/ledger-cache-0",
                "message": "Container ledger-cache healthy (Ready 1/1, restartCount=0, uptime=14d)",
            },
            {
                "timestamp": iso_minutes_ago(14),
                "type": "Warning",
                "reason": "MemoryCgroupPressure",
                "object": "Pod/payments-worker-6f8d9c7b4-xk29p",
                "message": "Container payments-worker working_set_bytes exceeded 85% of 4Gi cgroup memory.max; pgmajfault spiking (148/s)",
            },
            {
                "timestamp": iso_minutes_ago(4),
                "type": "Warning",
                "reason": "OOMKilling",
                "object": "Pod/payments-worker-6f8d9c7b4-xk29p",
                "message": "Memory cgroup out of memory: Killed process 1 (settlement-engine) anon-rss:4194104kB, file-rss:12288kB — hit 4Gi memory limit (Exit Code 137)",
            },
            {
                "timestamp": iso_minutes_ago(1),
                "type": "Warning",
                "reason": "BackOff",
                "object": "Pod/payments-worker-6f8d9c7b4-xk29p",
                "message": "Back-off restarting failed container payments-worker in pod payments-worker-6f8d9c7b4-xk29p_payments-prod (CrashLoopBackOff, restartCount=6, lastState.terminated.reason=OOMKilled, exitCode=137)",
            },
        ],
    }


def get_pod_logs(
    pod: str = "payments-worker",
    namespace: str = "payments-prod",
    cluster: str = "gdc-bm-fra1",
    previous: bool = True,
) -> dict:
    cfg = load_demo_config()
    if cfg.get("mode") == "live":
        label = "ledger-cache" if "ledger" in pod else "payments-worker"
        cmd = ["logs", "-n", namespace, "-l", f"app={label}", "--tail=30"]
        if previous:
            cmd.append("--previous")
        raw = try_live_kubectl(cmd)
        if raw:
            return {
                "source": "LIVE_GKE_LOGS",
                "cluster": cfg.get("cluster", cluster),
                "namespace": namespace,
                "pod": pod,
                "previous": previous,
                "logs": raw.splitlines(),
            }

    if "ledger" in pod:
        return {
            "source": "SCOPED_CLOUD_LOGGING_BUCKET (team-payments)",
            "cluster": cluster,
            "namespace": namespace,
            "pod": "ledger-cache-0",
            "previous": previous,
            "containerStatus": {"state": "Running", "restartCount": 0, "exitCode": 0},
            "logs": [
                f"{iso_minutes_ago(10)} INFO  [ledger-cache] Read-through settlement ledger cache healthy; p99 read latency=0.42ms",
                f"{iso_minutes_ago(6)} INFO  [ledger-cache] Active heap working_set=5.80GiB / 16.00GiB (36.2%); OS kernel reclaimable file page-cache=9.62GiB",
                f"{iso_minutes_ago(1)} INFO  [ledger-cache] Checkpoint complete (fsync=1.1ms). Zero memory pressure, zero page faults.",
            ],
        }

    if not previous:
        return {
            "source": "SCOPED_CLOUD_LOGGING_BUCKET (team-payments)",
            "cluster": cluster,
            "namespace": namespace,
            "pod": "payments-worker-6f8d9c7b4-xk29p",
            "previous": False,
            "containerStatus": {
                "state": "Waiting (CrashLoopBackOff)",
                "restartCount": 6,
                "lastTerminatedReason": "OOMKilled",
                "lastExitCode": 137,
            },
            "hint": "Container just restarted! Pass previous=true (kubectl logs --previous) to inspect the crash logs prior to Exit Code 137.",
            "logs": [
                f"{iso_minutes_ago(1)} INFO  [payments-worker] Booting SEPA Instant Settlement Worker v2.14.0 on {cluster}...",
                f"{iso_minutes_ago(1)} INFO  [payments-worker] Detected cgroup memory limit: 4096 MiB (4Gi). Connecting to Kafka settlement-topic...",
            ],
        }

    return {
        "source": "SCOPED_CLOUD_LOGGING_BUCKET (team-payments)",
        "cluster": cluster,
        "namespace": namespace,
        "pod": "payments-worker-6f8d9c7b4-xk29p",
        "previous": True,
        "containerStatus": {
            "lastTerminatedReason": "OOMKilled",
            "lastExitCode": 137,
            "restartCount": 6,
            "terminatedAt": iso_minutes_ago(4),
        },
        "logs": [
            f"{iso_minutes_ago(16)} INFO  [payments-worker] Processing EU EOD SEPA settlement batch #88412 (280,000 Clearing Records)...",
            f"{iso_minutes_ago(14)} WARN  [payments-worker] Active working-set heap reached 3,624 MiB / 4,096 MiB (88.5% of cgroup limit). GC pause=410ms",
            f"{iso_minutes_ago(8)} WARN  [payments-worker] Un-evictable batch aggregation buffers at 3,912 MiB / 4,096 MiB (95.5%). Major page faults rising!",
            f"{iso_minutes_ago(4)} ERROR [payments-worker] Allocation of 256 MiB clearing batch buffer pushed anon-rss to 4,096 MiB ceiling (overlays/gdc-onprem limit=4Gi)!",
            f"{iso_minutes_ago(4)} FATAL [kernel-cgroup] Memory cgroup out of memory: container payments-worker killed by SIGKILL (Exit Code 137 / OOMKilled)",
        ],
    }


def query_promql(query: str, cluster: str = "all", window: str = "30m") -> dict:
    cfg = load_demo_config()
    if cfg.get("mode") == "live" and cfg.get("project_id"):
        live_data = try_live_promql(cfg["project_id"], query)
        if live_data:
            return {
                "source": "LIVE_GOOGLE_MANAGED_PROMETHEUS",
                "project": cfg["project_id"],
                "query": query,
                "result": live_data["data"]["result"],
            }

    q_lower = query.lower()
    timestamps = [iso_minutes_ago(m) for m in [30, 25, 20, 15, 10, 5, 1]]

    # Return comprehensive GMP PromQL telemetry comparing usage_bytes vs working_set_bytes across GDC & GKE
    series = []

    if "usage_bytes" in q_lower or "working_set" not in q_lower:
        series.extend(
            [
                {
                    "metric": {
                        "__name__": "container_memory_usage_bytes",
                        "cluster": "gdc-bm-fra1",
                        "namespace": "payments-prod",
                        "pod": "ledger-cache-0",
                        "container": "ledger-cache",
                        "limit_gib": "16.0",
                        "note": "96.4% of 16Gi limit — INCLUDES 9.62 GiB reclaimable Linux disk page cache (FALSE ALARM!)",
                    },
                    "values_gib": [15.20, 15.31, 15.35, 15.40, 15.41, 15.42, 15.42],
                    "ratio_of_limit": [0.950, 0.957, 0.959, 0.963, 0.963, 0.964, 0.964],
                },
                {
                    "metric": {
                        "__name__": "container_memory_usage_bytes",
                        "cluster": "gdc-bm-fra1",
                        "namespace": "payments-prod",
                        "pod": "payments-worker-6f8d9c7b4-xk29p",
                        "container": "payments-worker",
                        "limit_gib": "4.0",
                        "note": "Hit 100% of 4Gi limit -> OOMKilled (Exit Code 137)!",
                    },
                    "values_gib": [2.15, 2.78, 3.30, 3.58, 3.86, 4.00, 1.10],
                    "ratio_of_limit": [0.538, 0.695, 0.825, 0.895, 0.965, 1.000, 0.275],
                },
            ]
        )

    if "working_set" in q_lower or "limit" in q_lower or "oom" in q_lower or "usage_bytes" in q_lower:
        series.extend(
            [
                {
                    "metric": {
                        "__name__": "container_memory_working_set_bytes",
                        "cluster": "gdc-bm-fra1",
                        "namespace": "payments-prod",
                        "pod": "ledger-cache-0",
                        "container": "ledger-cache",
                        "limit_gib": "16.0",
                        "alert_threshold_0_85": "HEALTHY (0.363 <= 0.85 — 0 restarts, sleep tight!)",
                    },
                    "values_gib": [5.72, 5.75, 5.78, 5.80, 5.79, 5.80, 5.80],
                    "working_set_to_limit_ratio": [0.358, 0.359, 0.361, 0.363, 0.362, 0.363, 0.363],
                },
                {
                    "metric": {
                        "__name__": "container_memory_working_set_bytes",
                        "cluster": "gdc-bm-fra1",
                        "namespace": "payments-prod",
                        "pod": "payments-worker-6f8d9c7b4-xk29p",
                        "container": "payments-worker",
                        "limit_gib": "4.0",
                        "alert_threshold_0_85": "CRITICAL PRECURSOR FIRED AT T-15m (0.885 > 0.85) -> OOMKilled (137) at T-5m!",
                    },
                    "values_gib": [2.08, 2.72, 3.24, 3.54, 3.81, 4.00, 1.05],
                    "working_set_to_limit_ratio": [0.520, 0.680, 0.810, 0.885, 0.953, 1.000, 0.263],
                    "pgmajfault_per_sec": [0.0, 0.2, 4.5, 92.4, 148.6, 210.3, 0.1],
                },
                {
                    "metric": {
                        "__name__": "container_memory_working_set_bytes",
                        "cluster": "gke-prod-usc1",
                        "namespace": "payments-prod",
                        "pod": "payments-worker-7c4d8b9f5-m92lq",
                        "container": "payments-worker",
                        "limit_gib": "6.0",
                        "alert_threshold_0_85": "HEALTHY ON CLOUD GKE (peaked at 4.92 GiB / 6.0 GiB = 0.820 <= 0.85 because overlays/gke-cloud already has 6Gi!)",
                    },
                    "values_gib": [2.10, 2.85, 3.60, 4.45, 4.92, 4.70, 2.30],
                    "working_set_to_limit_ratio": [0.350, 0.475, 0.600, 0.742, 0.820, 0.783, 0.383],
                },
            ]
        )

    if cluster not in ("all", "", "*"):
        filtered = [s for s in series if s["metric"]["cluster"] == cluster]
        if filtered:
            series = filtered

    return {
        "source": "GOOGLE_MANAGED_PROMETHEUS (Monarch Global Fleet View)",
        "fleetHostProject": "prod-fleet-host",
        "executedPromQL": query,
        "goldenPrecursorRule": 'container_memory_working_set_bytes{container!=""} / kube_pod_container_resource_limits{resource="memory"} > 0.85',
        "timestamps_utc": timestamps,
        "series": series,
        "summaryInsight": (
            "1) ledger-cache-0 on gdc-bm-fra1 is a FALSE ALARM: usage_bytes is 96.4% (15.42Gi/16Gi) due to 9.62Gi of reclaimable Linux page cache, "
            "whereas working_set_bytes is flat at 36.3% (5.80Gi/16Gi).\n"
            "2) payments-worker on gdc-bm-fra1 is the REAL ROOT CAUSE: working_set_bytes crossed 85% (3.54Gi/4Gi) 15m ago with 148/s major page faults, "
            "then hit 100% (4.00Gi) -> OOMKilled (Exit Code 137). Notice gke-prod-usc1 peaked at 4.92Gi and survived because overlays/gke-cloud has 6Gi while overlays/gdc-onprem is stuck at 4Gi!"
        ),
    }


def get_vpa_recommendations(namespace: str = "payments-prod") -> dict:
    return {
        "source": "GKE_VPA_RECOMMENDER_AND_BIGQUERY_30D",
        "namespace": namespace,
        "updateMode": "Off (Zero-Eviction Production Telemetry Mode — Never restarts pods)",
        "recommendations": [
            {
                "vpaName": "payments-worker-vpa",
                "targetWorkload": "Deployment/payments-worker",
                "currentOverlayGkeCloud": {"requests.memory": "6Gi", "limits.memory": "6Gi"},
                "currentOverlayGdcOnPrem": {"requests.memory": "4Gi", "limits.memory": "4Gi", "driftAlert": "UNDER-PROVISIONED — causing Exit 137 OOMKills!"},
                "vpa30DayRecommendation": {
                    "lowerBound": "4Gi",
                    "target": "6Gi",
                    "uncappedTarget": "5.6Gi",
                    "upperBound": "8Gi",
                    "qosNote": "Keep requests.memory == limits.memory == 6Gi to preserve Kubernetes Guaranteed QoS tier.",
                },
            },
            {
                "vpaName": "ledger-cache-vpa",
                "targetWorkload": "StatefulSet/ledger-cache",
                "currentSpec": {"requests.memory": "16Gi", "limits.memory": "16Gi"},
                "vpa30DayRecommendation": {
                    "target": "16Gi",
                    "status": "OPTIMAL — No change needed (high usage_bytes is normal OS page cache).",
                },
            },
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Hybrid GKE/GDC & GMP Telemetry CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ev = sub.add_parser("events", help="List Kubernetes events across hybrid clusters")
    p_ev.add_argument("--cluster", default="gdc-bm-fra1")
    p_ev.add_argument("--namespace", "-n", default="payments-prod")

    p_logs = sub.add_parser("logs", help="Fetch container logs (supports --previous)")
    p_logs.add_argument("--pod", default="payments-worker")
    p_logs.add_argument("--cluster", default="gdc-bm-fra1")
    p_logs.add_argument("--namespace", "-n", default="payments-prod")
    p_logs.add_argument("--previous", action="store_true", help="Fetch crashed container logs")

    p_prom = sub.add_parser("promql", help="Execute global PromQL against Managed Prometheus (GMP)")
    p_prom.add_argument("--query", "-q", required=True)
    p_prom.add_argument("--cluster", default="all")

    p_vpa = sub.add_parser("vpa", help="Inspect VPA 'Off' mode right-sizing targets")
    p_vpa.add_argument("--namespace", "-n", default="payments-prod")

    args = parser.parse_args()
    if args.cmd == "events":
        out = list_k8s_events(cluster=args.cluster, namespace=args.namespace)
    elif args.cmd == "logs":
        out = get_pod_logs(pod=args.pod, namespace=args.namespace, cluster=args.cluster, previous=args.previous)
    elif args.cmd == "promql":
        out = query_promql(query=args.query, cluster=args.cluster)
    elif args.cmd == "vpa":
        out = get_vpa_recommendations(namespace=args.namespace)
    else:
        out = {"error": "unknown command"}

    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
