"""
Latency scorer and metrics shared across all three eval tasks.

The solver stores wall_clock_ms in state.metadata for every sample.
latency_scorer() reads that value and returns Score(value=ms) so that
the p50/p99/max metric reducers can aggregate across samples.

Latency is per-case end-to-end wall clock (includes cold-start if any).
The first case in a run is most likely to be a cold-start; the metric
doesn't tag which case is cold, but the max_ms() surface shows it.

Per-task budgets (set in CI workflow):
  wallet_agent      p99 < 8000ms
  agentic_rag       p99 < 20000ms
  combined_routing  p99 < 30000ms  (multi-turn cases do 2 HTTP calls each)
"""

from inspect_ai.scorer import scorer, Score, SampleScore, metric, Metric, Value
from inspect_ai.solver import TaskState


@metric
def p50_ms() -> Metric:
    def calc(scores: list[SampleScore]) -> Value:
        vals = sorted(
            float(ss.score.value) for ss in scores
            if ss.score is not None and isinstance(ss.score.value, (int, float))
        )
        if not vals:
            return 0.0
        return vals[len(vals) // 2]
    return calc


@metric
def p99_ms() -> Metric:
    def calc(scores: list[SampleScore]) -> Value:
        vals = sorted(
            float(ss.score.value) for ss in scores
            if ss.score is not None and isinstance(ss.score.value, (int, float))
        )
        if not vals:
            return 0.0
        # for small N (<100), p99 = max; avoids 0-index underflow
        idx = max(0, int(len(vals) * 0.99) - 1) if len(vals) >= 100 else len(vals) - 1
        return vals[idx]
    return calc


@metric
def max_ms() -> Metric:
    def calc(scores: list[SampleScore]) -> Value:
        vals = [
            float(ss.score.value) for ss in scores
            if ss.score is not None and isinstance(ss.score.value, (int, float))
        ]
        return max(vals) if vals else 0.0
    return calc


@scorer(metrics=[p50_ms(), p99_ms(), max_ms()])
def latency_scorer():
    async def score(state: TaskState, target) -> Score:
        wall_clock_ms = state.metadata.get("wall_clock_ms", 0)
        return Score(value=float(wall_clock_ms))
    return score
