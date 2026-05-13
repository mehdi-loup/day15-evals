#!/usr/bin/env bash
# Cross-grader benchmark — Day 17
#
# Runs agentic_rag and combined_routing with two grader models:
#   1. anthropic/claude-haiku-4-5-20251001  (baseline)
#   2. anthropic/claude-sonnet-4-6          (comparison)
#
# Results land in logs/cross-grader/<grader>/<task>/
# Run from the repo root: bash evals/scripts/cross_grader_benchmark.sh
#
# Cost ceiling: ~$0.05 per run (2 tasks × 2 graders × 6 cases)
# Haiku: ~$0.001/case grader call; Sonnet: ~$0.015/case grader call

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOG_BASE="$REPO_ROOT/logs/cross-grader"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"

GRADERS=(
  "anthropic/claude-haiku-4-5-20251001"
  "anthropic/claude-sonnet-4-6"
)

TASKS=(
  "evals/agentic_rag.py"
  "evals/combined_routing.py"
)

echo "=== Cross-grader benchmark — $TIMESTAMP ==="
echo "Graders: ${GRADERS[*]}"
echo "Tasks:   ${TASKS[*]}"
echo ""

for grader in "${GRADERS[@]}"; do
  # Sanitize grader name for use as directory (replace / and : with -)
  grader_dir="${grader//\//-}"
  grader_dir="${grader_dir//:/-}"

  for task in "${TASKS[@]}"; do
    task_name="$(basename "$task" .py)"
    log_dir="$LOG_BASE/$grader_dir/$task_name/$TIMESTAMP"
    mkdir -p "$log_dir"

    echo "--- grader=$grader  task=$task_name ---"

    GRADER_MODEL="$grader" uv run inspect eval "$task" \
      --model "anthropic/claude-haiku-4-5-20251001" \
      --log-dir "$log_dir" \
      2>&1 | tee "$log_dir/run.log"

    echo ""
  done
done

echo "=== Done. Logs in $LOG_BASE ==="
