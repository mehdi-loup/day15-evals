"""
Custom Inspect AI solver that hits the deployed wallet-agent /api/chat endpoint.

The agent streams SSE in the Vercel AI SDK UIMessageStream format:
  data: {"type":"tool-input-available","toolName":"getTokenPrice",...}
  data: {"type":"text-delta","id":"0","delta":"..."}
  data: {"type":"finish","finishReason":"stop"}
  data: [DONE]

The solver:
  1. POSTs the sample input as a single user message
  2. Streams the response and parses each SSE line
  3. Extracts tool names from tool-input-available events
  4. Accumulates text from text-delta events
  5. Stores both on state.metadata so scorers can read them
  6. Sets state.output.completion to the final text

Tool names are stored in state.metadata["tool_calls"] as a list[str].
"""

import json
import uuid
import httpx
from inspect_ai.solver import Solver, TaskState, Generate, solver
from inspect_ai.model import ChatMessageAssistant, ModelOutput


AGENT_URL = "https://day1-wallet-agent.vercel.app/api/chat"
TIMEOUT_SECONDS = 60


@solver
def wallet_agent_solver() -> Solver:
    async def solve(state: TaskState, generate: Generate) -> TaskState:
        user_text = state.input_text

        payload = {
            "messages": [
                {
                    "id": f"eval-{uuid.uuid4().hex[:8]}",
                    "role": "user",
                    "content": user_text,
                    "parts": [{"type": "text", "text": user_text}],
                }
            ]
        }

        tool_calls: list[str] = []
        text_chunks: list[str] = []

        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            async with client.stream("POST", AGENT_URL, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    raw = line[6:]  # strip "data: " prefix
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
                        delta = event.get("delta", "")
                        text_chunks.append(delta)

        final_text = "".join(text_chunks)

        # Store tool call list in metadata so scorers can read it
        # without needing to re-parse the completion text.
        state.metadata["tool_calls"] = tool_calls

        # Populate output so model-graded scorers can read state.output.completion
        state.output = ModelOutput.from_content(
            model="wallet-agent-deployed",
            content=final_text,
        )

        return state

    return solve
