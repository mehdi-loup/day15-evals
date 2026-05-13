"""
Task 3: Combined routing eval — Day 16 new cases.

Dataset: datasets/combined_routing.jsonl — 6 cases across three risk categories:
  - ambiguous-routing (2): queries where the wrong tool is tempting
  - combined-live-corpus (2): queries that legitimately need both tools
  - multi-turn-context (2): two-turn conversations where turn 2 depends on turn 1

Scorer strategy (extended from Day 15):
  routing_scorer_v2: deterministic, handles:
    - expected_tool: at least one call to this tool
    - forbidden_tool: this tool must NOT be called
    - required_tools: ALL tools in this list must be called
    - expected_min_calls: dict of tool → minimum call count
    - turn_required_tools: per-turn tool lists (multi-turn cases)
    - zapper_degradation_ok: if True, Zapper absence is not a failure
  faithfulness_scorer: model-graded (reused from agentic_rag.py logic)

Risk categories and what they test:
  ambiguous-routing: does the agent pick the right tool when the query surface
    mentions a different tool's domain? (e.g. "what does the corpus say about prices")
  combined-live-corpus: does the agent call both tools when both are legitimately
    needed? (failure mode: answers only one half)
  multi-turn-context: does the agent carry turn-1 context into turn-2 routing?
    (failure mode: treats turn-2 as a standalone query, picks wrong tool)
"""

import sys
import os
import re

_HERE = os.path.dirname(__file__)
sys.path.insert(0, _HERE)
from solver import wallet_agent_solver

from inspect_ai import Task, task
from inspect_ai.dataset import json_dataset
from inspect_ai.scorer import Scorer, Score, scorer, accuracy, stderr, CORRECT, INCORRECT
from inspect_ai.model import get_model
from inspect_ai.solver import TaskState

from latency import latency_scorer

_DATASETS = os.path.join(_HERE, "..", "datasets")

# Configurable via GRADER_MODEL env var for cross-grader benchmarking (Day 17).
# Default: claude-haiku-4-5-20251001. Override: GRADER_MODEL=anthropic/claude-sonnet-4-6
GRADER_MODEL = os.environ.get("GRADER_MODEL", "anthropic/claude-haiku-4-5-20251001")

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


def _routing_score_v2(state: TaskState) -> Score:
    """
    Extended deterministic routing scorer.

    Handles all cases in combined_routing.jsonl:
      expected_tool: at least one call to this tool
      forbidden_tool: this tool must NOT appear in any tool_calls
      required_tools: ALL tools in this list must appear in tool_calls
      expected_min_calls: {tool: n} — tool must appear at least n times
      turn_required_tools: [[tools for turn 0], [tools for turn 1], ...]
        — checked against state.metadata["turn_tool_calls"]
    """
    tool_calls: list[str] = state.metadata.get("tool_calls", [])
    expected_tool: str | None = state.metadata.get("expected_tool")
    forbidden_tool: str | None = state.metadata.get("forbidden_tool")
    required_tools: list[str] | None = state.metadata.get("required_tools")
    expected_min_calls: dict[str, int] | None = state.metadata.get("expected_min_calls")
    turn_required_tools: list[list[str]] | None = state.metadata.get("turn_required_tools")
    per_turn: list[list[str]] = state.metadata.get("turn_tool_calls", [])

    # 1. forbidden_tool check — must fail before anything else
    if forbidden_tool and any(tc == forbidden_tool or tc.startswith(forbidden_tool + "_") for tc in tool_calls):
        return Score(
            value=INCORRECT,
            answer=", ".join(tool_calls),
            explanation=f"Forbidden tool '{forbidden_tool}' was called: {tool_calls}",
        )

    # 2. required_tools — all must appear
    if required_tools:
        missing = [t for t in required_tools if not any(
            tc == t or tc.startswith(t + "_") for tc in tool_calls
        )]
        if missing:
            return Score(
                value=INCORRECT,
                answer=", ".join(tool_calls) if tool_calls else "no-tool-call",
                explanation=f"Required tools not called: {missing}. Got: {tool_calls}",
            )

    # 3. expected_tool — at least one call
    if expected_tool:
        if not any(tc == expected_tool or tc.startswith(expected_tool + "_") for tc in tool_calls):
            return Score(
                value=INCORRECT,
                answer=", ".join(tool_calls) if tool_calls else "no-tool-call",
                explanation=f"Expected tool '{expected_tool}' not called. Got: {tool_calls}",
            )

    # 4. expected_min_calls — minimum count per tool
    if expected_min_calls:
        for tool, min_count in expected_min_calls.items():
            actual_count = sum(1 for tc in tool_calls if tc == tool or tc.startswith(tool + "_"))
            if actual_count < min_count:
                return Score(
                    value=INCORRECT,
                    answer=", ".join(tool_calls) if tool_calls else "no-tool-call",
                    explanation=f"Expected '{tool}' called at least {min_count}x, got {actual_count}x. Calls: {tool_calls}",
                )

    # 5. turn_required_tools — per-turn assertions
    if turn_required_tools and per_turn:
        for i, (req_tools, turn_calls) in enumerate(zip(turn_required_tools, per_turn)):
            missing = [t for t in req_tools if not any(
                tc == t or tc.startswith(t + "_") for tc in turn_calls
            )]
            if missing:
                return Score(
                    value=INCORRECT,
                    answer=str(per_turn),
                    explanation=f"Turn {i + 1}: required tools {missing} not called. Turn {i + 1} calls: {turn_calls}",
                )

    return Score(
        value=CORRECT,
        answer=", ".join(tool_calls) if tool_calls else "no-tool-call",
        explanation=f"Routing check passed. Calls: {tool_calls}",
    )


@scorer(metrics=[accuracy(), stderr()])
def routing_scorer_v2():
    async def score(state: TaskState, target) -> Score:
        return _routing_score_v2(state)
    return score


@scorer(metrics=[accuracy(), stderr()])
def faithfulness_scorer(model: str = GRADER_MODEL):
    grader = get_model(model)

    async def score(state: TaskState, target) -> Score:
        rubric: str | None = state.metadata.get("judge_rubric")
        if not rubric:
            return Score(value=CORRECT, answer="no-rubric", explanation="No judge_rubric — routing is the sole signal")

        # For multi-turn, evaluate the final turn's output
        prompt = FAITHFULNESS_PROMPT.format(
            question=state.input_text,
            answer=state.output.completion,
            criterion=rubric,
        )
        result = await grader.generate(prompt)
        completion = result.completion.strip()

        match = re.search(r"(?i)GRADE\s*:\s*([CI])", completion)
        if match:
            grade = match.group(1).upper()
            return Score(
                value=CORRECT if grade == "C" else INCORRECT,
                answer=grade,
                explanation=completion,
            )

        return Score(
            value=INCORRECT,
            answer="parse-error",
            explanation=f"Could not parse GRADE from: {completion[:200]}",
        )

    return score


@task
def combined_routing():
    dataset = json_dataset(os.path.join(_DATASETS, "combined_routing.jsonl"))
    return Task(
        dataset=dataset,
        solver=[wallet_agent_solver()],
        scorer=[routing_scorer_v2(), faithfulness_scorer(), latency_scorer()],
    )
