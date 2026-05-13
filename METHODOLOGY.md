# Methodology

## Why these cases?

The 20 evaluation cases across three tasks cover four failure modes that matter for production agentic systems, and that are underrepresented in existing LLM benchmarks:

1. **Tool-routing correctness** — does the agent invoke the right tool (or no tool) for a given query? Cases span clear-cut queries (standalone price lookup, corpus path question) and deliberately ambiguous ones (price impact vs. spot price, general DeFi question with LP corpus content nearby).

2. **RAG faithfulness** — when the agent retrieves corpus content, does it attribute correctly without fabricating citations? Cases cover grounded queries (answer is in the corpus), ungrounded queries (answer is not in the corpus), and the hard case: partial-match queries where corpus content is *related* but does not directly answer the question.

3. **Degraded-tool behavior** — the Zapper MCP server cannot run in a Vercel Lambda (stdio subprocess restriction). Cases verify the agent degrades gracefully (explains tool unavailability, does not hallucinate holdings) rather than failing silently or fabricating data.

4. **Multi-turn context retention** — does the agent carry routing context across conversation turns? Two-turn cases verify that tool selection in turn 2 is informed by what was established in turn 1.

Risk categories (from Day 16) are tagged in the dataset JSON as `risk_category`: `ambiguous-routing`, `combined-live-corpus`, `multi-turn-context`, `baseline`.

## Why these scorers?

Two scorer types, chosen for complementary failure modes:

**Deterministic routing scorer** (`tool_routing_scorer`, `routing_scorer_v2`): checks which tools were actually called, using metadata fields (`expected_tool`, `forbidden_tool`, `required_tools`, `expected_min_calls`, `turn_required_tools`). No model call required. Zero grader variance. CI-gateable on every commit. The right scorer when the success condition can be expressed as a boolean over tool call names.

**Model-graded faithfulness scorer** (`faithfulness_scorer`): reads the full agent response against a per-case rubric and returns GRADE: C or GRADE: I. Used when correctness requires understanding response content — specifically, whether corpus citations are accurate and whether ungrounded responses avoid fabrication. Rubrics specify exact required phrases and exact forbidden phrases to minimize grader interpretation variance (see Cross-grader benchmark in [RESULTS.md](RESULTS.md)).

Faithfulness is informational-only in CI (not a gate), because agent-side response variance can change the faithfulness verdict without the scorer or rubric changing. The grader stability harness ([STABILITY.md](STABILITY.md)) confirms 0% grader disagreement at N=3 on cached responses — the scorer qualifies as a measurement, not as a gate for non-deterministic agent outputs.

## Why these models?

**Agent under test:** `anthropic/claude-haiku-4-5-20251001` via the deployed URL (`https://day1-wallet-agent.vercel.app/api/chat`). The agent is a fixed system under test — the eval suite makes HTTP requests to the production deployment and measures behavior, not model internals.

**Grader model:** `anthropic/claude-haiku-4-5-20251001` (default). The Day 17 cross-grader benchmark compared Haiku vs. Sonnet 4.6 across 12 faithfulness verdicts and found 100% agreement. This validates Haiku as the CI grader: equivalent faithfulness quality for these rubrics at ~10× lower cost. See [RESULTS.md](RESULTS.md) for the full agreement table.

**Why Anthropic-only for the grader?** Cross-vendor grader comparison (e.g., GPT-4o-mini as grader) was out of scope for Day 17 — the intent was to validate the grader axis within a known provider, not to benchmark providers. A cross-vendor grader comparison would be a natural Day 18+ extension, particularly if the rubrics are made more ambiguous (to expose model-size grader variance).

**What "cross-model" means here (important):** The cross-grader benchmark varies the *judge model* for model-graded scorers, not the agent's underlying LLM. These are two distinct axes. The agent under test is always the deployed URL serving Haiku. See [LIMITATIONS.md](LIMITATIONS.md) for the cross-vendor agent comparison that was explicitly excluded.

## Dataset size justification

~20 cases is adequate for *demonstrating an evaluation methodology* and explicitly insufficient for *making statistical claims about model quality*.

What 20 cases can support:
- "The eval suite correctly caught a named regression (getTokenPriceV2 rename)" — binary yes/no, confirmed
- "The faithfulness scorer has 0% grader disagreement at N=3" — stability measurement, confirmed
- "The ambiguous-price-impact case is agent-side non-deterministic" — qualitative observation from repeated runs, confirmed

What 20 cases cannot support:
- "This agent correctly routes tool calls X% of the time" — requires production traffic sampling, not author-curated cases
- "Model A is better than Model B for agentic RAG" — requires many cases across the capability distribution, not a hand-picked 20
- "This eval generalizes to other agents or domains" — requires deliberately held-out test cases not used during agent development

The 20-case dataset was frozen at Day 16 to avoid eval-as-training-signal contamination: adding cases based on observed agent failures would turn the eval suite into a target, not a probe.

## Reproducibility

| Field | Value |
|---|---|
| Python version | 3.12.13 |
| Inspect AI version | 0.3.220 (pinned in `pyproject.toml`) |
| Agent URL | https://day1-wallet-agent.vercel.app |
| Agent commit (Day 17) | 7a58ea1 (`mehdi-loup/day1-wallet-agent`) |
| Grader default | `anthropic/claude-haiku-4-5-20251001` |
| uv.lock | committed — `uv sync` reproduces the exact environment |

To reproduce from a fresh clone:

```bash
git clone https://github.com/mehdi-loup/day15-evals
cd day15-evals
uv sync
ANTHROPIC_API_KEY=<your-key> uv run inspect eval evals/wallet_agent.py --model anthropic/claude-haiku-4-5-20251001
```

Note: `agentic_rag` and `combined_routing` tasks make Voyage AI + Supabase pgvector calls via the deployed agent. Cold-start latency for these services can push p99 above 60s. The `wallet_agent` task hits only the Anthropic API via the agent and completes in ~5s per case.
