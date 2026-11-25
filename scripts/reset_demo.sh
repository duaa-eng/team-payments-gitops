#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

git checkout main >/dev/null 2>&1 || true
git reset --hard main >/dev/null 2>&1
git clean -fd -e .demo_env.json >/dev/null 2>&1

# Delete any temporary fix/* branches locally (and remotely if online)
for br in $(git for-each-ref --format='%(refname:short)' refs/heads/fix/ refs/heads/pr/ 2>/dev/null); do
  git branch -D "$br" >/dev/null 2>&1 || true
  if git remote get-url origin >/dev/null 2>&1; then
    git push origin --delete "$br" >/dev/null 2>&1 || true
  fi
done

echo "✅ Demo workspace reset cleanly to 'main' branch (gdc-onprem overlay back at 4Gi bug state)."
