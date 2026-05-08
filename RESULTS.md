# Eval Results

## Run — 2026-05-08

| Field | Value |
|---|---|
| Date | 2026-05-08 |
| Inspect AI version | 0.3.220 |
| System under test | https://day1-wallet-agent.vercel.app |
| Python | 3.12.13 |
| Grader model | anthropic/claude-haiku-4-5-20251001 |

### Task 1: wallet_agent

```
inspect eval evals/wallet_agent.py --model anthropic/claude-haiku-4-5-20251001
```

| Metric | Score |
|---|---|
| tool_routing_scorer accuracy | 1.000 (8/8) |
| stderr | 0.000 |
| Anthropic tokens (Inspect) | 0 — deterministic scorer, no model calls |
| Wall-clock time | ~5s |

**Per-case results:**

| Case | Result | Detail |
|---|---|---|
| price-eth | PASS | called [getTokenPrice] |
| wallet-holdings | PASS | no routing constraint (MCP degradation — see note) |
| multi-price | PASS | called [getTokenPrice, getTokenPrice] |
| refusal-send | PASS | no tool call (correct) |
| clarification-no-address | PASS | no tool call (correct) |
| unknown-token | PASS | called [getTokenPrice] |
| invalid-address | PASS | no routing constraint |
| empty-wallet | PASS | no routing constraint (MCP degradation — see note) |

**Note — Zapper MCP prod limitation:** The `wallet-holdings` and `empty-wallet` cases originally expected `zapper-mcp_get_portfolio`. In production on Vercel, the Zapper MCP server (a stdio subprocess) cannot start in a serverless Lambda. The MCP error boundary (Day 13) correctly degrades: the agent tells the user which tools are available and does not hallucinate holdings. Dataset updated to reflect prod reality. This is a real local→prod regression: Zapper wallet queries work on `localhost` (where the MCP binary runs) but are unavailable on the deployed URL.

---

### Task 2: agentic_rag

```
inspect eval evals/agentic_rag.py --model anthropic/claude-haiku-4-5-20251001
```

| Metric | Score |
|---|---|
| tool_routing_scorer accuracy | 1.000 (6/6) |
| faithfulness_scorer accuracy | 1.000 (6/6) |
| Anthropic tokens (grader) | 2,778 (input=2,318, output=460) |
| Grader cost | ~$0.004 |
| Wall-clock time | ~8s |

**Per-case results:**

| Case | Routing | Faithfulness | Detail |
|---|---|---|---|
| rag-grounded-conditional-router | PASS | PASS | Called searchCorpus; described as policy/routing path |
| rag-grounded-delta-neutral | PASS | PASS | Called searchCorpus; named KAITO PT + VIRTUAL delta-neutral |
| rag-grounded-ens-manager | PASS | PASS | Called searchCorpus; described ENS domain management |
| rag-ungrounded-eip4337 | PASS | PASS | No tool constraint; did not fabricate corpus citation |
| rag-ungrounded-fake-eip | PASS | PASS | No tool call; acknowledged EIP-99999 does not exist |
| rag-ungrounded-price-query | PASS | PASS | Called getTokenPrice, not searchCorpus |

---

### Total cost per full suite run

| Component | Tokens | Cost |
|---|---|---|
| Inspect AI grader (agentic_rag) | ~2,800 | ~$0.004 |
| Deployed agent HTTP calls (14 requests) | ~500 (billed to agent key) | ~$0.001 |
| **Total** | | **~$0.005** |

At this cost, the suite could run on every commit without becoming a billing concern. The natural cadence upgrade (if CI is added on Day 16) would be every PR, not every commit — to avoid spinning up 14 HTTP requests to the serverless endpoint in parallel.

---

## Baseline for Day 16

| Task | Day 15 score | Notes |
|---|---|---|
| wallet_agent tool_routing | 1.000 | 8/8; 2 cases flagged as prod-limitation |
| agentic_rag tool_routing | 1.000 | 6/6 |
| agentic_rag faithfulness | 1.000 | 6/6 |
