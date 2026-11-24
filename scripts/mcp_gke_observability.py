#!/usr/bin/env python3
"""
Model Context Protocol (MCP) Stdio Server for Hybrid GKE & GDC Observability.

Exposes the exact read-only diagnostic tools featured on Day 3 Slide 89:
- list_k8s_events
- query_promql
- get_pod_logs
- get_vpa_recommendations
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hybrid_telemetry as ht  # noqa: E402

TOOLS = [
    {
        "name": "list_k8s_events",
        "description": "Read-only: List recent Kubernetes events in a hybrid Fleet cluster (e.g., gdc-bm-fra1 or gke-prod-usc1) via Connect Gateway.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cluster": {
                    "type": "string",
                    "description": "Cluster membership name (e.g., 'gdc-bm-fra1' or 'gke-prod-usc1').",
                    "default": "gdc-bm-fra1",
                },
                "namespace": {
                    "type": "string",
                    "description": "Kubernetes namespace (e.g., 'payments-prod').",
                    "default": "payments-prod",
                },
            },
        },
    },
    {
        "name": "query_promql",
        "description": "Read-only: Execute a global PromQL query against Google Cloud Managed Service for Prometheus (GMP) across GKE and GDC clusters.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "PromQL expression (e.g., container_memory_working_set_bytes{container!=\"\"} / kube_pod_container_resource_limits{resource=\"memory\"}).",
                },
                "cluster": {
                    "type": "string",
                    "description": "Optional cluster filter ('all', 'gdc-bm-fra1', 'gke-prod-usc1').",
                    "default": "all",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_pod_logs",
        "description": "Read-only: Fetch Scoped Cloud Logging container logs for a workload (set previous=true to inspect crashed OOMKilled / CrashLoopBackOff containers).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pod": {
                    "type": "string",
                    "description": "Pod or workload prefix (e.g., 'payments-worker' or 'ledger-cache-0').",
                },
                "namespace": {
                    "type": "string",
                    "default": "payments-prod",
                },
                "cluster": {
                    "type": "string",
                    "default": "gdc-bm-fra1",
                },
                "previous": {
                    "type": "boolean",
                    "description": "Equivalent to kubectl logs --previous for crashed containers.",
                    "default": True,
                },
            },
            "required": ["pod"],
        },
    },
    {
        "name": "get_vpa_recommendations",
        "description": "Read-only: Retrieve Vertical Pod Autoscaler (updateMode: 'Off') 30-day CPU/Memory right-sizing targets from GMP / BigQuery.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "namespace": {
                    "type": "string",
                    "default": "payments-prod",
                }
            },
        },
    },
]


def send_message(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def handle_request(msg: dict) -> None:
    method = msg.get("method", "")
    req_id = msg.get("id")

    # JSON-RPC notifications have no "id" and must not receive a response
    if req_id is None:
        return

    if method == "initialize":
        client_proto = msg.get("params", {}).get("protocolVersion", "2024-11-05")
        supported = {"2024-11-05", "2025-03-26", "2025-06-18"}
        proto = client_proto if client_proto in supported else "2024-11-05"
        send_message(
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": proto,
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "gke-hybrid-mcp",
                        "version": "1.0.0",
                    },
                },
            }
        )
    elif method == "ping":
        send_message({"jsonrpc": "2.0", "id": req_id, "result": {}})
    elif method == "tools/list":
        send_message({"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}})
    elif method == "tools/call":
        params = msg.get("params", {})
        name = params.get("name")
        args = params.get("arguments") or {}
        try:
            if name == "list_k8s_events":
                res = ht.list_k8s_events(
                    cluster=args.get("cluster", "gdc-bm-fra1"),
                    namespace=args.get("namespace", "payments-prod"),
                )
            elif name == "query_promql":
                res = ht.query_promql(
                    query=args.get("query", "container_memory_working_set_bytes"),
                    cluster=args.get("cluster", "all"),
                )
            elif name == "get_pod_logs":
                res = ht.get_pod_logs(
                    pod=args.get("pod", "payments-worker"),
                    namespace=args.get("namespace", "payments-prod"),
                    cluster=args.get("cluster", "gdc-bm-fra1"),
                    previous=bool(args.get("previous", True)),
                )
            elif name == "get_vpa_recommendations":
                res = ht.get_vpa_recommendations(
                    namespace=args.get("namespace", "payments-prod"),
                )
            else:
                raise ValueError(f"Unknown MCP tool: {name}")

            send_message(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(res, indent=2)}],
                        "isError": False,
                    },
                }
            )
        except Exception as exc:
            send_message(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": f"Tool execution error: {exc}"}],
                        "isError": True,
                    },
                }
            )
    else:
        send_message(
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            }
        )


def main() -> None:
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
            handle_request(msg)
        except Exception as exc:
            sys.stderr.write(f"[gke-hybrid-mcp] parse error: {exc}\n")
            sys.stderr.flush()


if __name__ == "__main__":
    main()
