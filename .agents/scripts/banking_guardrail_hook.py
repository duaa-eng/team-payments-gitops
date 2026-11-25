#!/usr/bin/env python3
"""
PreToolUse Lifecycle Hook — Banking Production GitOps Guardrail (Policy DB-GITOPS-001).

Hard-blocks mutating `kubectl` commands against live clusters while allowing
read-only observability diagnostics and local GitOps validation scripts.
"""

import json
import re
import sys

MUTATING_KUBECTL_PATTERN = re.compile(
    r"\bkubectl\b(?:\s+--?[a-zA-Z0-9_-]+(?:=\S+)?)*\s+"
    r"(apply|create|delete|edit|patch|replace|scale|set|autoscale|cordon|drain|taint|exec)\b"
)
MUTATING_ROLLOUT_PATTERN = re.compile(
    r"\bkubectl\b.*\brollout\s+(restart|undo|pause|resume)\b"
)

SAFE_LOCAL_PREFIXES = (
    "python3 scripts/hybrid_telemetry.py",
    "python3 ./scripts/hybrid_telemetry.py",
    "./scripts/hybrid_telemetry.py",
    "bash scripts/validate_gitops.sh",
    "./scripts/validate_gitops.sh",
    "kubectl kustomize",
    "/Users/duaahassan/Downloads/google-cloud-sdk/bin/kubectl kustomize",
    "git status",
    "git diff",
    "git branch",
    "git checkout -b",
    "git switch -c",
    "git add",
    "git commit",
    "git log",
    "python3 scripts/create_github_pr.py",
    "python3 ./scripts/create_github_pr.py",
    "./scripts/create_github_pr.py",
)


def decide(command_line: str) -> dict:
    cmd = command_line.strip()

    # Allow client-side dry-run or kustomize rendering
    if "--dry-run=client" in cmd or "kubectl kustomize" in cmd:
        return {"decision": "allow"}

    # Hard-block any mutating kubectl operation against live clusters
    match = MUTATING_KUBECTL_PATTERN.search(cmd) or MUTATING_ROLLOUT_PATTERN.search(cmd)
    if match:
        verb = match.group(1)
        return {
            "decision": "deny",
            "reason": (
                f"BANKING PRODUCTION GUARDRAIL [Policy DB-GITOPS-001]: "
                f"Direct cluster mutation ('kubectl {verb}') is strictly blocked on production GKE/GDC clusters "
                f"(Read-Only Viewer IAM + Drift Shield active). Remediate via a reviewed GitOps Pull Request in overlays/."
            ),
        }

    # Smoothly allow read-only telemetry & local GitOps workflow steps during live demo
    if cmd.startswith(SAFE_LOCAL_PREFIXES) or re.match(r"^\bkubectl\s+(get|describe|logs|top)\b", cmd):
        return {"decision": "allow"}

    return {"decision": "ask"}


def main() -> None:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        cmd = payload.get("toolCall", {}).get("args", {}).get("CommandLine", "")
        result = decide(cmd)
    except Exception:
        result = {"decision": "ask"}

    sys.stdout.write(json.dumps(result) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
