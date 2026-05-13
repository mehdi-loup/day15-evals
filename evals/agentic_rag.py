"""
Task 2: Agentic RAG eval — grounded vs. ungrounded corpus queries (Day 12 cases).

Dataset: datasets/agentic_rag.jsonl — 6 cases:
  - 3 grounded: questions whose answers ARE in the Wayfinder Paths corpus
  - 3 ungrounded: questions whose answers are NOT in the corpus

Two-scorer strategy:
  1. tool_routing_scorer (deterministic): did the model call the right tool?
     - grounded cases: must call searchCorpus
     - ungrounded-price: must call getTokenPrice, NOT searchCorpus
     - ungrounded-fake-path: must call searchCorpus (searches, finds nothing, says not found)
     - ungrounded-general-defi: no tool constraint (general DeFi knowledge, not a path)
  2. faithfulness_scorer (model-graded): did the grounded responses use corpus content
     correctly, and did ungrounded responses avoid fabricating corpus citations?

Why two scorers?
  Tool routing is binary and cheap. Faithfulness requires reading the full response
  and judging whether it correctly attributes / doesn't over-attribute to the corpus.
  No string match can capture "did the model hallucinate a corpus citation?" — that
  requires understanding the response. Model-graded scorers cost ~1 judge call per
  case and introduce flakiness, so they're layered on top of the cheaper routing check.

Grader prompt failure modes (documented here per the eval repo contract):
  False positive (marks hallucination as faithful):
    - Graded response is vague enough that the rubric condition is trivially satisfied
      e.g. "The response mentions DeFi" could match anything about DeFi
    - Mitigation: rubric specifies WHAT the response must say AND what it must NOT say

  False negative (marks correct response as unfaithful):
    - Grader is over-strict about exact phrasing from the corpus
    - Mitigation: rubric says "consistent with" not "verbatim matches"
    - Note: we cannot verify corpus content in the grader prompt; the grader assesses
      whether the response is *internally consistent* with the rubric's description
      of what the corpus would contain.
"""

import sys, os
_HERE = os.path.dirname(__file__)
sys.path.insert(0, _HERE)
from solver import wallet_agent_solver
from latency import latency_scorer

import os
import re
from inspect_ai import Task, task
from inspect_ai.dataset import json_dataset
from inspect_ai.scorer import Scorer, Score, scorer, accuracy, stderr, CORRECT, INCORRECT
from inspect_ai.model import get_model
from inspect_ai.solver import TaskState

_DATASETS = os.path.join(_HERE, "..", "datasets")

# Grader model: configurable via GRADER_MODEL env var for cross-grader benchmarking.
# Default: claude-haiku-4-5-20251001 (cheap, Anthropic-only, consistent with agent stack).
# Cross-grader runs (Day 17): set GRADER_MODEL=anthropic/claude-sonnet-4-6 to compare.
# Note: --model CLI flag controls the Inspect solver-side model, not the scorer grader.
# Our custom HTTP solver ignores it; env var is the correct override surface for scorers.
GRADER_MODEL = os.environ.get("GRADER_MODEL", "anthropic/claude-haiku-4-5-20251001")

# Grader prompt template for faithfulness scoring.
# Reads criterion from state.metadata["judge_rubric"] — NOT from target.text,
# because target.text carries the tool name for the routing scorer.
# Output format: "GRADE: C" (correct) or "GRADE: I" (incorrect) to match
# the Inspect AI DEFAULT_GRADE_PATTERN = r"(?i)GRADE\s*:\s*([CPI])(.*)$"
#
# Failure modes documented here:
#   False positive: rubric condition is vague enough that any plausible response satisfies it
#     e.g. "must mention DeFi" could match anything
#     Mitigation: rubric specifies exact path names or exact negative phrases
#   False negative: grader over-strict about exact wording
#     Mitigation: rubric says "consistent with" not "verbatim matches"
FAITHFULNESS_PROMPT = """You are evaluating whether an AI assistant's response correctly satisfies a grading criterion.

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


def _tool_routing_score(state: TaskState) -> Score:
    """Deterministic routing check for RAG cases."""
    tool_calls: list[str] = state.metadata.get("tool_calls", [])
    expected_tool: str | None = state.metadata.get("expected_tool")
    expect_no_tool: bool | None = state.metadata.get("expect_no_tool")

    if expect_no_tool is True:
        if tool_calls:
            return Score(
                value=INCORRECT,
                answer=", ".join(tool_calls),
                explanation=f"Expected no tool call but got: {tool_calls}",
            )
        return Score(value=CORRECT, answer="no-tool-call", explanation="Correctly made no tool call")

    if expected_tool is not None:
        hit = expected_tool in tool_calls
        if not hit:
            return Score(
                value=INCORRECT,
                answer=", ".join(tool_calls) if tool_calls else "no-tool-call",
                explanation=f"Expected '{expected_tool}' but got: {tool_calls}",
            )
        return Score(value=CORRECT, answer=", ".join(tool_calls), explanation=f"Correctly called '{expected_tool}'")

    # No routing constraint on this case (rag-ungrounded-general-defi)
    return Score(value=CORRECT, answer="unconstrained", explanation="No tool routing constraint for this case")


@scorer(metrics=[accuracy(), stderr()])
def tool_routing_scorer():
    async def score(state: TaskState, target) -> Score:
        return _tool_routing_score(state)
    return score


@scorer(metrics=[accuracy(), stderr()])
def faithfulness_scorer(model: str = GRADER_MODEL):
    """
    Model-graded faithfulness scorer.
    Reads judge_rubric from state.metadata (not from target.text).
    Uses a custom prompt that asks for GRADE: C or GRADE: I.
    """
    grader = get_model(model)

    async def score(state: TaskState, target) -> Score:
        rubric: str | None = state.metadata.get("judge_rubric")
        if not rubric:
            # No rubric defined — skip faithfulness check (routing scorer is the signal)
            return Score(value=CORRECT, answer="no-rubric", explanation="No judge_rubric for this case")

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

        # Grader returned unexpected format — log the raw output and fail safe
        return Score(
            value=INCORRECT,
            answer="parse-error",
            explanation=f"Could not parse GRADE from: {completion[:200]}",
        )

    return score


@task
def agentic_rag():
    dataset = json_dataset(os.path.join(_DATASETS, "agentic_rag.jsonl"))

    return Task(
        dataset=dataset,
        solver=[wallet_agent_solver()],
        scorer=[tool_routing_scorer(), faithfulness_scorer(), latency_scorer()],
    )
