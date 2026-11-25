#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

BASELINE_REF="demo-baseline"
if ! git rev-parse "$BASELINE_REF" >/dev/null 2>&1; then
  BASELINE_REF="main"
fi

git checkout -B main "$BASELINE_REF" >/dev/null 2>&1
git reset --hard "$BASELINE_REF" >/dev/null 2>&1
git clean -fd -e .demo_env.json >/dev/null 2>&1

# Delete temporary fix/* branches locally & remotely, and reset GitHub main back to 4Gi bug state
for br in $(git for-each-ref --format='%(refname:short)' refs/heads/fix/ refs/heads/pr/ 2>/dev/null); do
  git branch -D "$br" >/dev/null 2>&1 || true
  if git remote get-url origin >/dev/null 2>&1; then
    git push origin --delete "$br" >/dev/null 2>&1 || true
  fi
done

if git remote get-url origin >/dev/null 2>&1; then
  git push --force origin main >/dev/null 2>&1 || echo "⚠️  Local repo reset; run with network to also reset GitHub 'main'."
fi

echo "✅ Demo workspace & GitHub 'main' reset cleanly back to the 4Gi bug state!"
