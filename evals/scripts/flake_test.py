"""
Faithfulness scorer stability harness — Day 16 Move 2b.

This is a META-EVAL of the grader, not the agent.
It replays a fixed set of cached agent responses through the faithfulness grader
N times and reports the per-case agreement rate.

Why committed cache (not on-demand generation):
  The goal is to isolate *grader* non-determinism from *agent* non-determinism.
  Re-running the agent introduces two noise sources at once; replaying a fixed
  response isolates exactly one: whether the grader gives the same verdict on
  the same text. If the cache goes stale (agent response format changes), re-run
  the agentic_rag task, extract the new responses, and commit an updated cache.

Decision rule:
  agreement_rate = fraction of N runs with the same verdict as run 1
  - >= 0.9  (all 3/3 or at least 90% for larger N): scorer is stable → CI-blocking
  - < 0.9:  scorer is unstable → downgrade to informational-only in CI

Usage:
  uv run python evals/scripts/flake_test.py [--n 3]

Output:
  stdout:     per-case agreement table + headline disagreement %
  STABILITY.md: written to repo root

Cost: ~$0.004 × N grader calls (claude-haiku-4-5-20251001, ~2.8K tokens/case)
"""

import argparse
import json
import os
import re
import sys
from dotenv import load_dotenv
import anthropic

# Load .env from repo root (needed when ANTHROPIC_API_KEY is not in shell env)
_REPO_ROOT_FOR_ENV = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
load_dotenv(os.path.join(_REPO_ROOT_FOR_ENV, ".env"))

_HERE = os.path.dirname(__file__)
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))

GRADER_MODEL = "claude-haiku-4-5-20251001"
CACHE_FILE = os.path.join(_HERE, "grader_cache.json")

FAITHFULNESS_PROMPT = """You are evaluating whether an AI assistant's response correctly satisfies a grading criterion.

IMPORTANT: Tool routing (which tools were called) has already been verified by a separate scorer. Your job is ONLY to assess whether the response content itself is accurate, faithful, and appropriate — not whether tools were invoked.

Question asked:
{question}

AI response to evaluate:
{answer}

Grading criterion:
{criterion}

Grade the response against the criterion above. The criterion is the sole authority — do not apply any other rules.
- GRADE: C if the response satisfies ALL "must" conditions AND violates none of the "must NOT" conditions in the criterion.
- GRADE: I if the response violates ANY condition in the criterion.

Respond with your reasoning in one sentence, then on a new line: GRADE: C or GRADE: I"""


def grade_once(client: anthropic.Anthropic, case: dict) -> str:
    """Run the grader once on a cached case. Returns 'C' or 'I' or 'PARSE_ERROR'."""
    prompt = FAITHFULNESS_PROMPT.format(
        question=case["input"],
        answer=case["completion"],
        criterion=case["judge_rubric"],
    )
    msg = client.messages.create(
        model=GRADER_MODEL,
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )
    completion = msg.content[0].text.strip()
    match = re.search(r"(?i)GRADE\s*:\s*([CI])", completion)
    if match:
        return match.group(1).upper()
    return "PARSE_ERROR"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=3, help="Number of grader runs per case")
    args = parser.parse_args()
    N = args.n

    with open(CACHE_FILE) as f:
        cases = json.load(f)

    client = anthropic.Anthropic()

    print(f"Faithfulness scorer stability harness (N={N})")
    print(f"Grader: {GRADER_MODEL}")
    print(f"Cases: {len(cases)}")
    print("-" * 60)

    results = []
    total_disagreements = 0
    total_pairs = 0

    for case in cases:
        verdicts = []
        for i in range(N):
            verdict = grade_once(client, case)
            verdicts.append(verdict)
            print(f"  {case['id']} run {i+1}/{N}: {verdict}")

        # Agreement = fraction matching the majority verdict
        majority = max(set(verdicts), key=verdicts.count)
        agree_count = verdicts.count(majority)
        agreement_rate = agree_count / N

        # Disagreement pairs: count runs that differ from majority
        disagree_count = N - agree_count
        total_disagreements += disagree_count
        total_pairs += N

        stable = agreement_rate >= 0.9
        results.append({
            "id": case["id"],
            "verdicts": verdicts,
            "majority": majority,
            "agreement_rate": agreement_rate,
            "stable": stable,
        })
        print(f"  → verdicts={verdicts}  agreement={agreement_rate:.1%}  {'STABLE' if stable else 'UNSTABLE'}\n")

    headline_disagreement_pct = (total_disagreements / total_pairs) * 100
    n_unstable = sum(1 for r in results if not r["stable"])

    print("=" * 60)
    print(f"Headline disagreement: {headline_disagreement_pct:.1f}% ({total_disagreements}/{total_pairs} runs differed from majority)")
    print(f"Unstable cases (agreement < 90%): {n_unstable}/{len(cases)}")
    print()

    for r in results:
        ci_status = "BLOCKING" if r["stable"] else "INFORMATIONAL-ONLY"
        print(f"  {r['id']}: {r['agreement_rate']:.0%} agreement → CI: {ci_status}")

    # Write STABILITY.md
    lines = [
        "# Faithfulness Scorer Stability",
        "",
        f"Harness: `flake_test.py` — N={N} grader runs per case on cached agent responses.",
        f"Grader model: `{GRADER_MODEL}`",
        f"Cache: `evals/scripts/grader_cache.json` (committed; regenerate if agent response format changes)",
        "",
        "## Decision rule",
        "",
        "- agreement_rate ≥ 90% → scorer is **stable** → CI-blocking",
        "- agreement_rate < 90% → scorer is **unstable** → downgrade to informational-only",
        "",
        "## Per-case results",
        "",
        "| Case | Verdicts | Agreement | CI status |",
        "|---|---|---|---|",
    ]
    for r in results:
        ci = "blocking" if r["stable"] else "informational-only"
        verdicts_str = ", ".join(r["verdicts"])
        lines.append(f"| {r['id']} | {verdicts_str} | {r['agreement_rate']:.0%} | {ci} |")

    lines += [
        "",
        "## Headline",
        "",
        f"**Headline disagreement rate: {headline_disagreement_pct:.1f}%** "
        f"({total_disagreements}/{total_pairs} runs differed from majority verdict)",
        "",
        f"**Unstable cases: {n_unstable}/{len(cases)}**",
        "",
    ]

    if n_unstable == 0:
        lines.append(
            "All cases are stable. The faithfulness scorer qualifies to gate CI. "
            "Document N=3 as minimum; consider N=10 for a deeper check in a future session."
        )
    else:
        lines.append(
            f"{n_unstable} case(s) downgraded to informational-only. "
            "These run in CI but do not block merges. Re-run after rubric or grader prompt changes."
        )

    stability_path = os.path.join(_REPO_ROOT, "STABILITY.md")
    with open(stability_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nWrote {stability_path}")


if __name__ == "__main__":
    main()
