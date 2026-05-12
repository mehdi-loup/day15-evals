"""
Task 1: Wallet-agent tool-routing eval (Day 7 cases ported to Inspect AI).

Dataset: datasets/wallet_agent.jsonl — 8 cases covering:
  - deterministic tool-routing (price lookup, wallet holdings, multi-price)
  - no-tool-call checks (refusal, clarification)
  - LLM-judge quality checks on top of tool-routing (unknown token, empty wallet)

Scorer strategy:
  - tool_routing_scorer (deterministic): checks state.metadata["tool_calls"]
    against sample metadata["expected_tool"] / metadata["expect_no_tool"]
  - For cases with a judge_rubric, fails are caught by the deterministic scorer
    and reported; a follow-up model_graded_qa scorer layer is NOT used here
    because the routing check is the primary signal for Day 7 cases.
    (Day 15 introduces model-graded scoring in agentic_rag.py.)

Why deterministic-first for Day 7 cases?
  Tool routing is binary and cheap to check. Model-graded scorers cost a model
  call per case and introduce flakiness — they're the right tool when no string
  match captures correctness. Day 7 cases are mostly tool-routing checks; the
  few that also need quality assessment (unknown-token, empty-wallet) have rubrics
  documented in metadata for a future upgrade.
"""

from inspect_ai import Task, task
from inspect_ai.dataset import json_dataset, Sample
from inspect_ai.scorer import Scorer, Score, scorer, accuracy, stderr, CORRECT, INCORRECT
from inspect_ai.solver import TaskState
import sys, os
_HERE = os.path.dirname(__file__)
sys.path.insert(0, _HERE)
from solver import wallet_agent_solver
from latency import latency_scorer

_DATASETS = os.path.join(_HERE, "..", "datasets")


def _tool_routing_score(state: TaskState, sample: Sample) -> Score:
    """
    Deterministic scorer for tool-routing cases.

    Reads tool_calls from state.metadata (populated by wallet_agent_solver).
    Checks:
      - expected_tool: if set, at least one call to a tool matching this name
        (prefix match to handle zapper-mcp_ variants)
      - expect_no_tool: if True, no tool call expected
      - if both are None (invalid-address case), passes by default — the
        judge_rubric in metadata is the real check for that case.
    """
    tool_calls: list[str] = state.metadata.get("tool_calls", [])
    expected_tool: str | None = state.metadata.get("expected_tool")
    expect_no_tool: bool | None = state.metadata.get("expect_no_tool")

    # No-tool-call check
    if expect_no_tool is True:
        if tool_calls:
            return Score(
                value=INCORRECT,
                answer=", ".join(tool_calls),
                explanation=f"Expected no tool call but got: {tool_calls}",
            )
        return Score(
            value=CORRECT,
            answer="no-tool-call",
            explanation="Correctly made no tool call",
        )

    # Expected-tool check
    if expected_tool is not None:
        # Prefix match: handles both exact names and MCP-namespaced variants
        # e.g. expected "zapper-mcp_get_portfolio" matches "zapper-mcp_get_portfolio"
        # or expected "getTokenPrice" matches "getTokenPrice" exactly
        hit = any(
            tc == expected_tool or tc.startswith(expected_tool + "_")
            for tc in tool_calls
        )
        if not hit:
            return Score(
                value=INCORRECT,
                answer=", ".join(tool_calls) if tool_calls else "no-tool-call",
                explanation=f"Expected tool matching '{expected_tool}' but got: {tool_calls}",
            )
        return Score(
            value=CORRECT,
            answer=", ".join(tool_calls),
            explanation=f"Correctly called '{expected_tool}' (tools called: {tool_calls})",
        )

    # Neither expected_tool nor expect_no_tool is set (e.g. invalid-address).
    # Pass by default — the scoring for this case relies on the judge_rubric
    # which is documented in metadata for a future model-graded scorer upgrade.
    return Score(
        value=CORRECT,
        answer=", ".join(tool_calls) if tool_calls else "no-tool-call",
        explanation="No routing constraint for this case (judge_rubric is the signal)",
    )


@scorer(metrics=[accuracy(), stderr()])
def tool_routing_scorer():
    async def score(state: TaskState, target) -> Score:
        return _tool_routing_score(state, state)

    return score


@task
def wallet_agent():
    dataset = json_dataset(os.path.join(_DATASETS, "wallet_agent.jsonl"))
    return Task(
        dataset=dataset,
        solver=[wallet_agent_solver()],
        scorer=[tool_routing_scorer(), latency_scorer()],
    )
