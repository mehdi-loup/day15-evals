# Limitations

## Statistical coverage

~20 cases is a description, not a statistic. Accuracy numbers (e.g., "1.000 routing accuracy on 8 cases") reflect performance on a hand-curated set, not a sample from a population. A single agent-behavior change can move these numbers by ±0.125 (one case = 12.5% of an 8-case task). Do not extrapolate to "this agent routes correctly X% of the time in production."

## Real-user query distribution

All cases were authored by the developer during days 15–16 of the sprint. They reflect the developer's mental model of where the agent might fail, not a sample from actual user queries. Production traffic would surface failure modes not represented here (e.g., multilingual queries, adversarial inputs, queries mixing multiple intents).

## Adversarial robustness

Not tested. No prompt injection cases. No cases where wallet token names contain instructions designed to hijack tool arguments. The system prompt has an existing comment noting this as a known attack surface, but it is not evaluated here.

## Latency under load

All evals run single-stream, sequential HTTP requests against the deployed agent. No concurrency testing. p50/p99 latency numbers reflect single-user cold-start behavior, not concurrent load behavior. Vercel Lambda cold-starts inflate p99 by 10–20× over warm-path p50.

## MCP degradation: incomplete coverage

The Zapper MCP server (stdio subprocess) cannot start in a Vercel Lambda. Wallet query cases (`wallet-holdings`, `empty-wallet`) test the MCP error boundary (agent degrades gracefully) but cannot test actual Zapper API results in production. The "Zapper works" path is only testable against the local dev server, not the deployed URL.

## Cross-vendor agent comparison: explicitly out of scope

The agent under test is always the deployed URL, which runs Anthropic claude-haiku-4-5-20251001. A cross-vendor comparison (GPT-4o or Gemini as the agent's underlying LLM) was excluded for Day 17 because:
- The system prompt is Anthropic-tuned (prompt formats differ by provider)
- The MCP integration is Anthropic-tuned
- Cross-vendor porting would require re-validating the agent, not just swapping the model
A same-vendor model-size comparison (Haiku vs. Sonnet vs. Opus as agent LLM) is a natural Day 18 extension via the `?model=` query param pattern described in [RESULTS.md](RESULTS.md) Day 18 handoff.

## Cross-grader variance: bounded to unambiguous rubrics

The Day 17 cross-grader benchmark found 100% Haiku/Sonnet agreement across 12 faithfulness verdicts. This validates Haiku as the CI grader for *these specific rubrics*. If rubrics were made more ambiguous (borderline cases, partial-attribution responses), grader model size would become more important. The 100% agreement is a property of rubric design, not a general claim about Haiku faithfulness quality.

## `ambiguous-price-impact` remains non-deterministic

After the Day 17 system prompt fix, this case improved but did not fully stabilize. The agent correctly declines spot-price-for-swap-simulation queries in ~80–90% of runs; occasional failures are agent-side non-determinism, not scorer error. The combined_routing CI threshold (0.67 floor) tolerates one flake. A more robust fix would require either a negative example in a multi-shot prompt or a structured output constraint on the tool invocation decision.

## Eval-as-training-signal risk

Cases were written by the same developer who wrote the agent system prompt. Several agent fixes (Day 17 Move 1) were directly informed by eval failures. This creates a risk that the eval suite is a target rather than a probe — the agent has been tuned to pass these specific cases, not to generalize. The dataset was frozen after Day 16 specifically to prevent further contamination, but the pre-freeze fixes mean the suite's 1.000 post-fix scores reflect both genuine improvement and eval overfitting.
