# Faithfulness Scorer Stability

Harness: `flake_test.py` — N=3 grader runs per case on cached agent responses.
Grader model: `claude-haiku-4-5-20251001`
Cache: `evals/scripts/grader_cache.json` (committed; regenerate if agent response format changes)

## Decision rule

- agreement_rate ≥ 90% → scorer is **stable** → CI-blocking
- agreement_rate < 90% → scorer is **unstable** → downgrade to informational-only

## Per-case results

| Case | Verdicts | Agreement | CI status |
|---|---|---|---|
| rag-grounded-conditional-router | C, C, C | 100% | blocking |
| rag-grounded-delta-neutral | C, C, C | 100% | blocking |
| rag-grounded-ens-manager | C, C, C | 100% | blocking |
| rag-ungrounded-fake-path | C, C, C | 100% | blocking |
| rag-ungrounded-general-defi | C, C, C | 100% | blocking |
| rag-ungrounded-price-query | C, C, C | 100% | blocking |

## Headline

**Headline disagreement rate: 0.0%** (0/18 runs differed from majority verdict)

**Unstable cases: 0/6**

All cases are stable. The faithfulness scorer qualifies to gate CI. Document N=3 as minimum; consider N=10 for a deeper check in a future session.
