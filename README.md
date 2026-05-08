# day15-evals

**Inspect AI evaluation suite for a publicly deployed TypeScript AI agent.**

This repo scores [day1-wallet-agent](https://github.com/mehdiloup/day1-wallet-agent) — a DeFi portfolio assistant backed by Anthropic's Claude, Mastra, Zapper MCP, and a pgvector RAG corpus — running against the deployed URL: **https://day1-wallet-agent.vercel.app**

The agent is treated as a black box behind an HTTP endpoint. No internal imports. No local dev server required.

Built on Day 15 of a [21-day AI engineer sprint](https://day1-wallet-agent.vercel.app/blog/week2). See [RESULTS.md](RESULTS.md) for the latest run numbers.

---

## What this evaluates

### Task 1: `wallet_agent` — Tool-routing accuracy
8 cases from the Day 7 eval suite, ported from ad-hoc TypeScript scripts to Inspect AI datasets.

Checks: does the agent call the right tool for the right query?
- Price lookups → `getTokenPrice`
- Wallet holdings → Zapper MCP tools (or graceful degradation in prod)
- Send transactions → no tool call (read-only agent refusal)
- Missing wallet address → no tool call (clarification required)

Scorer: **deterministic tool-routing** (no model calls, ~$0/run)

### Task 2: `agentic_rag` — RAG correctness (grounded vs. ungrounded)
6 cases from the Day 12 eval suite.

Checks:
1. **Tool routing** (deterministic): did the agent call `searchCorpus` for grounded questions and avoid it for ungrounded ones?
2. **Faithfulness** (model-graded): did the agent correctly use corpus content for grounded questions and avoid fabricating corpus citations for ungrounded ones?

Scorers: **deterministic tool-routing** + **model-graded faithfulness** (grader: `claude-haiku-4-5-20251001`, ~$0.004/run)

---

## Setup — clone to first run in under 10 minutes

**Prerequisites:** Python 3.12+, `uv` ([install](https://docs.astral.sh/uv/getting-started/installation/)), an Anthropic API key.

```bash
git clone https://github.com/mehdiloup/day15-evals
cd day15-evals

# Install dependencies (creates .venv automatically)
uv sync

# Set your Anthropic API key
cp .env.example .env
# Edit .env and add your key: ANTHROPIC_API_KEY=sk-ant-...
export $(cat .env | xargs)
```

**Run Task 1** (wallet-agent tool-routing, 8 cases, ~5s, no grader cost):
```bash
uv run inspect eval evals/wallet_agent.py --model anthropic/claude-haiku-4-5-20251001 --log-dir logs/
```

**Run Task 2** (agentic RAG, 6 cases, ~8s, ~$0.004 grader cost):
```bash
uv run inspect eval evals/agentic_rag.py --model anthropic/claude-haiku-4-5-20251001 --log-dir logs/
```

**View results in the Inspect AI log viewer:**
```bash
uv run inspect view logs/
```

---

## Why these eval cases?

The Day 7 cases cover the agent's **tool-routing boundary** — the most important behavioral invariant for an agent that exposes dangerous-sounding capabilities (wallet reads, price lookups) while being strictly read-only. Getting the routing wrong (calling `getTokenPrice` for a portfolio query, or calling any tool for a transaction request) is the primary failure mode.

The Day 12 cases cover the agent's **RAG faithfulness boundary** — the split between questions the corpus knows (Wayfinder Paths workflow documentation) and questions outside the corpus (general EVM knowledge, non-existent EIPs). The key failure mode is fabricating corpus citations for ungrounded questions.

Both suites were originally informal TypeScript scripts. This repo is the conversion to a framework that:
- Produces versioned, per-case logs (`inspect view logs/`)
- Gives a single aggregate number per run to compare over time
- Runs against the **deployed production URL**, not localhost

---

## Findings from Day 15

**Zapper MCP prod limitation (real local→prod regression):** The `wallet-holdings` and `empty-wallet` cases revealed that Zapper MCP tools (which use a stdio subprocess) cannot start in Vercel serverless Lambdas. The agent's MCP error boundary correctly degrades — it tells the user which tools are available without hallucinating wallet data. But wallet portfolio queries don't work on the deployed URL. Documented in the dataset as `mcp-degradation` cases; tracked as a Day 16+ agent-side fix.

**Grader prompt failure mode encountered:** The first version of the faithfulness scorer's grader prompt included generic rules about corpus attribution that caused false negatives on grounded cases (the grader penalized "According to the Wayfinder Paths corpus:" even when attribution was correct). Fix: let the per-case rubric be the sole authority; don't add generic rules that might contradict the rubric.

---

## Repo structure

```
day15-evals/
├── evals/
│   ├── solver.py          # custom HTTP solver — POSTs to deployed /api/chat, parses SSE stream
│   ├── wallet_agent.py    # Task 1: tool-routing eval (8 Day-7 cases)
│   └── agentic_rag.py     # Task 2: RAG eval (6 Day-12 cases) with two scorers
├── datasets/
│   ├── wallet_agent.jsonl  # Day 7 cases in Inspect AI Sample format
│   └── agentic_rag.jsonl   # Day 12 cases in Inspect AI Sample format
├── RESULTS.md             # Per-run results log (append new runs here)
└── pyproject.toml         # Python 3.12, inspect-ai 0.3.220, anthropic
```

---

## Inspect AI version

`inspect-ai==0.3.220` (UK AI Safety Institute). Pinned in `pyproject.toml`. See [inspect.aisi.org.uk](https://inspect.aisi.org.uk) for docs.
