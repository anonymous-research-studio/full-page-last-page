"""Run one episode: a model, a condition, the mock API, and a capped tool loop."""

from __future__ import annotations

import json
from dataclasses import asdict

from fplp import __version__
from fplp.agents.base import ModelClient
from fplp.env.server import MockAPI
from fplp.env.tools import tool_schemas
from fplp.tasks.specs import EpisodeSpec

_PREAMBLE = (
    "You are an assistant for the operations team of an online store. You have access to the "
    "store's internal API through the tools provided. Use the tools to answer the user's question.\n\n"
)
SYSTEM_PROMPT = _PREAMBLE + "When you are done, end your reply with a line of the form:\nFINAL ANSWER: <your answer>"
# The answer-format arm adds a structured completeness field, which makes disclosure measurable
# without the regex but may itself cue checking for more data; it is therefore a factor.
SYSTEM_PROMPT_COMPLETENESS = _PREAMBLE + (
    "When you are done, end your reply with two lines of the form:\n"
    "FINAL ANSWER: <your answer>\n"
    "COMPLETENESS: <complete, partial, or unknown>"
)
SYSTEM_PROMPTS = {"final_line": SYSTEM_PROMPT, "completeness": SYSTEM_PROMPT_COMPLETENESS}
# Shown only if the model tries to exceed the cap, so it never cues episodes that stay under it.
LIMIT_RESULT = json.dumps({"error": "tool call limit reached"})
LIMIT_NOTICE = "Tool call limit reached. No more tool calls are possible. Give your final answer now."
# After the notice the loop ends: a tool call in the final turn (possible only on hosts that cannot
# disable tools) is not executed, and the turn's text is the final answer.
# Stop reasons meaning the output was cut at the model's max_tokens (Chat Completions, Messages API).
TRUNCATED = ("length", "max_tokens")


def run_episode(client: ModelClient, spec: EpisodeSpec, *, max_tool_calls: int) -> dict:
    api = MockAPI(spec)
    c = spec.condition
    tools = tool_schemas(c.page_limit, c.documented, c.limit_stated, c.doc_wording)
    session = client.open(SYSTEM_PROMPTS[c.answer_format], spec.question, tools, oracle=spec)

    turns: list = []
    hit_cap = False
    try:
        turns.append(session.first())
        while turns[-1].tool_calls and not hit_cap:
            results = []
            for tc in turns[-1].tool_calls:
                if len(api.calls) < max_tool_calls:
                    results.append((tc, api.call(tc.name, tc.arguments)))
                    api.calls[-1]["turn"] = len(turns)  # 1-based turn that issued the call
                else:
                    hit_cap = True
                    results.append((tc, LIMIT_RESULT))
            turns.append(session.finalize(results, LIMIT_NOTICE) if hit_cap else session.reply(results))
    except Exception as e:
        # Tokens of the turns that completed before the failure, so the run charges what was billed.
        e.partial_tokens = (sum(t.tokens_in for t in turns), sum(t.tokens_out for t in turns),
                            sum(t.cache_write for t in turns), sum(t.cache_read for t in turns))
        raise

    return {
        "harness_version": __version__,
        "model": client.name,
        "condition": spec.condition.to_dict(),
        "question": spec.question,
        "target": {"tool": spec.target_tool, "args": spec.target_args},
        "n_items": len(spec.rows),
        "first_page_size": spec.first_page_size,
        "gold": asdict(spec.gold),
        "calls": api.calls,
        "turns": [asdict(t) for t in turns],
        "final_text": turns[-1].text,
        # A last turn with no text and no tool call is a protocol failure (e.g. a host dropping a
        # tool call into the reasoning channel), not a decision to stop; analysis excludes it.
        # A refusal is an outcome to report, not a protocol failure, so it is not flagged.
        "empty_reply": not turns[-1].text.strip() and not turns[-1].tool_calls
        and turns[-1].stop_reason != "refusal",
        "stop_reason": turns[-1].stop_reason,
        "truncated": any(t.stop_reason in TRUNCATED for t in turns),
        "hit_cap": hit_cap,
        "max_tool_calls": max_tool_calls,
        "tokens_in": sum(t.tokens_in for t in turns),
        "tokens_out": sum(t.tokens_out for t in turns),
        "cache_write": sum(t.cache_write for t in turns),
        "cache_read": sum(t.cache_read for t in turns),
    }
