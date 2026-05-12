"""
Custom Inspect AI solver that hits the deployed wallet-agent /api/chat endpoint.

The agent streams SSE in the Vercel AI SDK UIMessageStream format:
  data: {"type":"tool-input-available","toolName":"getTokenPrice",...}
  data: {"type":"text-delta","id":"0","delta":"..."}
  data: {"type":"finish","finishReason":"stop"}
  data: [DONE]

Single-turn (default):
  - POSTs the sample input as a single user message
  - Streams the response, extracts tool names + text
  - Stores tool_calls and wall_clock_ms on state.metadata

Multi-turn (when metadata["turns"] is present):
  - Each turn in the list is sent sequentially with accumulated message history
  - tool_calls is a flat list of all tools called across all turns
  - turn_tool_calls is a list-of-lists (per-turn breakdown)
  - wall_clock_ms is the total for the entire conversation
"""

import json
import time
import uuid
import httpx
from inspect_ai.solver import Solver, TaskState, Generate, solver
from inspect_ai.model import ModelOutput


AGENT_URL = "https://day1-wallet-agent.vercel.app/api/chat"
# connect: 10s for TCP handshake; read: 120s between stream chunks (searchCorpus
# calls Voyage AI embeddings + Supabase pgvector — up to 6s; cold-start adds more)
HTTPX_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=5.0)


def _make_user_message(text: str) -> dict:
    mid = f"eval-{uuid.uuid4().hex[:8]}"
    return {"id": mid, "role": "user", "content": text, "parts": [{"type": "text", "text": text}]}


def _make_assistant_message(text: str) -> dict:
    mid = f"eval-{uuid.uuid4().hex[:8]}"
    return {"id": mid, "role": "assistant", "content": text, "parts": [{"type": "text", "text": text}]}


async def _stream_turn(client: httpx.AsyncClient, messages: list[dict]) -> tuple[list[str], str]:
    """POST messages to /api/chat, stream SSE, return (tool_calls, text)."""
    tool_calls: list[str] = []
    text_chunks: list[str] = []

    async with client.stream("POST", AGENT_URL, json={"messages": messages}) as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            if not line.startswith("data: "):
                continue
            raw = line[6:]
            if raw == "[DONE]":
                break
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue
            etype = event.get("type")
            if etype == "tool-input-available":
                tool_name = event.get("toolName")
                if tool_name:
                    tool_calls.append(tool_name)
            elif etype == "text-delta":
                text_chunks.append(event.get("delta", ""))

    return tool_calls, "".join(text_chunks)


@solver
def wallet_agent_solver() -> Solver:
    async def solve(state: TaskState, generate: Generate) -> TaskState:
        turns_spec: list[dict] | None = state.metadata.get("turns")
        t_start = time.monotonic()

        async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT) as client:
            if turns_spec:
                # Multi-turn: thread message history across turns
                history: list[dict] = []
                all_tool_calls: list[str] = []
                per_turn_tool_calls: list[list[str]] = []
                final_text = ""

                for turn in turns_spec:
                    if turn["role"] != "user":
                        continue
                    history.append(_make_user_message(turn["text"]))
                    turn_tools, turn_text = await _stream_turn(client, history)
                    all_tool_calls.extend(turn_tools)
                    per_turn_tool_calls.append(turn_tools)
                    # Append assistant reply to history so next turn sees the context
                    history.append(_make_assistant_message(turn_text))
                    final_text = turn_text  # last turn's text is the output

                state.metadata["tool_calls"] = all_tool_calls
                state.metadata["turn_tool_calls"] = per_turn_tool_calls
            else:
                # Single-turn (original behaviour)
                messages = [_make_user_message(state.input_text)]
                tool_calls, final_text = await _stream_turn(client, messages)
                state.metadata["tool_calls"] = tool_calls

        wall_clock_ms = int((time.monotonic() - t_start) * 1000)
        state.metadata["wall_clock_ms"] = wall_clock_ms

        state.output = ModelOutput.from_content(
            model="wallet-agent-deployed",
            content=final_text,
        )
        return state

    return solve
