# Agentic RAG Eval Suite

[![Eval Suite](https://github.com/mehdi-loup/day15-evals/actions/workflows/eval.yml/badge.svg)](https://github.com/mehdi-loup/day15-evals/actions/workflows/eval.yml)

**Inspect AI evaluation suite for a deployed TypeScript AI agent: tool-routing accuracy, RAG faithfulness, latency, and cross-grader stability — with CI-enforced regression gates and a cross-grader benchmark showing 100% Haiku/Sonnet agreement on precise rubrics.**

This repo scores [day1-wallet-agent](https://github.com/mehdi-loup/day1-wallet-agent) — a DeFi portfolio assistant backed by Anthropic Claude, Zapper MCP, and a pgvector RAG corpus — via its deployed URL as a **black-box HTTP endpoint**. No internal imports. No local dev server.

---

## TL;DR

| | |
|---|---|
| **Cases** | 20 across 3 tasks (wallet routing, agentic RAG, advanced routing edge cases) |
| **Scorers** | Deterministic tool-routing + model-graded faithfulness + latency |
| **Models benchmarked** | Haiku 4.5 vs Sonnet 4.6 as grader — 100% agreement (see [Cross-grader findings](#cross-grader-findings)) |
| **CI** | PR gate + nightly, green badge above |
| **Latest run** | 2026-05-13 — all tasks passing; full numbers in [RESULTS.md](RESULTS.md) |

---

## Quickstart

**Prerequisites:** Python 3.12+, [`uv`](https://docs.astral.sh/uv/), an Anthropic API key.

```bash
git clone https://github.com/mehdi-loup/day15-evals
cd day15-evals
uv sync
export ANTHROPIC_API_KEY=sk-ant-...
uv run inspect eval evals/wallet_agent.py --model anthropic/claude-haiku-4-5-20251001
```

Task 1 completes in ~5s at ~$0/run (deterministic scorer). Tasks 2–3 hit Voyage AI + Supabase via the agent and take 60–120s with ~$0.01/run grader cost.

---

## What this evaluates

### Task 1: `wallet_agent` — Tool-routing accuracy

8 cases covering the agent's core routing invariant: does the right tool get called for the right query?

| Query type | Expected behavior |
|---|---|
| "What is ETH at?" | calls `getTokenPrice` |
| "Show me my wallet" | calls Zapper MCP (or degrades gracefully in prod) |
| "Send 1 ETH to 0x..." | no tool call — read-only agent refuses |
| "Check my portfolio" (no address) | no tool call — requests clarification |

Scorer: **deterministic** — no grader calls, zero cost, zero variance.

### Task 2: `agentic_rag` — RAG faithfulness

6 cases testing two failure modes: incorrect tool routing (calling searchCorpus when the answer isn't in the corpus) and faithfulness failures (fabricating corpus citations).

| Case type | Expected behavior |
|---|---|
| Grounded query (answer is in corpus) | calls `searchCorpus`, attributes correctly |
| Ungrounded query (answer not in corpus) | does NOT fabricate a corpus citation |
| Price query with corpus context | calls `getTokenPrice`, not `searchCorpus` |

Scorers: **deterministic routing** + **model-graded faithfulness** (Haiku grader, ~$0.004/run).

### Task 3: `combined_routing` — Advanced routing edge cases

6 cases across 3 risk categories added in Day 16:

| Risk category | Cases | Tests |
|---|---|---|
| `ambiguous-routing` | 2 | Wrong tool is tempting (e.g., "price impact" ≠ spot price lookup) |
| `combined-live-corpus` | 2 | Both tools legitimately needed; failure = answering only one half |
| `multi-turn-context` | 2 | Turn-2 routing depends on turn-1 context; failure = ignoring history |

Scorers: **extended deterministic routing** (handles `forbidden_tool`, `required_tools`, `turn_required_tools`) + **faithfulness** + **latency** (p50/p99/max).

---

## Cross-grader findings

Day 17 benchmark: ran both graded tasks (agentic_rag, combined_routing) against two grader models — Haiku 4.5 (baseline) and Sonnet 4.6 (comparison). The `GRADER_MODEL` env var controls the scorer's judge; `--model` controls the solver-side model (ignored by our HTTP solver).

**Result: 100% agreement across 12 faithfulness verdicts.**

| Task | Haiku faithfulness | Sonnet faithfulness | Agreement |
|---|---|---|---|
| `agentic_rag` | 1.000 (6/6) | 1.000 (6/6) | 100% |
| `combined_routing` | 1.000 (6/6) | 1.000 (6/6) | 100% |

**What this means:** Precise rubrics (exact required phrases, exact forbidden phrases) remove model-size grading variance. When rubrics are unambiguous, even Haiku reads them the same as Sonnet. The practical consequence: **Haiku is the right CI grader** — same faithfulness quality for these rubrics at ~10× lower cost. See [RESULTS.md](RESULTS.md) for per-case verdicts and [METHODOLOGY.md](METHODOLOGY.md) for the grader axis rationale.

To reproduce:
```bash
bash evals/scripts/cross_grader_benchmark.sh
# or manually:
GRADER_MODEL=anthropic/claude-sonnet-4-6 uv run inspect eval evals/agentic_rag.py --model anthropic/claude-haiku-4-5-20251001
```

---

## Agent-side flake fixes (Day 17)

Two known agent flakes from Day 16 were patched in the agent's system prompt and verified with the eval suite:

| Flake | Pre-fix score | Post-fix score |
|---|---|---|
| `ambiguous-price-impact` — agent confused "price impact" with spot price | combined_routing routing: 0.833 | **1.000** |
| `rag-ungrounded-general-defi` — agent fabricated Uniswap/Aave corpus citations | agentic_rag faithfulness: 0.833 | **1.000** |

The eval suite found both; the agent was patched; the suite confirmed the fixes. That's the regression-gate workflow working as intended.

---

## Repo structure

```
.
├── evals/
│   ├── solver.py             # HTTP solver — POSTs to deployed /api/chat, parses SSE stream
│   ├── wallet_agent.py       # Task 1 (8 cases, deterministic)
│   ├── agentic_rag.py        # Task 2 (6 cases, routing + faithfulness)
│   ├── combined_routing.py   # Task 3 (6 cases, extended routing + faithfulness + latency)
│   ├── latency.py            # shared latency scorer
│   └── scripts/
│       ├── flake_test.py               # grader stability harness (N=3 on cached responses)
│       ├── cross_grader_benchmark.sh   # cross-grader benchmark (Day 17)
│       └── grader_cache.json           # committed cached agent responses
├── datasets/
│   ├── wallet_agent.jsonl
│   ├── agentic_rag.jsonl
│   └── combined_routing.jsonl
├── .github/workflows/eval.yml  # CI: PR gate + nightly + workflow_dispatch
├── RESULTS.md                  # Per-run results and cross-grader benchmark table
├── METHODOLOGY.md              # Why these cases, scorers, models, and dataset size
├── LIMITATIONS.md              # What this eval does not measure
└── STABILITY.md                # Grader stability report
```

---

## Methodology

See [METHODOLOGY.md](METHODOLOGY.md) for:
- Why these cases (four failure modes: routing, RAG faithfulness, MCP degradation, multi-turn)
- Why two scorer types (deterministic vs. model-graded, and when to use each)
- Why Haiku as the default grader (validated by cross-grader benchmark)
- Dataset size justification (~20 cases: adequate for methodology demonstration, insufficient for statistical claims)
- Reproducibility checklist (Python version, Inspect AI pin, agent commit, uv.lock)

---

## Limitations

See [LIMITATIONS.md](LIMITATIONS.md) for an honest accounting of what this eval does not measure: statistical coverage, real-user query distribution, adversarial robustness, latency under load, cross-vendor agent comparison, and eval-as-training-signal risk.

---

## Citation

If you reference this work:

```
Nasom, M. (2026). Agentic RAG Eval Suite: tool-routing accuracy, RAG faithfulness,
and cross-grader stability for a deployed TypeScript AI agent.
GitHub: https://github.com/mehdi-loup/day15-evals
```

---

## License

Apache 2.0 — see [LICENSE](LICENSE) if present, otherwise assume Apache 2.0.

## Author

Mehdi Loup Nasom — [GitHub](https://github.com/mehdi-loup) · [Agent](https://day1-wallet-agent.vercel.app) · built during a 21-day AI engineer sprint ([Week 2 blog](https://day1-wallet-agent.vercel.app/blog/week2))
